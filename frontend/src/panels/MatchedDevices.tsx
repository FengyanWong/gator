import { useEffect, useState } from 'react';
import { api, Json, problemText } from '../api';
import { DiffView } from './Editors';

/** "Matched devices..." of the Parameters tab (status record 7.103): the structures the backend reads from the loaded
 *  circuit (differential pairs, current-mirror loads, matched loads and cascodes, tails - device types and pin roles from
 *  the verified mapping, never from names) and the ties they suggest. Nothing changes until "Review..." shows the
 *  diff and Apply is pressed; Undo in the toolbar takes an applied change back. Every request is a press: an answer about
 *  rows that have changed since says so and offers "Find again" instead of asking again by itself. */
export function MatchedDevices({ config, setConfig, onClose }: { config: Json; setConfig: (c: Json | ((c: Json) => Json)) => void; onClose: () => void }) {
  const about = (c: Json) => JSON.stringify({ circuit: c.circuit, parameters: c.parameters });
  const [answer, setAnswer] = useState<Json>(null);
  const [asked, setAsked] = useState<string | null>(null);
  const [ticked, setTicked] = useState<Record<string, boolean>>({});
  const [shown, setShown] = useState<Json>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const stale = asked !== null && asked !== about(config);
  const chosen = (answer?.suggestions ?? []).filter((s: Json) => s.acts && ticked[s.id]).map((s: Json) => s.id);

  const find = async () => {
    setBusy(true); setError(null); setShown(null); setDone(null);
    try {
      const got = await api.matchedDevices(config);
      setAnswer(got); setAsked(about(config));
      setTicked(Object.fromEntries((got.suggestions ?? []).filter((s: Json) => s.acts && s.default).map((s: Json) => [s.id, true])));
    } catch (e: any) { setError(problemText(e)); } finally { setBusy(false); }
  };
  const review = async () => {
    setBusy(true); setError(null); setDone(null);
    try { setShown(await api.matchedDevices(config, chosen)); } catch (e: any) { setError(problemText(e)); } finally { setBusy(false); }
  };
  const apply = () => {
    const changed = shown.diff.length;
    setConfig((c: Json) => ({ ...c, parameters: shown.parameters }));
    // What was found is about the rows before: it goes, and its "the rows changed" warning no longer stands next to "Applied".
    setShown(null); setAnswer(null); setAsked(null);
    setDone(`Applied: ${changed} row${changed === 1 ? '' : 's'} changed. Undo in the toolbar takes it back.`);
  };
  // The toolbar's "Matched devices..." is the press that asks: the box opens with the answer on its way.
  useEffect(() => { find(); }, []);                     // eslint-disable-line react-hooks/exhaustive-deps
  const ratio = (r: number) => Number(r.toPrecision(6)).toString();
  const change = (c: Json) => c.action === 'tie' ? `${c.variable_id} follows ${c.leader} (ratio ${ratio(c.ratio)})`
    : c.action === 'add' ? `adds a row for ${c.device} ${c.parameter}, following ${c.leader} (ratio ${ratio(c.ratio)})`
    : `${c.variable_id ?? `${c.device} ${c.parameter}`}: ${c.reason}`;

  return (
    <div className="matched-devices">
      <div className="row"><h4>Matched devices</h4>
        <button className="text" disabled={busy} onClick={find} title="Find again: read the structures of the circuit and the ties they suggest for the rows as they are now.">{answer ? 'Find again' : 'Find'}</button>
        <span className="spacer" /><button className="text" onClick={onClose} title="Close this box. The rows stay as they are.">Close</button></div>
      {!answer && !busy && !error && <p className="hint">Reads the circuit of this task for differential pairs, current-mirror loads, matched loads and cascodes, and
        suggests tying their sizes: a follower row keeps the ratio the circuit has now. Device types come from the device mapping, not from names. Nothing is simulated.</p>}
      {busy && <p className="hint">Reading the circuit...</p>}
      {error && <p className="error">{error}</p>}
      {answer && <>
        {stale && <p className="warn">The rows or the circuit changed after this was found: press Find again.</p>}
        {answer.structures.length > 0
          ? <ul className="structures">{answer.structures.map((s: Json) => <li key={`${s.kind}:${s.devices.join('+')}`}>{s.text}</li>)}</ul>
          : answer.applicable && <p className="hint">No differential pair, current-mirror load, matched load or cascode was found in this circuit.</p>}
        {/* A verified task's fixed rows are a limit, said in the normal colour; a circuit that cannot be read is a problem. */}
        {!answer.applicable && <p className={answer.blocked ? 'warn' : 'fact'}>{answer.why_not}</p>}
        {answer.applicable && answer.suggestions.length > 0 && <>
          <table className="grid small"><thead><tr><th></th><th>Tie</th><th>What changes</th></tr></thead>
            <tbody>{answer.suggestions.map((s: Json) => <tr key={s.id} className={s.acts ? '' : 'muted'}>
              <td><input type="checkbox" aria-label={`Tie ${s.devices.join(' and ')}`} disabled={!s.acts || stale} checked={!!ticked[s.id] && s.acts}
                onChange={e => { setTicked(t => ({ ...t, [s.id]: e.target.checked })); setShown(null); }} /></td>
              <td>{s.text}{s.note && <div className="hint">{s.note}</div>}</td>
              <td>{s.changes.map((c: Json, i: number) => <div key={i} className={c.action === 'skip' ? 'hint' : ''}>{change(c)}</div>)}</td></tr>)}</tbody></table>
          <div className="row"><button disabled={busy || stale || !chosen.length} onClick={review}
            title="Review: the rows with the ticked ties made, as a diff. Nothing changes before Apply.">Review...</button>
            <span className="hint">Independent action variables now: <b>{answer.independent_before ?? '?'}</b>.</span></div>
          {answer.note && <p className="hint">{answer.note}</p>}
        </>}
        {answer.applicable && answer.suggestions.length === 0 && answer.structures.length > 0 &&
          <p className="hint">Nothing to tie: none of these devices has a size among the Parameters rows.</p>}
      </>}
      {shown && !stale && <div className="confirm">
        <h4>Tie {chosen.length}: independent action variables {shown.independent_before} &rarr; {shown.independent_after}</h4>
        {shown.problems.map((p: Json, i: number) => <p key={i} className="issue error">{p.level}: {p.message}</p>)}
        <DiffView diff={shown.diff} />
        <button disabled={shown.problems.length > 0} onClick={apply}>Apply</button><button onClick={() => setShown(null)}>Cancel</button></div>}
      {done && <p className="ok">{done}</p>}
    </div>
  );
}
