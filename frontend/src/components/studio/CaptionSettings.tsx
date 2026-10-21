import { NumericInput } from '../ui/NumericInput';
import type { EditingPlan, SubtitleStyle } from '../../types';

export function CaptionSettings({plan,onChange}:{plan:EditingPlan;onChange:(plan:EditingPlan)=>void}) {
  if(!plan.subtitles?.length)return null;
  const defaults:SubtitleStyle={preset:'bold_pop',font_size:42,font_family:'Arial',color:'#FFFFFF',highlight_color:'#FACC15',stroke_color:'#000000',stroke_width:3,position:'center_bottom'};
  const style={...defaults,...plan.subtitles[0].style};
  const update=(patch:Partial<SubtitleStyle>)=>onChange({...plan,subtitles:plan.subtitles?.map(s=>({...s,style:{...defaults,...s.style,...patch},
    words:patch.highlight_color?s.words?.map(w=>({...w,color:undefined})):s.words}))});
  const field='w-full rounded border border-zinc-300 bg-white p-1 text-xs';
  return <fieldset className="space-y-2 text-xs text-zinc-700"><legend className="font-semibold mb-2">Caption appearance</legend>
    <div className="grid grid-cols-2 gap-2">
      <label>Font<select aria-label="Caption font" className={field} value={style.font_family} onChange={e=>update({font_family:e.target.value})}>
        <option value="Arial">Arial</option><option value="Anton">Anton</option><option value="DejaVu Sans">DejaVu Sans</option><option value="Inter, sans-serif">System sans</option><option value="Trebuchet MS">Trebuchet</option>
      </select></label>
      <label>Size<NumericInput aria-label="Caption font size" className={field} min={10} max={300} value={style.font_size} onCommit={font_size => update({font_size})}/></label>
      <label>Weight<select aria-label="Caption weight" className={field} value={style.font_weight??700} onChange={e=>update({font_weight:Number(e.target.value)})}><option value={400}>Regular</option><option value={700}>Bold</option></select></label>
      <label>Tracking<NumericInput aria-label="Caption tracking" className={field} min={-2} max={15} step={.5} value={style.tracking??0} onCommit={tracking => update({tracking})}/></label>
      <label>Phrase characters<NumericInput aria-label="Caption phrase length" className={field} min={10} max={100} value={style.max_chars??38} onCommit={max_chars => update({max_chars})}/></label>
      <label>Phrase seconds<NumericInput aria-label="Caption phrase duration" className={field} min={.5} max={15} step={.5} value={style.max_duration??4} onCommit={max_duration => update({max_duration})}/></label>
      <label>Color<input aria-label="Caption color" className={field} type="color" value={style.color} onChange={e=>update({color:e.target.value})}/></label>
      <label>Emphasis<input aria-label="Caption emphasis color" className={field} type="color" value={style.highlight_color} onChange={e=>update({highlight_color:e.target.value})}/></label>
    </div>
    <label>Backdrop (%)<NumericInput aria-label="Caption backdrop opacity" className={field} min={0} max={100}
      value={Math.round((style.background_opacity??0)*100)} onCommit={value=>update({background_opacity:value/100})}/></label>
    <label className="flex gap-2"><input type="checkbox" checked={style.safe_area??false} onChange={e=>update({safe_area:e.target.checked})}/>Raise lower captions into the platform-safe area</label>
    <label>Position<select aria-label="Caption position" className={field} value={style.position} onChange={e=>update({position:e.target.value as SubtitleStyle['position']})}><option value="center_bottom">Lower</option><option value="middle">Center</option><option value="top">Upper</option></select></label>
    <label className="flex gap-2"><input type="checkbox" checked={style.highlight_active??false} onChange={e=>update({highlight_active:e.target.checked})}/>Highlight the spoken word in phrases</label>
    <p className="text-zinc-500">Phrase splits and spoken-word highlighting use recorded word timings. Captions without them retain their full segment timing.</p>
  </fieldset>;
}
