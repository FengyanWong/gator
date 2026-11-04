import { Component, lazy, Suspense, useState } from 'react';
import type { ComponentType, ReactNode } from 'react';

/** Optional panels load on first use. A failed download can be retried without losing the page's edits. */
export function deferredPanel<P extends object>(load: () => Promise<ComponentType<P>>, name: string) {
  const makePanel = () => lazy(async () => {
    const Loaded = await load();
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

class PanelError extends Component<{ name: string; retry: () => void; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    return this.state.failed ? <div className="error" role="alert">Could not open {this.props.name}.{' '}
      <button type="button" onClick={this.props.retry}>Retry</button></div> : this.props.children;
  }
}
