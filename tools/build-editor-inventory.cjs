// Regenerate the migration index from real source declarations, not workspace screenshots.
const fs = require('node:fs');
const path = require('node:path');
const ts = require('../frontend/node_modules/typescript');
const root = path.resolve(__dirname, '..');
const editor = path.join(root, 'frontend/src/features/ai-editor');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'docs/ai-editor-source-manifest.json'), 'utf8'));
const relative = file => path.relative(root, file).replaceAll('\\', '/');
const files = [];
function walk(folder) { for (const entry of fs.readdirSync(folder, { withFileTypes: true })) {
  const file = path.join(folder, entry.name);
  if (entry.isDirectory()) walk(file); else if (/\.tsx?$/.test(file) && !/\.test\.tsx?$/.test(file)) files.push(file);
} }
walk(editor);
const native = /(?:midjourneyAgentService|localAgentsService)/;
const adapters = {
  gemini: 'runtime/google.ts → /api/editor/jobs → Node Google SDK',
  notebook: 'NotebookLM HTTP MCP → /api/editor/jobs → backend/app/editor/mcp.py',
  cloud: 'Encrypted backend OAuth → backend/app/editor/cloud.py',
  audio: 'runtime/audio.ts → Python mastering/remastering jobs',
  surface: 'runtime/processors.ts → CPU normal maps or operator Depth Anything V2',
  corridor: 'runtime/processors.ts → operator CorridorKey runtime',
  project: 'runtime/project.ts → versioned owned project records and private Storage',
  collaborative: 'runtime/collaboration.ts → durable authenticated Yjs relay',
  realtime: 'backend/app/editor/collaboration.py → authenticated presence and events',
  studioauth: 'backend/app/editor/accounts.py → verified email-code account attachment',
};
const entries = [];
const workspaceMapping = {
  ProjectHub: ['Project / production workflow', 'Plain-text script import/edit, Scene Wall creation, save/reload pass browser checks. Formats, bible, creative direction, concepts, casting, storyboard, filming, continuity and marketing retained; remaining actions and generation unverified live.'],
  Script: ['Project / Script', 'Upstream redirect retained as an Open Project workflow action. No separate script editor is claimed.'],
  SceneWall: ['Project / Scene Wall phase', 'Activate from Project, create scene cards from imported script sluglines, save/reload verified. Reel ordering, concepts/VFX and generation workflows still pending.'],
  Microdrama: ['Project / Microdrama', 'Vertical episodic planning and generation. Source imported; per-action browser/live tests pending.'],
  Import: ['Create / Import and shared Assets', 'Browser upload/relink adapters. Real shared image/audio uploads exercised through Assets/Studio; document-format UI paths pending.'],
  AssetLibrary: ['Project / Library and shared Assets', 'Reusable assets, packs, stock and generated media. Shared image insertion/reload verified; stock/provider searches and every pack action pending.'],
  Moodboard: ['Project / Moodboard', 'Board creation, note entry/reopening, save and reload pass browser checks. Connectors, research image sources and other board actions not individually verified.'],
  NotebookLM: ['Project / Research', 'Research sources, knowledge graph, Brave and optional HTTP MCP. MCP protocol mocked; live service/search/graph UI pending.'],
  Design: ['Create / Design', 'Title template -> real PNG -> timeline -> private stored media and reload pass browser checks. Other canvas/generation tools pending.'],
  Photo: ['Edit / Photo', 'Image/mask/sketch tools imported. Provider operations and complete canvas gestures unverified.'],
  Outfit: ['Create / Outfit', 'Wardrobe, garments and variants imported and navigation restored. Generation/live verification pending.'],
  Avatar: ['Create / Avatar', 'Avatar/character references and generation settings imported. Provider/live verification pending.'],
  ImageGeneration: ['Create / Images', 'Catalogs, auto selection, references and generation queue adapted to jobs. Catalog unit tests and transport contracts; live generations pending.'],
  VideoGeneration: ['Create / Video', 'Start/end frames, reference uploads, motion, queue and cancellation adapters. Model-choice tests; per-model live generation pending.'],
  Node: ['Create / Nodes', 'Prompt edit, node insertion, immediate workspace switch, save/reload pass browser checks. Graph execution/provider chains pending. Empty graph restoration preserved.'],
  SetDesign: ['Create / Set Design', 'Add/select/rename/position/recolor a box, capture a real 1920x1080 PNG with the colored object, private save and reload pass browser checks. Model imports, lighting/animation and Blender handoff still need acceptance.'],
  SceneMap: ['Create / Scene Map', 'Add/rename/drag actor, add camera, switch 3D view, camera/reset controls, second scene/light and reload pass browser checks. Other gestures/reference links remain unverified.'],
  WorldGeneration: ['Create / World', 'World generation/reference/catalog and available asset previews/exports retained. Upstream world-mesh conversion remains unavailable. Live World Labs pending.'],
  Edit: ['Edit / Timeline (default #/editor)', 'Shared media, clip insertion, undo/redo, reload, responsive panel tabs and cross-workspace navigation pass. Complete effect/keyframe/shortcut matrix pending.'],
  Trim: ['Edit / Trim', 'Trim and automatic cutting source retained; timeline helper tests. Workspace gestures and paid automatic cutting pending.'],
  Grading: ['Edit / Grading', 'Wheel preset and keyboard edit, .cube download/import, typed LUT save/reload, and real HQ color output pass browser checks. Real 1D/3D LUT and half-strength backend outputs tested. Other controls/scopes/AI colorist need acceptance.'],
  Compositing: ['Edit / Composite', 'Layers, keying, relighting, pose, node compositing imported. Helpers/CPU normal map tested; provider/GPU workflows pending.'],
  Upscale: ['Edit / Upscale', 'Restoration, interpolation and image/video upscaling retained. Transport contracts only; output quality/live provider checks pending.'],
  Sound: ['Create / Sound', 'Voice, music, effects/stems/editing plus backend mastering/remastering. Real local audio processor tests; all provider voice/music/stem paths pending live.'],
  Analysis: ['Review / Analysis', 'Pacing/quality analysis imported. Helper tests; full rendered-media/provider UI checks pending.'],
  Review: ['Review / Review', 'Annotations, feedback, approvals and continuity imported. Review data tests; full collaborative browser workflow pending.'],
  Requests: ['Review / Requests', 'Shot/asset-linked changes and requests retained. Data helpers tested; full UI workflow pending.'],
  Export: ['Delivery / Export', 'Real H.264, 10-bit HEVC/ProRes video/audio/pixels/duration; volume easing and custom LUTs; fresh Design -> HQ MP4 and private Quick WebM, cancellation and immediate retry verified. OTIO/FCPXML/OCIO/VFX generators tested. HDR/native-host imports pending; Quick records video only.'],
  LocalAi: ['Project / Local AI', 'Reachable server connections, catalogs and workflows retained; installation remains operator-only. Mocked transport; no live model-service tests.'],
  Plugins: ['Project / Plugins', 'Catalogs, packs/LUTs/presets and downloadable host assets retained. Native plugin installation/shell actions excluded; every pack/download pending verification.'],
};
const actionEvidence = {
  'DesignWorkspace.tsx:handleExport': 'tests/test_editor_workspaces_browser.py: title-card PNG, real pixels, private storage, timeline and reload.',
  'DesignWorkspace.tsx:applyTemplate': 'tests/test_editor_workspaces_browser.py: Title Card template only.',
  'MoodboardWorkspace.tsx:addNote': 'tests/test_editor_workspaces_browser.py: place note, type, reopen with double-click, save/reload.',
  'MoodboardWorkspace.tsx:handleAddCategory': 'tests/test_editor_workspaces_browser.py: create named board and restore it.',
  'ProjectHubWorkspace.tsx:handleScriptUpload': 'tests/test_editor_workspaces_browser.py: plain-text document import/edit, save/reload. PDF/DOCX/spreadsheet formats not UI-tested.',
  'SceneWallWorkspace.tsx:handleApplyFromStoryBible': 'tests/test_editor_workspaces_browser.py: imported screenplay sluglines become saved scene cards.',
  'SetDesignWorkspace.tsx:handleAddPrimitive': 'tests/test_editor_scene_browser.py: add a box, select/rename/position/recolor and reload.',
  'SetDesignWorkspace.tsx:handleSnapshot': 'tests/test_editor_scene_browser.py: private 1920x1080 PNG decoded and colored object pixels verified.',
  'SceneMapWorkspace.tsx:addElement': 'tests/test_editor_scene_browser.py: actor, camera and light; labels, drag, two scenes and reload.',
  'SceneMapWorkspace.tsx:addScene': 'tests/test_editor_scene_browser.py: independent second scene and reload.',
  'GradingWorkspace.tsx:handleExportCube': 'tests/test_editor_grading_browser.py: wheel preset/keyboard edit -> 33-cube download with complete samples.',
  'GradingWorkspace.tsx:handleImportLut': 'tests/test_editor_grading_browser.py: inverse LUT import/save/reload -> correct decoded MP4 pixels.',
  'ExportWorkspace.tsx:startRender': 'tests/test_editor_export_browser.py: fresh Design title, HQ/Quick output, private downloads, decoded frames and cancel/retry; grading test covers a restored LUT.',
  'ExportWorkspace.tsx:cancelRender': 'tests/test_editor_export_browser.py: real backend cancellation, browser cancellation without saved partial output, immediate retry.',
};
function disposition(file, name, type) {
  const base = path.basename(file).toLowerCase();
  if (base === 'placeholderworkspace.tsx') return { implementation: 'Upstream fallback placeholder, not an implemented workspace', verification: 'No feature completion claimed for fallback UI.' };
  if (native.test(file)) return { implementation: 'accepted native-only limitation', verification: 'Unavailable in hosted runtime; native login and desktop shell are excluded.' };
  const tests = [file.replace(/\.tsx?$/, '.test.ts'), file.replace(/\.tsx?$/, '.test.tsx')].filter(fs.existsSync).map(relative);
  let implementation = 'Active upstream implementation imported into the React module';
  for (const [match, target] of Object.entries(adapters)) if (base.includes(match)) { implementation = target; break; }
  let verification = tests.length ? `Unit-test module: ${tests.join(', ')}. Per-action UI/live coverage is not implied.` : 'Source and migration location indexed; this individual action has not been independently exercised.';
  if (/services/.test(file) && /(?:generate|request|fetch|predict|upload|search)/i.test(name)) verification += ' Live provider/service execution pending configured credentials.';
  if (type === 'workspace') {
    const mapping = workspaceMapping[path.basename(file, 'Workspace.tsx')];
    if (!mapping) throw new Error('Missing workspace disposition: ' + file);
    implementation = mapping[0] + '; native React module, preserving upstream project schema';
    verification = mapping[1];
  }
  if (actionEvidence[path.basename(file) + ':' + name]) verification = actionEvidence[path.basename(file) + ':' + name];
  return { implementation, verification };
}
for (const file of files) {
  const source = fs.readFileSync(file, 'utf8');
  const ast = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true);
  const module = relative(file);
  const seen = new Set();
  function add(name, type, node) {
    const key = type + ':' + name;
    if (seen.has(key)) return;
    seen.add(key);
    entries.push({ source: manifest.find(row => row.destination === module)?.source || 'Rayflow adapter', destination: module,
      line: ast.getLineAndCharacterOfPosition(node.getStart(ast)).line + 1, name, type, ...disposition(file, name, type) });
  }
  if (path.dirname(file) === path.join(editor, 'workspaces') && /Workspace\.tsx$/.test(file)) add(path.basename(file, '.tsx'), 'workspace', ast);
  function visit(node) {
    if ((ts.isFunctionDeclaration(node) || ts.isClassDeclaration(node)) && node.name) add(node.name.text, 'operation', node);
    if (ts.isMethodDeclaration(node) && node.name) add(node.name.getText(ast), 'operation', node);
    if (ts.isPropertyAssignment(node) && (ts.isArrowFunction(node.initializer) || ts.isFunctionExpression(node.initializer))) {
      add(node.name.getText(ast), 'operation', node);
    }
    if (ts.isVariableDeclaration(node) && ts.isIdentifier(node.name) && node.initializer) {
      if (ts.isArrowFunction(node.initializer) || ts.isFunctionExpression(node.initializer)) add(node.name.text, /^(handle|on)/.test(node.name.text) ? 'nested action' : 'operation', node);
    }
    if ((ts.isInterfaceDeclaration(node) || ts.isTypeAliasDeclaration(node)) && /(?:Settings|Config|Options|Preferences|Preset|Request|Parameters)/.test(node.name.text)) {
      const members = node.members || node.type?.members || [];
      for (const member of members) if (member.name) add(node.name.text + '.' + member.name.getText(ast), 'configuration field', member);
    }
    if (ts.isCallExpression(node) && /editorStorage\.(getItem|setItem|removeItem)/.test(node.expression.getText(ast)) && node.arguments[0]) add(node.arguments[0].getText(ast), 'saved preference', node);
    if (ts.isPropertyAssignment(node) && node.name.getText(ast) === 'name' && ts.isStringLiteralLike(node.initializer)) {
      const parent = node.parent.getText(ast);
      if (/parameters:|inputSchema:/.test(parent)) add(node.initializer.text, 'assistant tool', node);
    }
    ts.forEachChild(node, visit);
  }
  visit(ast);
}
const exportFormats = [
  ['Browser recording', 'WebM / browser MediaRecorder codecs', 'workspaces/ExportWorkspace.tsx', 'Real Quick output saved privately, downloaded, decoded for dimensions/duration/visible title; cancellation and retry pass. Video only, as labeled in UI.'],
  ['Backend render', 'MP4 H.264, MP4 HEVC, MOV ProRes; 8/10/12-bit subject to codec', 'workspaces/ExportWorkspace.tsx', 'Real H.264 8-bit, HEVC 10-bit and ProRes 10-bit output decoded for codec, dimensions, duration, audio and pixels. Trim/speed/volume easing and full/half-strength LUT output verified. Cancellation/retry passes. 12-bit/HDR remain unverified.'],
  ['Editorial interchange', 'OpenTimelineIO JSON import/export; FCPXML', 'utils/openTimelineIOExport.ts', 'Imported OTIO roundtrip and FCPXML unit tests pass. External NLE import not tested.'],
  ['Color/VFX handoff', 'OCIO JSON manifests; Nuke .nk; Natron .py; VFX handoff JSON', 'utils/vfxHandoffManifest.ts', 'Imported manifest and script generation tests pass. Native hosts not launched.'],
  ['Color LUT', '1D/3D .cube; wheel grades as 33-cube', 'workspaces/GradingWorkspace.tsx', 'Browser wheel preset/edit/download and LUT import/reload verified. HQ rendered pixels verified at full and half strength. Native NLE imports untested.'],
  ['Production archives', 'ZIP and JSON, embedded media, typed LUT data, shared sequence schemas', 'runtime/project.ts', 'Backend archive/relinking and typed-array unit tests pass. Supabase storage smoke test pending.'],
  ['Storyboard', 'Browser print / PDF', 'runtime/project.ts', 'Browser print adapter present; PDF appearance not yet verified.'],
  ['Design canvas', 'PNG -> media bin/timeline/private project asset', 'workspaces/DesignWorkspace.tsx', 'Real title-card PNG decoded and its pixels/dimensions checked in browser workflow.'],
  ['Set design', 'Blender Python .py handoff; HDRI pack JSON; PNG camera captures', 'workspaces/SetDesignWorkspace.tsx', 'Real 1920x1080 PNG capture, private persistence and colored object pixels verified. Blender execution and hosted model-file relinking, HDRI downloads remain pending.'],
  ['World assets', 'Provider-supplied GLB collider mesh, SPZ splats, panorama and thumbnail', 'workspaces/WorldGenerationWorkspace.tsx', 'Existing output assets can be inserted/downloaded. No implemented world-mesh conversion; live file formats pending.'],
];
const providerModules = [
  ['Gemini', 'geminiService.ts', 'Google SDK content/image/video/audio/files and model discovery'],
  ['Replicate', 'replicateService.ts', 'Predictions, model media processing and uploads'],
  ['fal.ai', 'falAiService.ts', 'Image/video/audio/3D model calls and queued predictions'],
  ['xAI', 'xaiService.ts', 'Image/video and model discovery'],
  ['ElevenLabs', 'elevenLabsService.ts', 'Voices, speech, sound and audio operations'],
  ['Sonauto', 'sonautoService.ts', 'Music generation and status'],
  ['Sonilo', 'soniloService.ts', 'Music/SFX generation and status'],
  ['LTX', 'ltxService.ts', 'Video operations'],
  ['Runway', 'runwayService.ts', 'Video/task operations'],
  ['World Labs', 'worldLabsService.ts', 'World/media-asset generation and operation status'],
  ['Higgsfield', 'higgsfieldService.ts', 'Image/video queue (KEY_ID:KEY_SECRET credential)'],
  ['MachGen', 'machgenService.ts', 'Image/task operations'],
  ['Brave Search', 'braveSearchService.ts', 'Research search'],
  ['Unsplash', 'unsplashService.ts', 'Stock photo search'],
  ['Sketchfab', 'sketchfabService.ts', 'Model search/download'],
  ['OpenRouter', null, 'Existing Rayflow direction/chat; backend/app/llm/openai_compatible.py'],
  ['Pixabay', null, 'Existing Rayflow stock/B-roll; backend/app/services/pixabay.py'],
  ['Ollama / LM Studio / OpenAI-compatible', 'localModelService.ts', 'Operator-configured reachable model endpoints'],
  ['ComfyUI', 'comfyUiService.ts', 'Per-workspace inputs, prompts, history and output grants; audited node allowlist'],
  ['Draw Things', 'drawThingsService.ts', 'Operator-configured reachable image service'],
  ['NotebookLM', 'notebookLMService.ts', 'Operator HTTP MCP URL plus encrypted per-workspace token'],
];
const providers = providerModules.map(([name, file, operations]) => ({ name, operations,
  destination: file && fs.existsSync(path.join(editor, 'services', file)) ? relative(path.join(editor, 'services', file)) : 'See declaration index and backend/app/editor/providers.py',
  implementation: 'Backend credential/transport or SDK adapter; explicit workspace context',
  verification: 'Mocked transport/protocol checks in tests/test_editor_adapters.py and tests/test_editor_optional.py. No live provider execution is claimed; individual operations require credentials and services.' }));
