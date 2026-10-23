from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / 'frontend/src/features/ai-editor'

(EDITOR / 'components/ApiKeyModal.tsx').write_text('''import React, { useState } from 'react';
import ProviderConnections from '../../../components/ProviderConnections';
import { DEFAULT_SHORTCUTS } from '../utils/shortcuts';
import { WORKSPACE_NAV_GROUPS } from '../config/workspaceNav';

export default function ApiKeyModal(props: any) {
  const [tab, setTab] = useState('providers');
  const startup = props.startupPreferences;
  const autosave = props.autosaveSettings;
  return <div className="rayflow-modal-backdrop"><section className="rayflow-modal" role="dialog" aria-modal="true" aria-labelledby="editor-settings-title">
    <div className="workspace-actions"><h1 id="editor-settings-title">Rayflow settings</h1><button onClick={props.onClose}>Close</button></div>
    <div className="workspace-actions"><button onClick={() => setTab('providers')}>Providers</button><button onClick={() => setTab('preferences')}>Editor preferences</button><button onClick={() => setTab('shortcuts')}>Keyboard shortcuts</button></div>
    {tab === 'providers' && <ProviderConnections />}
    {tab === 'preferences' && <div className="connection-grid">
      {startup && <section><h2>Startup</h2><label>Workspace<select value={startup.startupWorkspace} onChange={e => props.onUpdateStartupPreferences?.({...startup, startupWorkspace:e.target.value})}>{WORKSPACE_NAV_GROUPS.flatMap(group => group.items).map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
        <label><input type="checkbox" checked={startup.autoOpenAssistant} onChange={e => props.onUpdateStartupPreferences?.({...startup,autoOpenAssistant:e.target.checked})} /> Open assistant on startup</label>
        <label>Agent control<select value={startup.studioAgentMode} onChange={e => props.onUpdateStartupPreferences?.({...startup,studioAgentMode:e.target.value})}><option value="agent">Agent</option><option value="manual">Manual</option></select></label>
        <label>Agent approvals<select value={startup.studioAgentApprovalMode} onChange={e => props.onUpdateStartupPreferences?.({...startup,studioAgentApprovalMode:e.target.value})}><option value="important_only">Important actions</option><option value="every_action">Every action</option></select></label></section>}
      {autosave && <section><h2>Save and recovery</h2><label><input type="checkbox" checked={autosave.enabled} onChange={e => props.onUpdateAutosaveSettings?.({...autosave,enabled:e.target.checked})} /> Autosave</label>
        <label>Save delay (seconds)<input type="number" min="1" max="300" value={autosave.debounceMs/1000} onChange={e => props.onUpdateAutosaveSettings?.({...autosave,debounceMs:Math.max(1000,Number(e.target.value)*1000)})}/></label>
        <label>Minimum save interval (seconds)<input type="number" min="1" max="600" value={autosave.minIntervalMs/1000} onChange={e => props.onUpdateAutosaveSettings?.({...autosave,minIntervalMs:Math.max(1000,Number(e.target.value)*1000)})}/></label>
        <label><input type="checkbox" checked={autosave.recoverOnCrash} onChange={e => props.onUpdateAutosaveSettings?.({...autosave,recoverOnCrash:e.target.checked})} /> Offer crash recovery</label></section>}
      <section><h2>Getting started</h2><button onClick={props.onRestartOnboarding}>Open setup guide</button></section>
    </div>}
    {tab === 'shortcuts' && <section>{Object.entries(props.shortcuts || DEFAULT_SHORTCUTS).map(([key,value]) => <label key={key}>{key.replaceAll('_',' ')}<input value={String(value)} onChange={e => props.onUpdateShortcuts?.({...props.shortcuts,[key]:e.target.value})}/></label>)}<button onClick={() => props.onUpdateShortcuts?.({...DEFAULT_SHORTCUTS})}>Reset shortcuts</button></section>}
  </section></div>;
}
''', encoding='utf-8')
(EDITOR / 'components/OnboardingModal.tsx').write_text('''import React from 'react';
import ProviderConnections from '../../../components/ProviderConnections';
export default function OnboardingModal(props: any) {
  if (!props.isOpen) return null;
  return <div className="rayflow-modal-backdrop"><section className="rayflow-modal" role="dialog" aria-modal="true" aria-labelledby="editor-welcome">
    <h1 id="editor-welcome">Your complete production workspace</h1><p>Import media, edit the timeline, or connect a provider to generate scripts, images, video and sound. All workspace groups are available in Pro mode.</p>
    <ProviderConnections quick />
    <div className="workspace-actions"><button onClick={() => props.onComplete(true)}>Start editing</button><button onClick={() => props.onComplete(true)}>Skip setup</button><button onClick={props.onOpenApiSettings}>All settings</button></div>
  </section></div>;
}
''', encoding='utf-8')

path = EDITOR / 'App.tsx'
source = path.read_text(encoding='utf-8')
source = re.sub(r"    const isElectron =\n[\s\S]*?;", '    const isElectron = false;', source, count=1)
source = source.replace("return editorStorage.getItem(ONBOARDING_COMPLETED_KEY) !== 'true';", 'return false;')
source = source.replace("const shouldLoad = window.confirm('An existing project was found in this folder. Load it now?');", 'const shouldLoad = true;')
path.write_text(source, encoding='utf-8')

path = EDITOR / 'config/env.ts'
source = path.read_text(encoding='utf-8')
source = re.sub(r"    brave: \{[\s\S]*?    \},", "    brave: { apiKey: '' },", source)
source = re.sub(r"    isElectron:[\s\S]*?\n\};", '    isElectron: false,\n};', source)
source = source.replace("getEnvVar('VITE_HOCUSPOCUS_TOKEN')", "''")
path.write_text(source, encoding='utf-8')
print('Connected provider UI and preserved editor preferences without payment screens.')
