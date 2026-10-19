import { useEffect, useRef, useCallback, useMemo } from 'react';
import type { EditingPlan } from '../../types';
import { creativeRequest, getMediaUrl } from '../../services/api';
import { insertRect, drawCover } from '../../utils/composition';

interface Matte { key: string; fps: number; frames: number; url_template: string }
export function useCreativePreview(plan: EditingPlan, isPlaying: boolean, seekVersion: number,
  timeRef: {current:number}, invalidate: {current:(time:number)=>void}, onWarning: (message:string)=>void) {
  const images = useRef(new Map<string, HTMLImageElement>());
  const videos = useRef(new Map<string, HTMLVideoElement>());
  const mattes = useRef(new Map<string, Matte>());
  const captions = useRef<Array<{start_time:number;end_time:number;url:string}>>([]);
  const titles = useRef(new Map<string,string[]>());
  const audioContext = useRef<AudioContext | null>(null);
  const sounds = useRef(new Map<string, Promise<AudioBuffer>>());
  const sources = useRef<AudioBufferSourceNode[]>([]);
  const titleCanvas = useRef<HTMLCanvasElement | null>(null);
  const splitCanvas = useRef<HTMLCanvasElement | null>(null);
  const maskCanvas = useRef<HTMLCanvasElement | null>(null);
  const image=useCallback((url:string) => {
    let element=images.current.get(url);
    if(!element){
      element=new Image(); element.onload=()=>{
        // Decoded RGBA images, especially full-frame captions, dominate memory.
        let pixels=[...images.current.values()].reduce((sum,img)=>sum+img.naturalWidth*img.naturalHeight,0);
        for(const [key,img] of images.current){
          if(pixels<=32*1024*1024 && images.current.size<=220)break;
          if(key===url)continue;
          pixels-=img.naturalWidth*img.naturalHeight;images.current.delete(key);
        }
        invalidate.current(timeRef.current);
      };
      element.src=getMediaUrl(url); images.current.set(url,element);
      if(images.current.size>220) images.current.delete(images.current.keys().next().value!);
    }else{images.current.delete(url);images.current.set(url,element);}
    return element.complete && element.naturalWidth>0 ? element : null;
  },[invalidate,timeRef]);
  const captionPlan=useMemo(()=>({subtitles:plan.subtitles,aspect_ratio:plan.aspect_ratio}),[plan.subtitles,plan.aspect_ratio]);
  const titlePlan=useMemo(()=>({cinematic_texts:plan.cinematic_texts,aspect_ratio:plan.aspect_ratio}),[plan.cinematic_texts,plan.aspect_ratio]);
  const mattePlan=useMemo(()=>({clips:plan.clips,cinematic_texts:plan.cinematic_texts,visual_inserts:plan.visual_inserts,
    aspect_ratio:plan.aspect_ratio,fit_mode:plan.fit_mode}),[plan.clips,plan.cinematic_texts,plan.visual_inserts,plan.aspect_ratio,plan.fit_mode]);
  useEffect(()=>{
    const abort=new AbortController();captions.current=[];
    if(captionPlan.subtitles?.length) {
      creativeRequest<Array<{start_time:number;end_time:number;url:string}>>('/cinematic/captions',captionPlan,abort.signal).then(events=>{
        if(abort.signal.aborted)return;
        captions.current=events;events.slice(0,12).forEach(event=>image(event.url));invalidate.current(timeRef.current);
      }).catch(error=>{if(!abort.signal.aborted)onWarning(error.message);});
    }
    return()=>abort.abort();
  },[captionPlan,image,invalidate,timeRef,onWarning]);
  useEffect(()=>{
    const abort=new AbortController();titles.current.clear();
    if(titlePlan.cinematic_texts?.length)creativeRequest<Array<{id:string;frames:string[]}>>('/cinematic/titles',titlePlan,abort.signal).then(results=>{
      if(abort.signal.aborted)return;
      for(const result of results){titles.current.set(result.id,result.frames);new Set(result.frames).forEach(url=>image(url));}
      invalidate.current(timeRef.current);
    }).catch(error=>{if(!abort.signal.aborted)onWarning(error.message);});
    return()=>abort.abort();
  },[titlePlan,image,invalidate,timeRef,onWarning]);
  useEffect(()=>{
    const abort=new AbortController();mattes.current.clear();
    const required=new Set((mattePlan.cinematic_texts||[]).filter(t=>t.behind_subject).map(t=>t.source_clip_id));
    for(const insert of mattePlan.visual_inserts||[])if(insert.mode==='background'){
      const clip=mattePlan.clips.find(c=>c.start_time<=insert.start_time && insert.start_time<c.start_time+c.duration);if(clip)required.add(clip.id);
    }
    required.forEach(clipId=>{
      creativeRequest<Matte>('/cinematic/matte',{plan:mattePlan,clip_id:clipId},abort.signal).then(matte=>{
        if(abort.signal.aborted)return;
        mattes.current.set(clipId,matte);invalidate.current(timeRef.current);
      }).catch(error=>{if(!abort.signal.aborted)onWarning(error.message);});
    });
    return()=>abort.abort();
  },[mattePlan,invalidate,timeRef,onWarning]);
  useEffect(()=>{
    sources.current.forEach(source=>{try{source.stop();}catch{/* already ended */}}); sources.current=[];
    if(!isPlaying || plan.list_sounds===false) return;
    let active=true;
    const context=audioContext.current ||= new AudioContext();
    void context.resume();
    const origin=context.currentTime-timeRef.current;
    let last=-1;
    for(const cue of [...(plan.sound_cues||[])].sort((a,b)=>a.start_time-b.start_time)) {
      if(cue.muted || cue.volume<=0 || cue.start_time<timeRef.current-.01 || cue.start_time>=plan.duration_seconds || cue.start_time-last<.18)continue;
      last=cue.start_time;
      let buffer=sounds.current.get(cue.sound);
      if(!buffer){buffer=fetch(getMediaUrl(`/api/sounds/${cue.sound}.wav`)).then(r=>r.arrayBuffer()).then(b=>context.decodeAudioData(b));sounds.current.set(cue.sound,buffer);}
      buffer.then(decoded=>{
        if(!active || context.currentTime>origin+cue.start_time+.1)return;
        const source=context.createBufferSource(), gain=context.createGain();source.buffer=decoded;gain.gain.value=cue.volume;
        source.connect(gain).connect(context.destination);sources.current.push(source);source.start(Math.max(context.currentTime,origin+cue.start_time));
      }).catch(()=>onWarning('Click preview audio is unavailable.'));
    }
    return()=>{active=false;sources.current.forEach(s=>{try{s.stop();}catch{/* ended */}});sources.current=[];};
  },[isPlaying,seekVersion,plan.sound_cues,plan.list_sounds,plan.duration_seconds,timeRef,onWarning]);
  useEffect(()=>()=>{
    videos.current.forEach(v=>{v.pause();v.removeAttribute('src');v.load();});
    void audioContext.current?.close();
  },[]);
  useEffect(()=>{if(!isPlaying)videos.current.forEach(v=>v.pause());},[isPlaying]);
  return (ctx:CanvasRenderingContext2D,time:number,width:number,height:number)=>{
    const activeIds=new Set<string>();
    for(const ins of plan.visual_inserts||[]) {
      if(time<ins.start_time || time>=ins.start_time+ins.duration)continue;
      activeIds.add(ins.id);
      let source:HTMLImageElement|HTMLVideoElement|null=null;
      let sw=0,sh=0;
      if(ins.media_type==='video' || /\.(mp4|mov|webm|mkv)(?:\?|$)/i.test(ins.asset_url)){
        let video=videos.current.get(ins.id);
        if(!video || video.dataset.asset!==ins.asset_url){
          video?.pause();video=document.createElement('video');video.muted=true;video.playsInline=true;video.preload='auto';
          video.dataset.asset=ins.asset_url;video.src=getMediaUrl(ins.asset_url);
          video.onloadeddata=video.onseeked=()=>invalidate.current(timeRef.current);videos.current.set(ins.id,video);
        }
        const target=(ins.source_start||0)+time-ins.start_time;
        if(video.readyState>=1 && Math.abs(video.currentTime-target)>(isPlaying?.08:.015) && !video.seeking)video.currentTime=target;
        if(isPlaying && video.paused && video.readyState>=2)void video.play().catch(()=>{});
        if(video.readyState>=2){source=video;sw=video.videoWidth;sh=video.videoHeight;}
      }else{source=image(ins.asset_url);if(source){sw=source.naturalWidth;sh=source.naturalHeight;}}
      if(!source || !sw || !sh)continue;
      if(ins.mode==='background'){
        const clip=plan.clips.find(c=>c.start_time<=time && time<c.start_time+c.duration);
        const matte=clip&&mattes.current.get(clip.id);if(!clip||!matte)continue;
        const frame=Math.min(matte.frames-1,Math.max(0,Math.floor((time-clip.start_time)*matte.fps)));
        const mask=image(`/api/cinematic/masks/${matte.key}/${frame}.png?alpha=true`);if(!mask)continue;
        const temporary=splitCanvas.current ||= document.createElement('canvas');temporary.width=width;temporary.height=height;
        const paint=temporary.getContext('2d')!;paint.drawImage(ctx.canvas,0,0);paint.globalCompositeOperation='destination-in';paint.drawImage(mask,0,0,width,height);
        drawCover(ctx,source,sw,sh,0,0,width,height);ctx.drawImage(temporary,0,0);continue;
      }
      if(ins.mode==='split'){
        const temporary=splitCanvas.current ||= document.createElement('canvas');temporary.width=width;temporary.height=height;
        const copy=temporary.getContext('2d')!;copy.drawImage(ctx.canvas,0,0);ctx.fillStyle='black';ctx.fillRect(0,0,width/2,height);
        const scaledH=height/2;ctx.drawImage(temporary,0,(height-scaledH)/2,width/2,scaledH);
      }
      const [x,y,w,h]=insertRect(ins);
      drawCover(ctx,source,sw,sh,Math.round(x*width),Math.round(y*height),Math.round(w*width),Math.round(h*height));
    }
    videos.current.forEach((video,id)=>{if(!activeIds.has(id))video.pause();});
    for(const title of plan.cinematic_texts||[]){
      if(time<title.start_time || time>=title.start_time+title.duration)continue;
      const frames=titles.current.get(title.id);if(!frames)continue;
      const frameIndex=Math.max(0,Math.min(frames.length-1,Math.floor(time*30+1e-6)-Math.round(title.start_time*30)));
      const url=frames[frameIndex];
      const raster=image(url);if(!raster)continue;
      const layer=titleCanvas.current ||= document.createElement('canvas');layer.width=width;layer.height=height;
      const paint=layer.getContext('2d')!;paint.drawImage(raster,0,0,width,height);
      if(title.behind_subject){
        const clip=plan.clips.find(c=>c.id===title.source_clip_id), matte=mattes.current.get(title.source_clip_id);
        if(!clip || !matte || time<clip.start_time || time>=clip.start_time+clip.duration)continue;
        const frame=Math.min(matte.frames-1,Math.max(0,Math.floor((time-clip.start_time)*matte.fps)));
        const mask=image(`/api/cinematic/masks/${matte.key}/${frame}.png?alpha=true`);
        // Do not substitute unmasked text while a frame is loading.
        if(!mask)continue;
        for(let next=frame+1;next<Math.min(frame+8,matte.frames);next++)image(`/api/cinematic/masks/${matte.key}/${next}.png?alpha=true`);
        const maskLayer=maskCanvas.current ||= document.createElement('canvas');maskLayer.width=width;maskLayer.height=height;
        const maskPaint=maskLayer.getContext('2d')!;maskPaint.drawImage(mask,0,0,width,height);
        for(const insert of plan.visual_inserts||[]){
          if(time<insert.start_time||time>=insert.start_time+insert.duration||insert.mode==='background')continue;
          if(insert.mode==='split'){
            maskPaint.clearRect(0,0,width,height);maskPaint.drawImage(mask,0,height/4,width/2,height/2);
          }else{const [x,y,w,h]=insertRect(insert);maskPaint.clearRect(x*width,y*height,w*width,h*height);}
        }
        paint.globalCompositeOperation='destination-out';paint.drawImage(maskLayer,0,0,width,height);
      }
      ctx.drawImage(layer,0,0);
    }
    for(const [index,caption] of captions.current.entries()){
      if(time>=caption.start_time && time<caption.end_time){const raster=image(caption.url);if(raster)ctx.drawImage(raster,0,0,width,height);}
      if(time>=caption.start_time && time<caption.end_time)captions.current.slice(index+1,index+5).forEach(next=>image(next.url));
    }
  };
}