const result = { version: 2, scope: 'Active upstream src and Rayflow adapters. Declaration index is not execution proof.',
  moduleCount: files.length, workspaceCount: entries.filter(row => row.type === 'workspace').length, entries,
  providers,
  exclusions: ['Payment/checkout/subscription screens and restrictions', 'Electron root and desktop shell', 'Midjourney/native agent login automation'],
  placeholders: ['Upstream World Labs world-mesh conversion is unavailable', 'Upstream remote mastering placeholder is replaced only where the working local backend processors apply'],
  exports: exportFormats.map(([name, formats, file, verification]) => ({ name, formats, destination: 'frontend/src/features/ai-editor/' + file, verification })) };
for (const item of result.exports) if (!fs.existsSync(path.join(root, item.destination))) throw new Error('Missing export destination: ' + item.destination);
fs.writeFileSync(path.join(root, 'docs/ai-editor-inventory.json'), JSON.stringify(result, null, 2) + '\n');
const md = ['# AI Editor migration inventory', '',
  'Generated by `node tools/build-editor-inventory.cjs`. Each row identifies an actual declaration and its destination. An indexed implementation does not mean that every UI path, provider model, or deployed service has passed acceptance.', '',
  `Indexed ${result.moduleCount} source modules, ${result.workspaceCount} workspace files, and ${entries.length} workspaces, operations, nested actions, assistant tools, configuration fields, and saved preferences.`, '',
  'Machine-readable details: [ai-editor-inventory.json](ai-editor-inventory.json). Provenance: [ai-editor-source-manifest.json](ai-editor-source-manifest.json). Actual checks and remaining work: [ai-editor-integration.md](ai-editor-integration.md).', '',
  '## Workspace files', '', '| Workspace | Implementation | Verification |', '| --- | --- | --- |'];
