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
      <label>Size<input aria-label="Caption font size" className={field} type="number" min={10} max={300} value={style.font_size} onChange={e=>update({font_size:Math.max(10,Math.min(300,Number(e.target.value)))})}/></label>
      <label>Weight<select aria-label="Caption weight" className={field} value={style.font_weight??700} onChange={e=>update({font_weight:Number(e.target.value)})}><option value={400}>Regular</option><option value={700}>Bold</option></select></label>
      <label>Tracking<input aria-label="Caption tracking" className={field} type="number" min={-2} max={15} step={.5} value={style.tracking??0} onChange={e=>update({tracking:Math.max(-2,Math.min(15,Number(e.target.value)))})}/></label>
      <label>Phrase characters<input aria-label="Caption phrase length" className={field} type="number" min={10} max={100} value={style.max_chars??38} onChange={e=>update({max_chars:Math.max(10,Math.min(100,Number(e.target.value)))})}/></label>
      <label>Phrase seconds<input aria-label="Caption phrase duration" className={field} type="number" min={.5} max={15} step={.5} value={style.max_duration??4} onChange={e=>update({max_duration:Math.max(.5,Math.min(15,Number(e.target.value)))})}/></label>
      <label>Color<input aria-label="Caption color" className={field} type="color" value={style.color} onChange={e=>update({color:e.target.value})}/></label>
      <label>Emphasis<input aria-label="Caption emphasis color" className={field} type="color" value={style.highlight_color} onChange={e=>update({highlight_color:e.target.value})}/></label>
    </div>
    <label>Position<select aria-label="Caption position" className={field} value={style.position} onChange={e=>update({position:e.target.value as SubtitleStyle['position']})}><option value="center_bottom">Lower</option><option value="middle">Center</option><option value="top">Upper</option></select></label>
    <label className="flex gap-2"><input type="checkbox" checked={style.highlight_active??false} onChange={e=>update({highlight_active:e.target.checked})}/>Highlight the spoken word in phrases</label>
    <p className="text-zinc-500">Phrase splits and spoken-word highlighting use recorded word timings. Captions without them retain their full segment timing.</p>
  </fieldset>;
}
