import type { ReactNode } from 'react';

export default function WorkspaceLoading({ message = 'Opening AI Editor', error, onRetry, children, page = false, overlay = false }: {
  message?: string; error?: string; onRetry?: () => void; children?: ReactNode; page?: boolean; overlay?: boolean;
}) {
  return <div className={`rayflow-loading${page ? ' rayflow-loading--page' : ''}${overlay ? ' rayflow-loading--overlay' : ''}`} aria-busy={!error}>
    <div className="pre-in">
      <div className="pre-mark"><img src="/landing-pages/rayflow-mark.svg" alt="" /></div>
      <h1>RAYFLOW AI</h1>
      {error ? <><p role="alert">{error}</p><div className="workspace-actions">
        {onRetry && <button onClick={onRetry}>Retry</button>}{children}
      </div></> : <><div className="pre-bar" aria-hidden="true"><i /></div><div className="pre-meta" role="status">{message}</div></>}
    </div>
  </div>;
}
