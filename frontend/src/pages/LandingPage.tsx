import { useCallback, useEffect, useRef, useState } from 'react';
import { KageLandingPage } from '@designcodeio/threeui';
import '@designcodeio/threeui/style.css';
import './LandingPage.css';

interface LandingPageProps {
  onEnterStudio: () => void;
}

export function LandingPage({ onEnterStudio }: LandingPageProps) {
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const observer = useRef<MutationObserver | null>(null);
  const applyBrand = useCallback((frame: HTMLIFrameElement) => {
    frame.title = 'Rayflow AI — Your story. Your rhythm.';
    const document = frame.contentDocument;
    if (!document?.body || !document.querySelector('#pre')) return;
    const link = (element: HTMLAnchorElement, path: string, label: string) => {
      element.href = `../#${path}`; element.target = '_parent'; element.setAttribute('aria-label', label);
      if (element.dataset.rayflowLinked) return;
      element.dataset.rayflowLinked = 'true';
      element.addEventListener('click', event => { event.preventDefault(); event.stopImmediatePropagation(); window.location.hash = path; }, true);
    };
    const navigation = [
      { path: '/studio', label: 'Editor', alternate: '編集' },
      { path: '/editor', label: 'AI Editor', alternate: 'AI 編集' },
      { path: '/dashboard', label: 'Dashboard', alternate: '記録' },
      { path: '/connections', label: 'Connections', alternate: '接続' },
    ];
    document.querySelectorAll<HTMLAnchorElement>('.nav-links .nav-link').forEach((anchor, index) => {
      const item = navigation[index]; if (!item) return;
      const spans = anchor.querySelectorAll('span');
      if (spans[0]) spans[0].textContent = item.label;
      if (spans[1]) spans[1].textContent = item.alternate;
      link(anchor, item.path, item.label);
    });
    const footerItems = [
      { path: '/', label: 'Home' }, { path: '/studio', label: 'Editor' },
      { path: '/dashboard', label: 'Dashboard' }, { path: '/studio/auto-reel', label: 'Auto Reel' },
      { path: '/studio/captions', label: 'Smart Captions' }, { path: '/studio/export', label: 'Timeline Export' },
      { path: '/studio/audio', label: 'Audio and beat analysis' }, { path: '/connections', label: 'Connections' },
      { path: '/studio', label: 'Continue your edit' },
      { path: '/studio/captions', label: 'Caption tools' }, { path: '/', label: 'Back to Rayflow' },
    ];
    document.querySelectorAll<HTMLAnchorElement>('.foot-grid li a').forEach((anchor, index) => {
      const item = footerItems[index]; if (!item) return;
      anchor.textContent = item.label; link(anchor, item.path, item.label);
    });
    if (!document.querySelector('#rayflow-tools-style')) {
      const style = document.createElement('style'); style.id = 'rayflow-tools-style';
      style.textContent = '#cards .glow{display:none}#cards .card:focus-visible,.foot a:focus-visible{outline:2px solid var(--brass);outline-offset:6px}.card-meta span:first-child{max-width:28ch}.card-lab .jp{display:none}';
      document.head.appendChild(style);
    }
    const workflows = [
      { path: '/studio/auto-reel', name: 'Auto Reel', description: 'Build a reel from your footage and soundtrack' },
      { path: '/studio/captions', name: 'Smart Captions', description: 'Transcribe speech and shape timed phrases' },
      { path: '/studio/export', name: 'Timeline Export', description: 'Export cut timing and media references' },
    ];
    document.querySelectorAll<HTMLElement>('#cards .card').forEach((card, index) => {
      const workflow = workflows[index];
      if (!workflow || card.dataset.rayflowLinked) return;
      card.dataset.rayflowLinked = 'true';
      card.setAttribute('role', 'link'); card.tabIndex = 0;
      card.setAttribute('aria-label', workflow.name);
      const label = card.querySelector('.card-lab b'); if (label) label.textContent = workflow.name;
      const description = card.querySelector('.card-meta span'); if (description) description.textContent = workflow.description;
      const open = () => { window.location.hash = workflow.path; };
      card.addEventListener('click', event => { event.preventDefault(); event.stopImmediatePropagation(); open(); }, true);
      card.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); event.stopImmediatePropagation(); open(); } }, true);
    });
    observer.current?.disconnect();
    const inspect = () => {
      if (document.querySelector('#pre')?.classList.contains('done') && !document.body.classList.contains('is-locked')) {
        setReady(true); setFailed(false); observer.current?.disconnect();
      }
    };
    observer.current = new MutationObserver(inspect);
    observer.current.observe(document.body, { subtree: true, attributes: true, attributeFilter: ['class'] });
    inspect();
  }, []);
  useEffect(() => {
    if (ready) return;
    const deadline = window.setTimeout(() => setFailed(true), 30000);
    return () => window.clearTimeout(deadline);
  }, [ready, attempt]);
  useEffect(() => () => observer.current?.disconnect(), []);
  return (
    <main className="kage-landing">
      <div className="shader-frame">
        <KageLandingPage
          key={attempt}
          applyScene={applyBrand}
          headingFont="onest"
          bodyFont="onest"
          headingWeight="400"
          bodyWeight="300"
          primaryColor="#e0231c"
          headingSize={46}
          bodySize={17}
          headingLetterSpacing={-0.012}
        />
      </div>
      {failed && <div className="scene-error" role="alert"><p>The landing preview could not initialize.</p><button onClick={() => { setFailed(false); setAttempt(value => value + 1); }}>Retry preview</button><button onClick={onEnterStudio}>Go to editor</button></div>}
      {ready && <button className="kage-studio-entry" onClick={onEnterStudio}>
        Open Studio <span aria-hidden="true">&#8599;</span>
      </button>}
    </main>
  );
}

export default LandingPage;
