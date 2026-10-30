import { lazy, Suspense, useEffect, useRef, useState } from 'react';
import LandingPage from './pages/LandingPage';
import StudioPage from './pages/StudioPage';
import SettingsPage from './pages/SettingsPage';
import DashboardPage from './pages/DashboardPage';
import TastePage from './pages/TastePage';
import { checkBackendHealth } from './services/api';
import { initializeWorkspace, getWorkspaceSession, getEditorProviders } from './services/editorClient';
import WorkspaceSetup from './components/WorkspaceSetup';
import ProjectManager from './components/ProjectManager';
import SharedAssets from './components/SharedAssets';
import ModuleBoundary from './components/ModuleBoundary';
import WorkspaceLoading from './components/WorkspaceLoading';
import { saveBeforeWorkspaceChange } from './services/workspaceNavigation';
import './styles/workspace.css';
const EditorWorkspace = lazy(() => import('./features/ai-editor/EditorWorkspace'));

export function App() {
  const [route, setRoute] = useState(() => window.location.hash.slice(1) || '/');
  const routeRef = useRef(route);
  const navigationVersion = useRef(0);
  const [startup, setStartup] = useState<'loading' | 'ready' | 'error'>('loading');
  const [setup, setSetup] = useState(false);
  const [startupError, setStartupError] = useState('');
  const initialize = async () => {
    setStartup('loading'); setStartupError('');
    try {
      if (!await checkBackendHealth()) throw new Error('The video engine could not be reached.');
      const session = await initializeWorkspace();
      setSetup(!session.preferences.setupComplete && !getEditorProviders().some(provider => provider.configured && !provider.local)); setStartup('ready');
    } catch (error) { setStartupError(error instanceof Error ? error.message : 'Workspace startup failed.'); setStartup('error'); }
  };
  useEffect(() => {
    void initialize();
    const change = async () => {
      const version = ++navigationVersion.current;
      const next = window.location.hash.slice(1) || '/';
      if (next.split('/')[1] !== routeRef.current.split('/')[1] && !await saveBeforeWorkspaceChange()) {
        if (version !== navigationVersion.current) return;
        window.history.replaceState(null, '', '#' + routeRef.current); return;
      }
      if (version !== navigationVersion.current) return;
      routeRef.current = next; setRoute(next);
    };
    window.addEventListener('hashchange', change);
    return () => window.removeEventListener('hashchange', change);
  }, []);
  const navigate = (path: string) => { window.location.hash = path; };
  if (startup !== 'ready') return <WorkspaceLoading page message="Preparing your workspace" error={startup === 'error' ? startupError : undefined} onRetry={() => void initialize()}><button onClick={() => setStartup('ready')}>Continue offline</button></WorkspaceLoading>;

  return (
    <div className={`${route.startsWith('/editor') ? 'workspace-shell workspace-shell--editor' : 'min-h-screen'} bg-studio-canvas text-studio-text font-sans`}>
      {route !== '/' && <nav className="workspace-nav" aria-label="Main"><a href="#/">Rayflow AI</a><a href="#/studio">Studio</a><a href="#/editor" aria-current={route.startsWith('/editor') ? 'page' : undefined}>AI Editor</a><a href="#/taste" aria-current={route.startsWith('/taste') ? 'page' : undefined}>Discover Your Taste</a><a href="#/dashboard">Dashboard</a><a href="#/connections">Connections</a><button onClick={() => window.dispatchEvent(new CustomEvent('rayflow:choose-project'))}>Projects</button><button onClick={() => window.dispatchEvent(new CustomEvent('rayflow:assets'))}>Assets</button></nav>}
      {route.startsWith('/editor') ? getWorkspaceSession() ? <ModuleBoundary><Suspense fallback={<WorkspaceLoading />}><EditorWorkspace /></Suspense></ModuleBoundary> : <main className="workspace-page"><h1>Connect to your workspace</h1><p>The AI Editor needs the backend for private projects and provider connections.</p><button onClick={() => void initialize()}>Reconnect</button></main> : route.startsWith('/studio') ? <StudioPage feature={route.split('/')[2]} onBackToHome={() => navigate('/')} /> : route === '/connections' ? <SettingsPage /> : route === '/dashboard' ? <DashboardPage /> : route.startsWith('/taste') ? <TastePage /> : <LandingPage onEnterStudio={() => navigate('/studio')} />}
      <ProjectManager />
      <SharedAssets />
      {setup && <WorkspaceSetup onClose={() => setSetup(false)} />}
    </div>
  );
}

export default App;
