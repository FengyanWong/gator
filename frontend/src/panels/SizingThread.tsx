import { useEffect, useState } from 'react';
import { api, Json } from '../api';
import { searchPhase } from './SearchSettings';

const LIVE = ['created', 'starting', 'running', 'pausing', 'stopping'];
const STARTING = ['created', 'starting'];            // a run's status has no search yet: it comes once the engine runs

/** The run's AI sizing thread in the Agent tab. `visible`: the tab is open, or the conversation is in its own window.
 *  `hint` lives in the Agent tab, so detaching the conversation (which draws this anew) keeps what is being typed. */
export function SizingThread({ runDir, active, visible, hint, setHint }: { runDir?: string | null; active: boolean; visible: boolean;
  hint: string; setHint: (text: string) => void }) {
  const [thread, setThread] = useState<Json>(null);
  const [error, setError] = useState('');
  const [sending, setSending] = useState(false);
  // A refused hint is said until the next press: on the line of the reads, the next good read took it away within a second.
  const [hintError, setHintError] = useState('');
  useEffect(() => { setThread(null); setError(''); setHintError(''); }, [runDir]);
  // Read while the thread can be seen, and again every second while the run is live AND has an AI search: a SAC run has
  // none, and was read every second all the same, with the Agent tab closed too (audit 2026-09-30). A failed read is
  // tried again more slowly instead of ending the updates for the rest of the run; a status read that fails for a moment
  // (active false, then true) no longer empties the thread.
  useEffect(() => {
    if (!runDir || !visible) return;
    let gone = false, failures = 0, timer: ReturnType<typeof setTimeout> | undefined;
    const read = async () => {
      let again = 0;
      try {
        const data = await api.llmThread(runDir);
        if (gone) return;
        failures = 0; setThread(data); setError('');
        // A run just started is read until its search appears (a SAC run's never does: its reads end once it runs). The
        // thread of a new AI run never came while the tab was open (review of 2026-10-01).
        if (active && LIVE.includes(data.state) && (data.search || STARTING.includes(data.state))) again = 1000;
      } catch (e: any) {
        if (gone) return;
        setError(e.message);
        if (active && ++failures <= 5) again = 3000 * failures;
      }
      if (again) timer = setTimeout(read, again);
    };
    read();
    return () => { gone = true; clearTimeout(timer); };
  }, [runDir, active, visible]);
  if (!thread?.search) return null;
  const search = thread.search;
  const calls: Record<string, Json[]> = {};
  for (const event of thread.events ?? []) (calls[event.call_id ?? 'run'] ??= []).push(event);
  // One hint per press: a double click used to store it twice (both counted towards the limit and went into the call).
  const send = async () => {
    if (sending) return;
    setSending(true);
    try { await api.llmHint(runDir!, hint); setHint(''); setHintError(''); }
    catch (e: any) { setHintError(e.message); } finally { setSending(false); }
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
      // The call's own number: the thread holds the newest events only, so a position would renumber older calls.
      const number = events.find(e => e.type === 'call_started')?.call_number ?? index + 1;
      const response = events.find(e => e.type === 'reply' && e.output);
      const finished = events.find(e => e.type === 'call_finished');
      const thinking = events.filter(e => e.type === 'thinking').map(e => e.text).join('');
      return <article className="sizing-call" key={id}>
        <h4>AI call {number}</h4>
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
    <button disabled={!search.hints_available || !active || !hint.trim() || sending} onClick={send}>{sending ? 'Adding...' : 'Add hint'}</button>
    <p className="hint">Hints guide a future eligible call. They cannot change bounds, specifications or budgets, or trigger a rescue.</p>
    {hintError && <p className="error">{hintError}</p>}
    {error && <p className="error">{error}</p>}
  </section>;
}
