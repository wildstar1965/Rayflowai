import React from 'react';
import ProviderConnections from '../../../components/ProviderConnections';
export default function OnboardingModal(props: any) {
  if (!props.isOpen) return null;
  return <div className="rayflow-modal-backdrop"><section className="rayflow-modal rayflow-setup-modal" role="dialog" aria-modal="true" aria-labelledby="editor-welcome">
    <div className="rayflow-modal-body">
    <h1 id="editor-welcome">Your complete production workspace</h1><p>Import media, edit the timeline, or connect a provider to generate scripts, images, video and sound. All workspace groups are available in Pro mode.</p>
    <ProviderConnections quick />
    </div>
    <div className="workspace-actions"><button onClick={() => props.onComplete(true)}>Start editing</button><button onClick={() => props.onComplete(true)}>Skip setup</button><button onClick={props.onOpenApiSettings}>All settings</button></div>
  </section></div>;
}
