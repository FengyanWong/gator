// The Parameters tab's Matched devices box (record 7.103): the structures the backend reads from the circuit and the
// ties they suggest, applied only by Review... and Apply.
import { useEffect, useState } from 'react';
import { api, Json, problemText } from '../api';
import { DiffView } from './DiffView';
import { unitIn } from './editorRules';
import { Icon } from './Icons';

/** A kind the circuit has three times or more is one line (branch record SIF-73): the VCO's eight cross-coupled pairs were
 *  one sentence eight times over, which filled the box and pushed the ties, Review... and the table out of view. The words say
 *  once what the backend's sentences (structures.py) repeat; each whole sentence stays in the line's tooltip. A kind not
 *  named here keeps its sentences. */
const KIND_LINES: Record<string, string> = {
  differential_pair: 'differential pairs', cross_coupled_pair: "cross-coupled pairs, each gate on the other's drain",
  tail_source: 'tail current sources', active_load: 'current-mirror loads, the diode-connected device first',
  load_pair: 'matched load pairs', cascode_pair: 'matched cascode pairs', current_mirror: 'current mirrors, the diode-connected reference first' };
const GROUP_FROM = 3;
const structureLines = (structures: Json[]) => {
  const count: Record<string, number> = {};
  structures.forEach((s: Json) => { count[s.kind] = (count[s.kind] ?? 0) + 1; });
  const lines: { key: string; text: string; title?: string }[] = [], grouped = new Set<string>();
  for (const s of structures) {
    if (!KIND_LINES[s.kind] || count[s.kind] < GROUP_FROM) { lines.push({ key: `${s.kind}:${s.devices.join('+')}`, text: s.text }); continue; }
    if (grouped.has(s.kind)) continue;
    grouped.add(s.kind);
    const same = structures.filter((x: Json) => x.kind === s.kind);
    const devices = (d: string[]) => s.kind === 'current_mirror' ? `${d[0]} into ${d.slice(1).join(', ')}` : d.join(' and ');
    lines.push({ key: s.kind, text: `${same.length} ${KIND_LINES[s.kind]}: ${same.map((x: Json) => devices(x.devices)).join('; ')}.`,
      title: same.map((x: Json) => x.text).join('\n') });
  }
  return lines;
};

/** "Matched devices..." of the Parameters tab (status record 7.103): the structures the backend reads from the loaded
 *  circuit (differential pairs, current-mirror loads, matched loads and cascodes, tails - device types and pin roles from
 *  the verified mapping, never from names) and the ties they suggest. Nothing changes until "Review..." shows the
 *  diff and Apply is pressed; Undo in the toolbar takes an applied change back. Every request is a press: an answer about
 *  rows that have changed since says so and points to the toolbar's "Matched devices..." instead of asking again by itself.
 *  `onShown`: an answer is drawn and the box has its height (Editors folds the bottom panel when that leaves the table too
 *  little room; branch record SIF-73). */
export function MatchedDevices({ config, setConfig, onClose, onShown }: { config: Json; setConfig: (c: Json | ((c: Json) => Json)) => void; onClose: () => void;
  onShown?: () => void }) {
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
  useEffect(() => { if (answer) onShown?.(); }, [answer]);   // eslint-disable-line react-hooks/exhaustive-deps
  const ratio = (r: number) => Number(r.toPrecision(6)).toString();
  const change = (c: Json) => c.action === 'tie' ? `${c.variable_id} follows ${c.leader} (ratio ${ratio(c.ratio)})`
    : c.action === 'add' ? `adds a row for ${c.device} ${c.parameter}, following ${c.leader} (ratio ${ratio(c.ratio)})`
    : `${c.variable_id ?? `${c.device} ${c.parameter}`}: ${c.reason}`;

  return (
    <div className="matched-devices">
      <div className="row"><h4>Matched devices</h4>
        <span className="spacer" /><button onClick={onClose} title="Close: The rows stay as they are."><Icon name="close" label="Close" /></button></div>
      {!answer && !busy && !error && <p className="hint">Reads the circuit of this task for differential pairs, current-mirror loads, matched loads and cascodes, and
        suggests tying their sizes: a follower row keeps the ratio the circuit has now. Device types come from the device mapping, not from names. Nothing is simulated.</p>}
      {busy && <p className="hint">Reading the circuit...</p>}
      {error && <p className="error">{error}</p>}
      {answer && <>
        {stale && <p className="warn">The rows or the circuit changed after this was found: press Matched devices... in the toolbar to refresh.</p>}
        {answer.structures.length > 0
          ? <ul className="structures">{structureLines(answer.structures).map(l => <li key={l.key} title={l.title}>{l.text}</li>)}</ul>
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
            {/* "Searched rows", the word of the Parameters fact line ("The optimizer searches ...", branch record SIF-73) and of
                the task's Details, where both lines here said "independent action variables" and the heading "Tie 2: ..." read
                like an order to tie item 2 (branch record SIF-50). "?" as before: the line is drawn only once the answer is here, so no count means the route could not count, not
                that it is still counting. */}
            <span className="hint">Searched rows now: <b>{answer.independent_before ?? '?'}</b>.</span></div>
          {answer.note && <p className="hint">{answer.note}</p>}
        </>}
        {answer.applicable && answer.suggestions.length === 0 && answer.structures.length > 0 &&
          <p className="hint">Nothing to tie: none of these devices has a size among the Parameters rows.</p>}
      </>}
      {shown && !stale && <div className="confirm">
        <h4>{chosen.length} tie{chosen.length === 1 ? '' : 's'}: searched rows {shown.independent_before} &rarr; {shown.independent_after}</h4>
        {shown.problems.map((p: Json, i: number) => <p key={i} className="issue error">{p.level}: {p.message}</p>)}
        {/* Its ties change Parameters rows only: their numbers are written in the rows' units, as the cells write them (1 um,
            not 0.000001; branch record SIF-51). */}
        <DiffView diff={shown.diff} unitOf={unitIn(config, { parameters: 'variable_id' })} />
        <button disabled={shown.problems.length > 0} onClick={apply}>Apply</button><button onClick={() => setShown(null)}>Cancel</button></div>}
      {done && <p className="ok">{done}</p>}
    </div>
  );
}
