import { Component, type ErrorInfo, type ReactNode } from 'react';
import Editor from './App';
import WorkspaceLoading from '../../components/WorkspaceLoading';
import './editor.css';
import './rayflow.css';

class EditorBoundary extends Component<{ children: ReactNode }, { error: string }> {
  state = { error: '' };
  static getDerivedStateFromError(error: Error) { return { error: error.message }; }
  componentDidCatch(_error: Error, _info: ErrorInfo) { /* The message is shown locally, without exporting project contents. */ }
  render() {
    if (this.state.error) return <WorkspaceLoading error={`The editor could not open. ${this.state.error}`} onRetry={() => this.setState({ error: '' })}><a href="#/">Back to Rayflow</a></WorkspaceLoading>;
    return this.props.children;
  }
}
export default function EditorWorkspace() {
  return <div className="rayflow-editor" data-theme="dark"><EditorBoundary><Editor /></EditorBoundary></div>;
}
