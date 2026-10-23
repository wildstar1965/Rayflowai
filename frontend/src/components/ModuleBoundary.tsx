import { Component, type ReactNode } from 'react';
import WorkspaceLoading from './WorkspaceLoading';

export default class ModuleBoundary extends Component<{ children: ReactNode }, { error: string }> {
  state = { error: '' };
  static getDerivedStateFromError(error: Error) { return { error: error.message }; }
  render() {
    if (this.state.error) return <WorkspaceLoading error={`The editor could not load. ${this.state.error}`} onRetry={() => window.location.reload()}><a href="#/">Return to Rayflow</a></WorkspaceLoading>;
    return this.props.children;
  }
}
