import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
const require = createRequire(new URL('../frontend/package.json', import.meta.url));
const ts = require('typescript');
async function moduleUrl(path, replacements={}) {
  let code = ts.transpileModule(await readFile(new URL(path, import.meta.url),'utf8'), {compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
  for (const [from,to] of Object.entries(replacements)) code=code.replaceAll(from,to);
  return 'data:text/javascript;base64,'+Buffer.from(code).toString('base64');
}
const devanagari=await moduleUrl('../frontend/src/utils/captionEngine/devanagari.ts');
const kannada=await moduleUrl('../frontend/src/utils/captionEngine/kannada.ts');
const {romanizeText,romanizeCaptions}=await import(await moduleUrl('../frontend/src/utils/romanizeCaptions.ts',{'./captionEngine/devanagari':devanagari,'./captionEngine/kannada':kannada}));
const {mergeSourceCaptions,attachTranscript}=await import(await moduleUrl('../frontend/src/utils/subtitles.ts'));

test('Offline scripts protect English, punctuation and unsupported languages',()=>{
  assert.equal(romanizeText('आज meeting बहुत important है।'), 'aaj meeting bahut important hai.');
  assert.equal(romanizeText('ಇದು ಒಂದು ಪುಸ್ತಕ'), 'idu ondu pustaka');
  assert.equal(romanizeText('Hello Telugu తెలుగు 42!'), 'Hello Telugu తెలుగు 42!');
  assert.equal(romanizeText('Helloआज!'), 'Helloaaj!');
});

test('Romanization preserves word timings and input for undo',()=>{
  const captions=[{id:'s',text:'आज meeting',start_time:0,end_time:2,words:[{word:'आज',start:.1,end:.4},{word:'meeting',start:.5,end:1}]}];
  const output=romanizeCaptions(captions);
  assert.equal(output[0].text,'aaj meeting');
  assert.equal(output[0].words[0].start,.1);
  assert.equal(output[0].origin,'manual');
  assert.equal(captions[0].text,'आज meeting');
});

test('Regeneration protects corrections and other sources while refreshing generated cues',()=>{
  const manual={id:'m',text:'Correction',start_time:1,end_time:2,origin:'manual',source_filename:'a.mp4'};
  const other={id:'b',text:'Other source',start_time:3,end_time:4,origin:'auto',source_filename:'b.mp4'};
  const stale={id:'old',text:'Old generated',start_time:0,end_time:1,origin:'auto',source_filename:'a.mp4'};
  const fresh={id:'new',text:'Hello again',start_time:0,end_time:2.5,origin:'auto',source_filename:'a.mp4',words:[{word:'Hello',start:0,end:.8},{word:'again',start:2,end:2.5}]};
  const output=mergeSourceCaptions({subtitles:[stale,manual,other]},[fresh],'a.mp4');
  assert.deepEqual(output.map(s=>s.text),['Hello','Correction','again','Other source']);
  assert.equal(output[1],manual);
  assert.equal(attachTranscript([fresh],{clips:[],duration_seconds:4},'a.mp4').length,0);
});
