import { Component, lazy, Suspense, useState } from 'react';
import type { ComponentType, ErrorInfo, ReactNode } from 'react';

/** The panel's own file could not be downloaded: a network fault, or a page rebuilt since it opened (its old file is
 *  gone, so only a Reload helps). Named, not subclassed, so the check survives any compile target. */
const DOWNLOAD_FAILED = 'PanelDownloadError';

/** Optional panels load on first use. A failed download can be retried without losing the page's edits. */
export function deferredPanel<P extends object>(load: () => Promise<ComponentType<P>>, name: string) {
  const makePanel = () => lazy(async () => {
    let Loaded: ComponentType<P>;
    try {
      Loaded = await load();
    } catch (error) {
      // The failed import is not kept for the next opening of the panel (review of 2026-11-04, record 7.471).
      Current = makePanel();
      const failed = new Error(error instanceof Error ? error.message : String(error));
      failed.name = DOWNLOAD_FAILED;
      throw failed;
    }
    return { default: ({ panelProps }: { panelProps: P }) => <Loaded {...panelProps} /> };
  });
  let Current = makePanel();
  return function DeferredPanel(props: P) {
    const [Panel, setPanel] = useState(() => Current);
    const [attempt, setAttempt] = useState(0);
    return <PanelError key={attempt} name={name} retry={() => { Current = makePanel(); setPanel(() => Current); setAttempt(n => n + 1); }}>
      <Suspense fallback={<p className="hint" role="status">Loading {name}…</p>}><Panel panelProps={props} /></Suspense>
    </PanelError>;
  };
}

/** Keep visited tabs mounted so charts, conversations and active cancellation controls survive tab switches. */
export function VisitedPanel({ active, children }: { active: boolean; children: ReactNode }) {
  const [visited, setVisited] = useState(active);
  if (active && !visited) setVisited(true);
  // No extra layout box: Training sizes its charts against the bottom panel's height.
  return visited || active ? <div hidden={!active} style={active ? { display: 'contents' } : undefined}>{children}</div> : null;
}

/** A failure stays inside its panel, so the editors, Undo and Export JSON stay usable. It says what failed: a download
 *  (Retry, or Reload after a rebuild: the configuration saved in this browser is kept) or a fault in the panel itself,
 *  whose message and details are shown as the crash panel shows them (record 7.471; it said "Could not open" for both). */
class PanelError extends Component<{ name: string; retry: () => void; children: ReactNode }, { error: Error | null; where: string }> {
  state = { error: null as Error | null, where: '' };
  static getDerivedStateFromError(error: Error) { return { error }; }
  componentDidCatch(_error: Error, info: ErrorInfo) { this.setState({ where: info.componentStack ?? '' }); }
  render() {
    const { error, where } = this.state;
    if (!error) return this.props.children;
    const download = error.name === DOWNLOAD_FAILED;
    return <div className="error" role="alert">
      Could not open {this.props.name}{download
        ? ': its file could not be downloaded. If the page was rebuilt since it opened, reload it; the configuration saved in this browser is kept.'
        : `: ${error.message || String(error)}`}{' '}
      <button type="button" onClick={this.props.retry}>Retry</button>{' '}
      <button type="button" onClick={() => window.location.reload()}>Reload the page</button>
      {!download && <details><summary>Details for a bug report</summary><pre>{`${error.stack ?? error}${where}`}</pre></details>}
    </div>;
  }
}
