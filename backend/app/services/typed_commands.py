"""Resolve typed media references before generic style/duration grammar."""
import re
from app.schemas.editing_plan import CommandResponse

def handle_typed_command(request):
    from app.services.command_interpreter import _resolve_clip_index, _parse_num, _recalc_timeline
    from app.services.timeline_edits import retime_attached
    plan = request.current_plan.model_copy(deep=True)
    before = request.current_plan
    text = request.command.lower().strip()
    def result(message):
        changed = plan.model_dump() != before.model_dump()
        return CommandResponse(plan=plan, explanation=message, applied_changes=[message] if changed else [], handled=True)
    toggle = re.search(r'\b(disable|enable|mute|unmute)\s+(?:all\s+|automatic\s+|auto\s+)?(b-?roll|list sounds?|click sounds?)', text)
    if toggle:
        field = 'auto_broll' if 'roll' in toggle[2] else 'list_sounds'
        setattr(plan,field,toggle[1] in ('enable','unmute'))
        return result(f'{toggle[2].capitalize()} {"enabled" if getattr(plan,field) else "disabled"}.')
    if 'keep the speaker visible' in text:
        for insert in plan.visual_inserts:
            insert.mode='split';insert.origin='manual'
        return result('Changed B-roll to split screen with the speaker retained.')
    contextual = re.search(r'\bput\s+(?:the\s+)?(.+?)\s+(video|image|photo)\s+when\s+.*?(?:talking about|mention)\s+(.+?)[.!?]?$',text)
    if contextual:
        query,kind,topic=contextual.groups()
        topic=topic.strip(' .!?')
        segment=next((s for s in (plan.subtitles or plan.transcript) if topic in s.text.lower()),None)
        if not segment:return result(f'Could not find "{topic}" in the transcript. No media was changed.')
        word=next((w for w in segment.words if topic.split()[0] in w.word.lower()),None)
        start=word.start if word else segment.start_time
        if start >= plan.duration_seconds:
            return result('That spoken mention is outside the current timeline. No media was changed.')
        media_type='video' if kind=='video' else 'image'
        source_clip=next((c for c in plan.clips if c.start_time<=start<c.start_time+c.duration),None)
        existing=[i for i in plan.visual_inserts if i.media_type==media_type
                  and query.rstrip('s') in ((i.query or '')+' '+(i.label or '')).lower()]
        if len(existing)>1:return result('Several inserts match that description; specify an ordinal or use the Inserts panel.')
        if existing:
            existing[0].start_time=start;existing[0].duration=min(existing[0].duration,plan.duration_seconds-start);existing[0].origin='manual'
            existing[0].source_clip_id=source_clip.id if source_clip else None
        else:
            from app.services import pixabay
            from app.schemas.editing_plan import VisualInsert
            import uuid
            try:
                matches=pixabay.search(query,media_type,plan.aspect_ratio)
                selected=next((m for m in matches if m['relevance']>=.5),None)
                if not selected:return result('No relevant media matched. Try a more specific search in Inserts.')
                asset=pixabay.download(selected['id'],media_type)
                plan.visual_inserts.append(VisualInsert(id='insert-'+uuid.uuid4().hex[:16],asset_id=str(asset['id']),
                    asset_url=asset['url'],start_time=start,
                    duration=min(2.5,plan.duration_seconds-start,asset.get('duration',2.5) if media_type=='video' else 2.5),mode='split',
                    media_type=media_type,query=query,label=query.title(),source_page=asset['source_page'],contributor=asset['contributor'],
                    source_clip_id=source_clip.id if source_clip else None))
            except pixabay.MediaProviderError as exc:return result(str(exc))
        return result(f'Placed {query} {kind} at the spoken mention of {topic}.')
    if re.search(r'(add|enable).*click.*(every|each|list)',text):
        from app.services.list_sounds import generate_list_cues
        fresh=generate_list_cues(plan.subtitles)
        for cue in fresh:
            if not any(abs(cue.start_time-old.start_time)<.18 for old in plan.sound_cues):
                plan.sound_cues.append(cue)
        plan.list_sounds=True
        return result('Added synchronized clicks to detected list items.' if fresh else 'No clearly timed list items were found; no cues were added.')
    mute = re.search(r'\b(mute|unmute)\b.*\b(\w+)\s+item', text)
    if mute:
        cues=sorted(plan.sound_cues,key=lambda c:c.start_time)
        index=_resolve_clip_index(mute[2],len(cues))
        if index is None:
            return result('The requested list item could not be found.')
        cues[index].muted=mute[1]=='mute';cues[index].origin='manual'
        return result(f'List item {index+1} sound {"muted" if cues[index].muted else "enabled"}.')
    if 'text-behind-speaker' in text or 'text behind speaker' in text:
        from app.services.cinematic import suggest_cinematic_texts
        from app.services.segmentation import existing_masks, mask_duration
        if not plan.cinematic_texts:
            plan.cinematic_texts=suggest_cinematic_texts(plan)
        if not plan.cinematic_texts:
            return result('Add or transcribe an opening caption first.')
        title=plan.cinematic_texts[0]
        clip=next((c for c in plan.clips if c.id==title.source_clip_id),None)
        try:
            if not clip: raise ValueError('Opening clip is missing.')
            existing_masks(clip,plan.aspect_ratio,plan.fit_mode,mask_duration(plan,clip))
        except ValueError:
            plan=before.model_copy(deep=True)
            return result('Prepare Text behind speaker in the Inserts panel first; the command has not enabled a fake effect.')
        title.behind_subject=True;title.origin='manual'
        return result('Enabled subject-aware text for the opening.')
    match=re.search(r'\b(remove|delete|move|make|set|extend|shorten)\s+(?:the\s+)?(\w+)\s+(b-?roll(?:\s+clip)?|photo|image|video(?:\s+clip)?|clip)\b',text)
    if not match:
        return None
    action, ordinal, kind=match.groups()
    if kind=='clip':
        pool=[('clips',c) for c in plan.clips]
    elif 'roll' in kind:
        pool=[('visual_inserts',i) for i in plan.visual_inserts]
    else:
        media='video' if 'video' in kind else 'image'
        pool=[('clips',c) for c in plan.clips if c.media_type==media]
        pool += [('visual_inserts',i) for i in plan.visual_inserts if i.media_type==media]
    pool.sort(key=lambda pair:pair[1].start_time)
    index=_resolve_clip_index(ordinal,len(pool))
    if index is None:
        return result(f'Could not find the {ordinal} {kind}; the project is unchanged.')
    collection,item=pool[index]
    if action in ('remove','delete'):
        setattr(plan,collection,[c for c in getattr(plan,collection) if c.id!=item.id])
        if collection=='visual_inserts':
            plan.suppressed_auto_inserts=list(set(plan.suppressed_auto_inserts+[item.id]))
    elif action=='move':
        destination=re.search(r'\bto\s+(?:the\s+)?(beginning|start|end|front|back|position\s+\d+)',text)
        if not destination: return result('Specify beginning, end, or a numbered position.')
        if collection=='visual_inserts':
            item.start_time=0 if destination[1] in ('beginning','start','front') else max(0,plan.duration_seconds-item.duration)
            item.source_clip_id=None;item.origin='manual'
        else:
            plan.clips.remove(item)
            pos=0 if destination[1] in ('beginning','start','front') else len(plan.clips)
            if destination[1].startswith('position'):
                pos=int(destination[1].split()[-1])-1
            if not 0<=pos<=len(plan.clips):
                plan=before.model_copy(deep=True);return result('Destination position is outside the timeline.')
            plan.clips.insert(pos,item)
    else:
        duration=re.search(r'\b(?:last|to|by|duration)\s+(\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten)\s*seconds?',text)
        if not duration: return result('Specify a duration in seconds.')
        seconds=_parse_num(duration[1])
        value=item.duration+seconds if action=='extend' else item.duration-seconds if action=='shorten' else seconds
        if value is None or value<.1 or value>120:
            return result('Duration must be between 0.1 and 120 seconds.')
        if collection=='visual_inserts':
            if item.start_time+value>plan.duration_seconds:
                return result('The insert would extend past the project end.')
            item.origin='manual'
        item.duration=value
    if collection=='clips':
        _recalc_timeline(plan)
        if not plan.clips: plan.duration_seconds=0
        adjacent={(a.id,b.id) for a,b in zip(plan.clips,plan.clips[1:])}
        plan.transitions=[t for t in plan.transitions if ((t.get('from_clip_id'),t.get('to_clip_id')) if isinstance(t,dict)
                          else (t.from_clip_id,t.to_clip_id)) in adjacent]
        retime_attached(before,plan)
    if plan.duration_seconds>120:
        plan=before.model_copy(deep=True);return result('The edit would exceed the 120-second project limit.')
    return result(f'Applied {action} to the {ordinal} {kind}.')
