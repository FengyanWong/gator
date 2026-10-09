import { Component, ErrorInfo, ReactNode } from 'react';
import { Json, saveJson } from '../api';
import { STORAGE_KEY } from '../store';
import { keep, readKept } from '../kept';

/** What the page shows when drawing it failed (record 7.188, design advice): what broke and the ways out - Undo the change that
 *  led to it, Export JSON of the configuration, Reload - instead of a blank page with nothing to press. App holds one under the
 *  configuration's Undo history (`undo`), main.tsx one around everything; without an Undo the way out of a failure that comes
 *  back on every reload is an empty configuration, the saved one downloaded first. */
type Props = { children: ReactNode; undo?: () => void; canUndo?: boolean; config?: Json };
type State = { error: Error | null; where: string };

export class CrashPanel extends Component<Props, State> {
  state: State = { error: null, where: '' };
  static getDerivedStateFromError(error: Error): Partial<State> { return { error }; }
  componentDidCatch(_error: Error, info: ErrorInfo) { this.setState({ where: info.componentStack ?? '' }); }

  render() {
    const { error, where } = this.state;
    if (!error) return this.props.children;
    const { undo, canUndo = false, config } = this.props;
    const saved = (): Json => readKept(s => JSON.parse(s.getItem(STORAGE_KEY) ?? 'null'), () => null);
    const exportJson = () => { const c = config ?? saved(); if (c) saveJson(`${c.project?.task_name ?? 'configuration'}.config.json`, c); };
    const startEmpty = () => {
      if (!window.confirm('Start from an empty configuration? The saved one is downloaded first (Export JSON); its rows can come back with Import JSON.')) return;
      exportJson();
      keep(s => s.removeItem(STORAGE_KEY));   // no storage: the page opens empty anyway
      window.location.reload();
    };
    return (
      <div className="crash-panel" role="alert">
        <h2>The page could not be drawn</h2>
        <code>{error.message || String(error)}</code>
        <p>{undo && canUndo
          ? 'Your configuration is kept in this browser. Undo goes back to it as it was before the last change; Export JSON downloads it as it is now; Reload opens the page again.'
          : 'The configuration saved in this browser is kept. Export JSON downloads it; Reload opens the page again. If the page fails on every reload, start from an empty configuration: the saved one is downloaded first.'}</p>
        <div className="row">
          {undo && canUndo && <button className="primary" onClick={() => { undo(); this.setState({ error: null, where: '' }); }}>Undo the last change</button>}
          <button onClick={exportJson}>Export JSON</button>
          <button onClick={() => window.location.reload()}>Reload</button>
          {!(undo && canUndo) && <button onClick={startEmpty}>Start from an empty configuration...</button>}
        </div>
        <details><summary>Details for a bug report</summary><pre>{`${error.stack ?? error}${where}`}</pre></details>
      </div>);
  }
}
