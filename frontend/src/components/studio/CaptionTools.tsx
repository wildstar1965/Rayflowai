import { useRef, useState } from 'react';
import type { CaptionFormat, EditingPlan, SubtitleSegment } from '../../types';
import { creativeRequest, downloadCaptions } from '../../services/api';
import { attachTranscript, mergeSourceCaptions } from '../../utils/subtitles';
import { romanizeCaptions } from '../../utils/romanizeCaptions';
import { regroupCaptions } from '../../utils/smartCaptions';

export function CaptionTools({plan, source, onChange}: {
  plan: EditingPlan; source?: string; onChange: (plan: EditingPlan) => void;
}) {
  const [format, setFormat] = useState<CaptionFormat>('srt');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [useRoman, setUseRoman] = useState(false);
  const current = useRef(plan);
  current.current = plan;
  const input = useRef<HTMLInputElement>(null);
  const control = 'rounded border border-studio-border bg-studio-panel px-2 py-1.5 text-xs';

  const importFile = async (file?: File) => {
    if (!file) return;
    setBusy(true); setMessage('');
    const before = current.current;
    try {
      if (file.size > 10 * 1024 * 1024) throw new Error('Caption JSON must be smaller than 10 MB.');
      const data = JSON.parse(await file.text());
      let updated: EditingPlan;
      if (data.format === 'rayflow-captions-v1') {
        const document = await creativeRequest<{subtitles: SubtitleSegment[]}>('/captions/validate', {
          ...data, duration_seconds: before.duration_seconds,
        });
        updated = {...before, subtitles: document.subtitles};
      } else {
        if (!source) throw new Error('Choose the uploaded speech source before importing a Caption Engine transcript.');
        const result = await creativeRequest<{subtitles: SubtitleSegment[]; source_fingerprint: string}>('/captions/import', {
          transcript: data, media_filename: source, use_roman: useRoman,
        });
        const mapped = attachTranscript(result.subtitles, before, source);
        if (!mapped.length) throw new Error('This transcript has no speech inside the selected source’s timeline range.');
        updated = {...before, subtitles: mergeSourceCaptions(before, mapped, source),
          transcript: mapped, source_filename: source, source_fingerprint: result.source_fingerprint, transcript_model: undefined};
      }
      if (current.current !== before) throw new Error('The project changed during import. Import again to keep your latest edits.');
      onChange(updated);
      setMessage('Captions imported. Undo restores the previous captions.');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Caption import failed.');
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
    }
  };

  return <div className="space-y-2 text-xs text-studio-text">
    <div className="flex flex-wrap gap-2">
      <select aria-label="Subtitle export format" className={control} value={format} onChange={e => setFormat(e.target.value as CaptionFormat)}>
        <option value="srt">SRT</option><option value="vtt">WebVTT</option><option value="ass">ASS (styled)</option><option value="json">Editable JSON</option>
      </select>
      <button className={control} disabled={busy || !plan.subtitles?.length} onClick={async () => {
        setBusy(true); setMessage('');
        try { await downloadCaptions(current.current, format); setMessage('Caption download ready.'); }
        catch (error) { setMessage(error instanceof Error ? error.message : 'Download failed.'); }
        finally { setBusy(false); }
      }}>Download captions</button>
    </div>
    <div className="flex flex-wrap gap-2">
      <input ref={input} aria-label="Import caption JSON" type="file" accept=".json,application/json" className="hidden" onChange={e => void importFile(e.target.files?.[0])} />
      <button className={control} disabled={busy} onClick={() => input.current?.click()}>Import caption JSON</button>
      <button className={control} disabled={busy || !plan.subtitles?.length} onClick={() => {
        const subtitles = romanizeCaptions(plan.subtitles || []);
        const count = subtitles.filter((s,i) => s !== plan.subtitles?.[i]).length;
        if (count) onChange({...plan, subtitles});
        setMessage(count ? `Converted ${count} captions to Roman letters. Undo restores native text.` : 'No Devanagari or Kannada text found.');
      }}>Romanize captions</button>
      <button className={control} disabled={busy || !plan.subtitles?.length} onClick={() => {
        try { const subtitles = regroupCaptions(plan.subtitles || []); onChange({ ...plan, subtitles }); setMessage(`Created ${subtitles.length} timed phrases. Undo restores the previous captions.`); }
        catch (error) { setMessage(error instanceof Error ? error.message : 'Could not group captions.'); }
      }}>Smart phrases</button>
    </div>
    <label className="flex gap-2"><input type="checkbox" checked={useRoman} onChange={e => setUseRoman(e.target.checked)} />Use saved Roman text when importing a Caption Engine transcript</label>
    <p className="text-studio-muted">Romanization supports Devanagari and Kannada with offline rules; review spellings. English and other scripts stay as written.</p>
    <p className="text-studio-muted">Caption Engine JSON follows the selected source. Rayflow JSON replaces the caption track and can be undone. SRT/VTT carry text and timing; MP4 keeps the preview styling.</p>
    <p role="status" aria-live="polite">{busy ? 'Working on captions…' : message}</p>
  </div>;
}