for (const item of entries.filter(row => row.type === 'workspace')) md.push(`| [${item.name}](../${item.destination}#L${item.line}) | ${item.implementation} | ${item.verification} |`);
md.push('', '## Export formats', '', '| Operation | Formats | Verification |', '| --- | --- | --- |');
for (const item of result.exports) md.push(`| [${item.name}](../${item.destination}) | ${item.formats} | ${item.verification} |`);
md.push('', '## Provider adapters', '', '| Provider | Operations / destination | Verification |', '| --- | --- | --- |');
for (const item of providers) md.push(`| ${item.name} | ${item.operations}; ${item.destination} | ${item.verification} |`);
md.push('', '## Exclusions and upstream placeholders', '', ...result.exclusions.concat(result.placeholders).map(item => '- ' + item));
md.push('', '## Operations and configuration', '', '| Declaration | Type | Destination | Implementation and verification |', '| --- | --- | --- | --- |');
for (const item of entries.filter(row => row.type !== 'workspace')) {
  const cell = value => String(value).replaceAll('|', '\\|').replaceAll('\n', ' ');
  md.push(`| ${cell(item.name)} | ${item.type} | [Source](../${item.destination}#L${item.line}) | ${cell(item.implementation)}. ${cell(item.verification)} |`);
}
fs.writeFileSync(path.join(root, 'docs/ai-editor-inventory.md'), md.join('\n') + '\n');
console.log(`Indexed ${files.length} modules and ${entries.length} declarations.`);
