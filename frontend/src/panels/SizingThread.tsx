import { useEffect, useState } from 'react';
import { api, Json } from '../api';
import { searchPhase } from './SearchSettings';

export function SizingThread({ runDir, active }: { runDir?: string | null; active: boolean }) {
  const [thread, setThread] = useState<Json>(null);
  const [hint, setHint] = useState('');
  const [error, setError] = useState('');
  useEffect(() => {
    setThread(null); setHint(''); setError('');
    if (!runDir) return;
    let gone = false, timer: ReturnType<typeof setTimeout> | undefined;
    const read = async () => {
      try {
        const data = await api.llmThread(runDir);
        if (gone) return;
        setThread(data);
        if (active && ['created', 'running', 'pausing', 'stopping'].includes(data.state)) timer = setTimeout(read, 1000);
      } catch (e: any) { if (!gone) setError(e.message); }
    };
    read();
    return () => { gone = true; clearTimeout(timer); };
  }, [runDir, active]);
  if (!thread?.search) return null;
  const search = thread.search;
  const calls: Record<string, Json[]> = {};
  for (const event of thread.events ?? []) (calls[event.call_id ?? 'run'] ??= []).push(event);
  const send = async () => {
    try { await api.llmHint(runDir!, hint); setHint(''); setError(''); }
    catch (e: any) { setError(e.message); }
  };
  return <section className="sizing-thread">
    <h3>Run’s AI sizing thread</h3>
    <p role="status">{searchPhase(search)} · LLM {search.calls} / {search.max_calls}</p>
    {search.degraded && <p className="warn">AI starting designs unavailable: {search.degraded}. Random designs complete the starting batch.</p>}
    <details><summary>Search details</summary>
      {search.method === 'sac_llm_rescue' && <p>Rescue rounds {search.rounds} / {search.max_rounds}; evaluations without progress {search.stalled} / {search.stall_window}.</p>}
      <p>Hints accepted: {search.hint_count}; included in calls: {search.hints_included ?? 0}. {search.steered ? 'This run is marked steered.' : ''}</p>
    </details>
    {Object.entries(calls).map(([id, events], index) => {
      const response = events.find(e => e.type === 'reply' && e.output);
      const finished = events.find(e => e.type === 'call_finished');
      const thinking = events.filter(e => e.type === 'thinking').map(e => e.text).join('');
      return <article className="sizing-call" key={id}>
        <h4>AI call {index + 1}</h4>
        {thinking && <details><summary>Thinking summary</summary><p style={{ whiteSpace: 'pre-wrap' }}>{thinking}</p></details>}
        {finished && finished.status !== 'completed' && <p className="warn">Call ended: {finished.status}</p>}
        {response && <><p>{typeof response.output.analysis === 'string' ? response.output.analysis : 'Invalid model reply'}</p>
          <table className="grid small"><thead><tr><th>Proposed values</th><th>Reason</th></tr></thead><tbody>
            {(Array.isArray(response.output.candidates) ? response.output.candidates : []).filter((c: Json) => c && typeof c === 'object').map((c: Json, i: number) => <tr key={i}><td>{Object.entries(c.values ?? {}).map(([k, v]) => `${k}: ${v}`).join(', ')}</td><td>{typeof c.rationale === 'string' ? c.rationale : ''}</td></tr>)}
          </tbody></table><p className="hint">Accepted {response.accepted}; rejected {response.rejected?.length ?? 0}.</p></>}
        {events.filter(e => e.type === 'outcome').map(e => <p key={e.evaluation_id}>
          Simulated: {e.feasible ? 'meets all specifications' : e.valid ? 'valid result; specifications not met' : 'evaluation failed'}; reward {e.reward ?? 'unavailable'}.
          <span className="hint"> {e.evaluation_id}</span></p>)}
        {events.some(e => e.type === 'unused') && <p className="hint">Some suggestions were unused when the run ended.</p>}
      </article>;
    })}
    <label>Hint for the next AI call<textarea value={hint} maxLength={1500} disabled={!search.hints_available || !active}
      onChange={e => setHint(e.target.value)} /></label>
    <button disabled={!search.hints_available || !active || !hint.trim()} onClick={send}>Add hint</button>
    <p className="hint">Hints guide a future eligible call. They cannot change bounds, specifications or budgets, or trigger a rescue.</p>
    {error && <p className="error">{error}</p>}
  </section>;
}
