import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
const require=createRequire(new URL('../frontend/package.json',import.meta.url));
const ts=require('typescript');
const source=await readFile(new URL('../frontend/src/utils/subtitles.ts',import.meta.url),'utf8');
const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext}}).outputText;
const {attachTranscript,editCaptionTiming,newCaptionInterval}=await import('data:text/javascript;base64,'+Buffer.from(compiled).toString('base64'));

test('New manual captions use free intervals inside the project',()=>{
  const plan={duration_seconds:5,subtitles:[{start_time:1,end_time:3}]};
  assert.deepEqual(newCaptionInterval(plan,0),{start_time:0,end_time:1});
  assert.deepEqual(newCaptionInterval(plan,2),{start_time:3,end_time:5});
  assert.deepEqual(newCaptionInterval(plan,4.9),{start_time:4.9,end_time:5});
  assert.equal(newCaptionInterval({duration_seconds:5,subtitles:[{start_time:0,end_time:5}]},2),null);
});

test('Transcript follows trimmed and reordered occurrences of its source',()=>{
  const plan={duration_seconds:8,clips:[{id:'a',image_url:'/api/uploads/a.mp4',media_type:'video',start_time:0,duration:2,source_start:5},
    {id:'b',image_url:'/api/uploads/a.mp4',media_type:'video',start_time:4,duration:3,source_start:4}]};
  const segments=[{id:'s',text:'Hello world.',start_time:4.5,end_time:6,words:[{word:'Hello',start:4.5,end:5},{word:'world.',start:5,end:6}]}];
  const result=attachTranscript(segments,plan,'a.mp4');
  assert.deepEqual(result.map(s=>[s.start_time,s.end_time,s.text,s.source_clip_id]),[[0,1,'world.','a'],[4.5,6,'Hello world.','b']]);
  assert.equal(segments[0].start_time,4.5);
});

test('Caption timing clamps against neighbours and keeps genuine word intervals',()=>{
  const plan={duration_seconds:8,subtitles:[{id:'a',start_time:0,end_time:2},{id:'b',start_time:2,end_time:5,words:[{word:'Hello',start:2,end:4}]},{id:'c',start_time:5,end_time:7}]};
  assert.equal(editCaptionTiming(plan,'b','start_time',1).subtitles[1].start_time,2);
  assert.equal(editCaptionTiming(plan,'b','end_time',7).subtitles[1].end_time,5);
  const edited=editCaptionTiming(plan,'b','start_time',3);
  assert.equal(edited.subtitles[1].words[0].start,3);
  assert.equal(edited.subtitles[1].words[0].end,4);
  assert.equal(plan.subtitles[1].words[0].start,2);
  assert.equal(editCaptionTiming(plan,'b','end_time',NaN),plan);
});
