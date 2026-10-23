"""One-time explicit adaptation of the imported baseline; never touches upstream."""
from pathlib import Path
import os
import re

ROOT = Path(__file__).resolve().parents[1]
EDITOR = ROOT / 'frontend/src/features/ai-editor'


def between(text, start, end, replacement):
    first = text.index(start)
    last = text.index(end, first)
    return text[:first] + replacement + text[last:]


def main():
    app = (EDITOR / 'App.tsx').read_text(encoding='utf-8')
    app = re.sub(r"import (?:PricingScreen|AuthScreen|StudioLogin) from .*;\n", '', app)
    app = app.replace("useState<Workspace>('PROJECT')", "useState<Workspace>('EDIT')")
    app = app.replace("startupWorkspace: 'PROJECT',", "startupWorkspace: 'EDIT',")
    app = app.replace("return prefersLight ? 'light' : 'dark';", "return 'dark';")
    app = app.replace('filterWorkspacesForRole(getAllowedWorkspacesForMode(uiMode), isDirector)', 'getAllowedWorkspacesForMode(uiMode)')
    app = app.replace('showReview: isDirector,', 'showReview: true,').replace('showRequests: !isDirector,', 'showRequests: true,')
    app = app.replace('document.body.dataset.theme = theme;', "document.querySelector<HTMLElement>('.rayflow-editor')?.setAttribute('data-theme', theme);")
    app = between(app, '    // --- Auth Handlers ---', '    const handleSwitchProfile', '''    // Rayflow owns the guest identity. Optional account linking lives in Connections.
    const handleLogout = () => { window.location.hash = '/connections'; };
    useEffect(() => {
        const session = getWorkspaceSession();
        if (session) setUser({ id: session.workspace_id, name: 'Guest filmmaker', email: '', plan: 'pro' });
        setAuthStatus('signed_in');
    }, []);

''')
    app = re.sub(r"    useEffect\(\(\) => \{\n        const unsubscribe = subscribeUsage[\s\S]*?    \}, \[isElectron, teamId\]\);", '''    useEffect(() => subscribeUsage(entry => {
        setUsageLedger(previous => ({ entries: [...previous.entries, entry] }));
    }), []);''', app, count=1)
    app = between(app, '    const planLabel = (() => {', '    const estimateTtsMinutes', '''    const planLabel = undefined;
    const creditBalance = null;
    const blockForBilling = false;
    const isByokMode = true;
    const effectiveCostRates = costSettings.rates?.length ? costSettings.rates : DEFAULT_COST_SETTINGS.rates;
''')
    app = between(app, '    const validateHostedGeneration = useCallback', '    useEffect(() => {\n        try {\n            window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY', '''    const validateHostedGeneration = async (_options: unknown): Promise<{ok: boolean; message?: string}> => ({ ok: true });

''')
    app = between(app, '    // --- Render ---', '    const renderWorkspace = () => {', '''    // The workspace stays mounted inside Rayflow's application shell.
    useEffect(() => {
        const open = (event: Event) => { void handleLoadProject((event as CustomEvent<string>).detail); };
        const save = () => { void handleSaveProject(); };
        window.addEventListener('rayflow:open-project', open);
        window.addEventListener('rayflow:save-project', save);
        const initial = getWorkspaceSession()?.preferences?.activeProject;
        if (initial) void handleLoadProject(initial);
        return () => { window.removeEventListener('rayflow:open-project', open); window.removeEventListener('rayflow:save-project', save); };
    }, []);

''')
    app = between(app, '                    {!isElectron && (trialExpired || lowCredits) && (', '                    {!isDirector && requestSummaries', '')
    app = between(app, '            {blockForBilling && (', '            {isAssistantVisible', '')
    app = between(app, '            {showPricing && (', '            <OptionsModal', '')
    app = app.replace('onOpenPricing={() => setShowPricing(true)}', '')
    app = app.replace("setActiveWorkspace('PROJECT');\n            projectFileMtimeRef.current", "setActiveWorkspace('EDIT');\n            projectFileMtimeRef.current")
    app = app.replace("<div className=\"app-shell app-frame\">", "<div className=\"app-shell app-frame\">")
    app = "import { getWorkspaceSession } from '../../services/editorClient';\n" + app
    (EDITOR / 'App.tsx').write_text(app, encoding='utf-8')

    path = EDITOR / 'config/uiModes.ts'
    path.write_text(path.read_text(encoding='utf-8').replace("DEFAULT_UI_MODE: UIMode = 'beginner'", "DEFAULT_UI_MODE: UIMode = 'pro'"), encoding='utf-8')
    path = EDITOR / 'services/projectService.ts'
    source = path.read_text(encoding='utf-8')
    source = between(source, 'const ensureProjectApi =', 'const MIME_EXTENSION', 'const ensureProjectApi = (): ElectronProjectApi => projectApi;\n\n')
    source = between(source, 'const toFileUrl =', 'const ensureUniqueProjectPath', 'const toFileUrl = projectFileUrl;\n\n')
    source = "import { projectApi, projectFileUrl } from '../runtime/project';\n" + source
    path.write_text(source, encoding='utf-8')

    excluded = ['components/PricingScreen.tsx', 'services/subscriptionService.ts', 'config/stripe.ts']
    for relative in excluded:
        path = EDITOR / relative
        if path.exists():
            path.unlink()

    for path in EDITOR.rglob('*'):
        if path.suffix not in ('.ts', '.tsx') or 'runtime' in path.parts or '.test.' in path.name:
            continue
        source = path.read_text(encoding='utf-8')
        imports = []
        relative = lambda file: os.path.relpath(EDITOR / 'runtime' / file, path.parent).replace('\\', '/')
        if 'localStorage' in source:
            source = re.sub(r'(?:(?:window|globalThis)\.)?localStorage\b', 'editorStorage', source)
            imports.append("import { editorStorage } from '" + relative('storage') + "';")
        if re.search(r'(?<![.\w])fetch\(', source):
            imports.append("import { editorFetch as fetch } from '" + relative('transport') + "';")
        if re.search(r"import \{[^}]*\bGoogleGenAI\b[^}]*\} from ['\"]@google/genai['\"]", source):
            source = re.sub(r"(import \{)([^}]*)(\} from ['\"]@google/genai['\"])",
                            lambda match: match[1] + re.sub(r'\bGoogleGenAI\b\s*,?\s*', '', match[2]) + match[3], source)
            imports.append("import { GoogleGenAI } from '" + relative('google') + "';")
        before = source
        source = re.sub(r'(?:window|\(window as any\))(?:\?\.|\.)electron(?:\?\.|\.)project', 'projectApi', source)
        if source != before and 'import { projectApi,' not in source:
            imports.append("import { projectApi } from '" + relative('project') + "';")
        # There is no process.env credential bridge in a browser bundle.
        source = source.replace('process.env.API_KEY', "editorStorage.getItem('gemini_api_key')")
        if 'editorStorage.' in source and not any('editorStorage' in item for item in imports) and "import { editorStorage }" not in source:
            imports.append("import { editorStorage } from '" + relative('storage') + "';")
        source = '\n'.join(imports) + '\n' + source
        path.write_text(source, encoding='utf-8')
    print('Adapted ownership, provider transport, project APIs, defaults, and payment gates.')


if __name__ == '__main__':
    main()
