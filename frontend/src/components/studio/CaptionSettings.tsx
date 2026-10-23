import { NumericInput } from '../ui/NumericInput';
import type { EditingPlan, SubtitleStyle } from '../../types';

export function CaptionSettings({plan,onChange}:{plan:EditingPlan;onChange:(plan:EditingPlan)=>void}) {
  if(!plan.subtitles?.length)return null;
  const defaults:SubtitleStyle={preset:'bold_pop',caption_mode:'phrase',font_size:72,font_family:'Noto Sans',font_weight:700,tracking:0,color:'#FFFFFF',highlight_color:'#FFD400',stroke_color:'#000000',stroke_width:6,position:'center_bottom',alignment:'center',highlight_active:true,safe_area:true,max_chars:22,max_words:4,max_duration:4,gap_break:.45,min_duration:.4,active_scale:1.08,background_color:'#08080A',background_opacity:0};
  const style={...defaults,...plan.subtitles[0].style};
  const update=(patch:Partial<SubtitleStyle>)=>onChange({...plan,subtitles:plan.subtitles?.map(s=>({...s,style:{...defaults,...s.style,...patch},
    words:patch.highlight_color?s.words?.map(w=>({...w,color:undefined})):s.words}))});
  const field='w-full rounded border border-studio-border bg-studio-panel p-1 text-xs';
  return <fieldset className="space-y-2 text-xs text-studio-text"><legend className="font-semibold mb-2">Caption appearance</legend>
    <button type="button" className="rounded border border-studio-border px-2 py-1" onClick={()=>update(defaults)}>Apply Caption Engine style</button>
    <div className="grid grid-cols-2 gap-2">
      <label>Font<select aria-label="Caption font" className={field} value={style.font_family} onChange={e=>update({font_family:e.target.value})}>
        <option value="Arial">Arial</option><option value="Anton">Anton</option><option value="DejaVu Sans">DejaVu Sans</option><option value="Inter, sans-serif">System sans</option><option value="Trebuchet MS">Trebuchet</option>
        <option value="Noto Sans">Noto Sans (multilingual)</option>
      </select></label>
      <label>Size<NumericInput aria-label="Caption font size" className={field} min={10} max={300} value={style.font_size} onCommit={font_size => update({font_size})}/></label>
      <label>Weight<select aria-label="Caption weight" className={field} value={style.font_weight??700} onChange={e=>update({font_weight:Number(e.target.value)})}><option value={400}>Regular</option><option value={700}>Bold</option></select></label>
      <label>Active word size (%)<NumericInput aria-label="Caption active word scale" className={field} min={100} max={130} value={Math.round((style.active_scale??1.08)*100)} onCommit={value=>update({active_scale:value/100})}/></label>
      <label>Tracking<NumericInput aria-label="Caption tracking" className={field} min={-2} max={15} step={.5} value={style.tracking??0} onCommit={tracking => update({tracking})}/></label>
      <label>Characters per phrase<NumericInput aria-label="Caption phrase length" className={field} min={10} max={100} value={style.max_chars??22} onCommit={max_chars => update({max_chars})}/></label>
      <label>Seconds per phrase<NumericInput aria-label="Caption phrase duration" className={field} min={.5} max={15} step={.5} value={style.max_duration??4} onCommit={max_duration => update({max_duration})}/></label>
      <label>Words per phrase<NumericInput aria-label="Caption word limit" className={field} min={1} max={30} value={style.max_words??4} onCommit={max_words => update({max_words})}/></label>
      <label>Pause break (s)<NumericInput aria-label="Caption pause break" className={field} min={.1} max={3} step={.05} value={style.gap_break??.45} onCommit={gap_break => update({gap_break})}/></label>
      <label>Color<input aria-label="Caption color" className={field} type="color" value={style.color} onChange={e=>update({color:e.target.value})}/></label>
      <label>Emphasis<input aria-label="Caption emphasis color" className={field} type="color" value={style.highlight_color} onChange={e=>update({highlight_color:e.target.value})}/></label>
      <label>Outline<input aria-label="Caption outline color" className={field} type="color" value={style.stroke_color} onChange={e=>update({stroke_color:e.target.value})}/></label>
      <label>Outline width<NumericInput aria-label="Caption outline width" className={field} min={0} max={20} value={style.stroke_width} onCommit={stroke_width => update({stroke_width})}/></label>
      <label>Background<input aria-label="Caption background color" className={field} type="color" value={style.background_color??'#08080A'} onChange={e=>update({background_color:e.target.value})}/></label>
      <label>Alignment<select aria-label="Caption alignment" className={field} value={style.alignment??'center'} onChange={e=>update({alignment:e.target.value as SubtitleStyle['alignment']})}><option value="left">Left</option><option value="center">Center</option><option value="right">Right</option></select></label>
    </div>
    <label>Backdrop (%)<NumericInput aria-label="Caption backdrop opacity" className={field} min={0} max={100}
      value={Math.round((style.background_opacity??0)*100)} onCommit={value=>update({background_opacity:value/100})}/></label>
    <label className="flex gap-2"><input type="checkbox" checked={style.safe_area??false} onChange={e=>update({safe_area:e.target.checked})}/>Raise lower captions into the platform-safe area</label>
    <label>Position<select aria-label="Caption position" className={field} value={style.position} onChange={e=>update({position:e.target.value as SubtitleStyle['position']})}><option value="center_bottom">Lower</option><option value="middle">Center</option><option value="top">Upper</option></select></label>
    <label className="flex gap-2"><input type="checkbox" checked={style.highlight_active??false} onChange={e=>update({highlight_active:e.target.checked})}/>Highlight the spoken word in phrases</label>
    <p className="text-studio-muted">Text and outlines scale together with the video height. Active words grow in a reserved space, keeping the phrase steady. Without word timings, captions retain phrase timing.</p>
    <p className="text-studio-muted">Indic scripts use bundled Noto fonts. Tracking is disabled for them to preserve joined letters.</p>
  </fieldset>;
}
