// The right column's Output settings (plan-refactoring C4, out of Right.tsx).
import { useEffect, useMemo, useState } from 'react';
import { useRequest } from '../store';
import { api, ApiError, Json } from '../api';
import { useCopied } from './copied';
import { bytes, clock, folderName, plural, stamp } from '../format';
import { OUTPUT_ROOT_ID } from '../contract';
import { ByteSize, Check, Module, Num } from './fields';
import { type Newest, useNewest } from '../newest';
import type { RunSummary } from '../contracts';

type Every = 'evaluations' | 'seconds';

/** A run folder's part in words, its key in the tooltip (branch record SIF-60: the rows read "run", "raw_data",
 *  "csv_exports"). The backend's keys (layout.py's subpaths) and the checks' fixtures' (run_dir, data); any other key
 *  in words as it is. */
const PATH_NAME: Record<string, string> = { run: 'Run folder', run_dir: 'Run folder', raw_data: 'Raw data', data: 'Data folder',
  csv_exports: 'CSV exports', simulator_work: 'Simulator work folder' };
const pathName = (key: string) => PATH_NAME[key] ?? key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' ');
/** An experiment folder as the run list names it, "<name>__<12 hex>" (layout.py, run_index.py); a run from before the ID
 *  reads "<name>__None" and is no experiment to add to. */
const EXPERIMENT = /^(.+)__([0-9a-f]{12})$/;
type Press = 'test' | 'measure' | 'list';

export function OutputPanel({ config, setConfig, meta, activeRun, headerWorks, runs, taskMock }: { config: Json; setConfig: (f: (c: Json) => Json) => void; meta: Json;
  activeRun: Json; headerWorks: boolean; runs: RunSummary[]; taskMock: boolean | null }) {
  const out = config.output;
  const set = (fields: Json) => setConfig(c => ({ ...c, output: { ...c.output, ...fields } }));
  const root = out.output_root ?? meta?.output_root ?? '';
  const [browse, setBrowse] = useState<Json>(null);
  // Copy path and a run path cell say "copied" or "could not copy", as Run status's Run folder does (branch record SIF-94:
  // they copied unsaid). Keyed by what was clicked: the root and a run path can be the same text. A run path by its row and
  // its text (SIF-94 review): by the row alone, another run shown within the 1.5 s said "copied" on a path never copied.
  const copying = useCopied();
  // The header's run working locks it too (branch record SIF-91: only the run the tabs show did).
  const locked = headerWorks || !!activeRun?.worker_alive;
  // The root is looked at 0.5 s after the last keystroke, and an answer for text typed before is dropped (useRequest):
  // whichever answer came last used to win, a half-typed path's too. A look no longer walks the folder for its size (record
  // 7.189: 0.7 to 2 s of disk work on D: at every page open, for one number in a closed fold): "Measure" asks for it.
  const { value: looked, error: lookError, refresh: retryLook } = useRequest<Json>(signal => api.checkOutput(root, false, signal), [root], { enabled: !!root, delay: 500 });
  // "Test writability", for the root it was pressed for, and when (local time) its answer came (branch record SIF-91: a writable
  // root's answer read as the look before it, so a press changed nothing on screen)
  const [tested, setTested] = useState<{ root: string; value: Json; at: string } | null>(null);
  useEffect(() => setTested(null), [root]);                                             // another root: its own look replaces it, as before
  const [sized, setSized] = useState<{ root: string; bytes: number | null } | null>(null);   // "Measure", for the root it was pressed for
  const testedHere = tested && tested.root === root ? tested : null;
  const check: Json = testedHere ? testedHere.value : looked;
  // Browse, a folder of its list and Test writability say what went wrong, as the other panels do (they used to say nothing).
  const [problem, setProblem] = useState<string | null>(null);
  // Only the newest press answers (two quick clicks in the folder list showed whichever came last), and a problem is
  // about the root it was pressed for: another root clears it. The folder list asks on its own line, which Close and "Use
  // this folder" let go: a folder on its way opened the list again after Close, or showed its error there (branch record
  // SIF-60 review); Test writability's and Measure's answers are not dropped with it.
  // Branch record SIF-91: each press says while its answer is on its way ("Testing...", "Measuring...", "Reading the
  // folder..."; on D: one takes seconds, and nothing showed that it ran), on a line of its own - Measure dropped a test on its
  // way, which then never answered.
  const tests = useNewest(), measures = useNewest(), listing = useNewest();
  const line: Record<Press, Newest> = { test: tests, measure: measures, list: listing };
  const [busy, setBusy] = useState<Record<Press, boolean>>({ test: false, measure: false, list: false });
  const working = (press: Press, now: boolean) => setBusy(held => (held[press] === now ? held : { ...held, [press]: now }));
  const ask = <T,>(press: Press, work: () => Promise<T>, done: (value: T) => void) => { const mine = line[press].next(); setProblem(null); working(press, true);
    work().then(v => { if (mine()) { working(press, false); done(v); } }, e => { if (mine()) { working(press, false); setProblem(e.message); } }); };
  const letGo = (...presses: Press[]) => presses.forEach(press => { line[press].drop(); working(press, false); });
  useEffect(() => { letGo('test', 'measure', 'list'); setProblem(null); }, [root]);
  const openFolder = (path?: string) => ask('list', () => api.browse(path), setBrowse);
  const closeList = () => { letGo('list'); setBrowse(null); };
  const paths = activeRun?.paths;
  const saved: string | null = activeRun?.persistence?.last_successful_save ?? null;   // ISO in UTC, as the backend writes it
  const tail = String(root).split(/[\\/]/).filter(Boolean).slice(-2).join('/');
  // ONE checkpoint interval, counted in evaluations OR in seconds (user request 2026-09-22). The number goes into the field
  // of the chosen unit and the other field is emptied - also the default of 200 evaluations (50 before record 7.280) that an
  // absent field means. The backend refuses both at once (validation.py, checkpoint_interval_both). Another unit carries
  // the number over: evaluations and seconds do not convert into each other.
  const every: Json = out.checkpoint_every_evaluations === undefined ? 200 : out.checkpoint_every_evaluations;
  const seconds: Json = out.checkpoint_every_seconds ?? null;
  const [by, setBy] = useState<Every>(() => seconds !== null && every === null ? 'seconds' : 'evaluations');
  useEffect(() => { if (seconds !== null && every === null) setBy('seconds'); else if (every !== null && seconds === null) setBy('evaluations'); }, [every, seconds]);
  const interval: Json = by === 'seconds' ? seconds : every;
  const setEvery = (unit: Every, v: Json) => set({ checkpoint_every_evaluations: unit === 'evaluations' ? v : null, checkpoint_every_seconds: unit === 'seconds' ? v : null });
  const both = every !== null && seconds !== null;          // only from a file or an older copy of the configuration
  // Branch record SIF-91: the experiments under the output root, from the run list, are Experiment ID's list, and one picked
  // sets the name and the ID together - the ID stood only in the Runs window (a tooltip, a run's Details), to be retyped and
  // its name matched by hand, and a wrong one was found only at Start.
  const experiments = useMemo(() => {
    const found = new Map<string, { runs: number; mock: boolean }>();
    for (const r of runs) { const name = String(r.experiment ?? ''); if (EXPERIMENT.test(name)) found.set(name, { runs: (found.get(name)?.runs ?? 0) + 1, mock: !!r.mock }); }
    return [...found];
  }, [runs]);
  // Branch record SIF-91 review: Start looks for a MOCK task's experiment under <root>/mock and a real task's under the root
  // itself (runs.py, paths.py data_root), so the list offers the loaded task's kind only - one of the other kind, picked from
  // it, was refused at Start, after a real run's question. With no task loaded (taskMock null) it offers both.
  const offered = taskMock === null ? experiments : experiments.filter(([, seen]) => seen.mock === taskMock);
  const named = out.experiment_id ? `${out.experiment_name ?? ''}__${out.experiment_id}` : null;
  const namedSeen = named ? experiments.find(([name]) => name === named)?.[1] : undefined;
  return (
    <Module id="output" title="Output settings" defaultOpen={false} summary={[out.experiment_name, tail ? `.../${tail}` : 'no output root'].filter(Boolean).join(' - ')}>
      {/* "Copy path" is a sibling of the label, not inside it: a button inside would become what the label's text clicks. Its
          word stands before it, so the button keeps its text and its place at the line's end (branch record SIF-94). */}
      <div className="field-head"><label htmlFor={OUTPUT_ROOT_ID} title="A backend directory inside an allowed root. Not a browser upload folder.">Output root</label>
        {copying.word('root')}<button className="text-link" title="Copy the output root to the clipboard" onClick={() => void copying.copyText(root, 'root')}>Copy path</button></div>
      <input id={OUTPUT_ROOT_ID} value={root} disabled={locked} onChange={e => set({ output_root: e.target.value })} />
      <div className="row"><button disabled={locked} onClick={() => openFolder()}>Browse allowed roots...</button>
        <button disabled={busy.test} onClick={() => { const at = root; if (at) ask('test', () => api.checkOutput(at, true), value => setTested({ root: at, value, at: clock() })); }}>
          {busy.test ? 'Testing...' : 'Test writability'}</button></div>
      {problem && <p className="error">{problem}</p>}
      {!testedHere && lookError && <p className="error">{lookError} <button onClick={retryLook}>Retry read</button></p>}
      {/* Continue... is where a run goes on since record 7.261; it said "A resumed run" (branch record SIF-60) */}
      {locked && <p className="hint">The run directory is locked while a run is active. A run that is continued writes back to its own folder.</p>}
      {/* The list says which folder it shows and can be closed; a folder's name is a link that opens it (it was a span
          drawn as plain text), ".." reads "Up one folder", "select" "Use this folder" (branch record SIF-60). The backend's
          path is null at the top, where the entries are the allowed roots. */}
      {busy.list && <p className="hint">Reading the folder...</p>}
      {browse && <><p className="hint">{browse.path ? `In ${browse.path}` : 'The allowed roots'} <button className="text-link" onClick={closeList}>Close</button></p>
        <ul className="tree">{browse.parent && <li><button className="text-link" title={`Open ${browse.parent}`} onClick={() => openFolder(browse.parent)}>Up one folder</button></li>}
        {/* "Use this folder" closes on the listing line too: the same root again changes nothing that would drop a folder on its way.
            It locks with the root (branch record SIF-91 review: a list opened before a Start still set the root under the run). */}
        {browse.entries.map((e: Json) => <li key={e.path}><button className="text-link" title="Open this folder" onClick={() => openFolder(e.path)}>{e.name}</button> <button disabled={locked} onClick={() => { set({ output_root: e.path }); closeList(); }}>Use this folder</button></li>)}</ul></>}
      {/* What the backend found for the root, as one line; the table behind it (record 7.179, design advice 3). Open at once when
          the root cannot be written. */}
      {check && <details className="more output-facts" open={!(check.allowed && check.writable)}><summary>{check.allowed && check.writable ? 'writable' : 'NOT writable'}{testedHere ? ` · tested ${testedHere.at}` : ''} · {bytes(check.free_bytes)} free{check.windows_path ? ` · ${check.windows_path}` : ''}</summary>
      <table className="grid small"><tbody>
        <tr><td>Resolved</td><td className="path">{check.resolved ?? '-'}</td></tr>
        <tr><td>Allowed / writable</td><td className={check.allowed && check.writable ? '' : 'error'}>{check.allowed ? 'yes' : 'no'} / {check.writable ? 'yes' : 'no'} {check.error ?? ''}</td></tr>
        <tr><td>Backend host</td><td>{check.host} ({check.environment}, {check.filesystem})</td></tr>
        <tr><td>Free space</td><td>{bytes(check.free_bytes)}; used here {sized && sized.root === root ? bytes(sized.bytes)
          : <button className="text-link" disabled={busy.measure} title="Adds up the files under the output root (on D: this takes a while for many runs)."
              onClick={() => { const at = root; ask('measure', () => api.checkOutput(at, false, undefined, true)
                // a backend from before record 7.189 refuses `usage` (422), and its plain look still carries the size
                .catch(e => e instanceof ApiError && e.status === 422 ? api.checkOutput(at, false) : Promise.reject(e)),
              v => setSized({ root: at, bytes: v.bytes_used ?? null })); }}>{busy.measure ? 'Measuring...' : 'Measure'}</button>}</td></tr>
        <tr><td>Windows path</td><td>{check.windows_path ?? <span className="hint">not shown: {check.windows_mapping}</span>}{check.windows_path && <span className="hint"> (verified by read-back)</span>}</td></tr>
        <tr><td>Mock data root</td><td className="path">{check.mock_data_root}</td></tr>
      </tbody></table></details>}
      <div className="row"><label>Experiment name<input value={out.experiment_name ?? ''} onChange={e => set({ experiment_name: e.target.value })} /></label>
        <label title="Set to append runs to an existing experiment; empty creates a new unique ID. Its list holds the experiments of the runs under the output root, of the loaded task's kind (MOCK or real): one picked sets the name too.">Experiment ID
          <input value={out.experiment_id ?? ''} placeholder="new" list="experiment-ids"
            onChange={e => { const picked = EXPERIMENT.exec(e.target.value); set(picked ? { experiment_name: picked[1], experiment_id: picked[2] } : { experiment_id: e.target.value || null }); }} /></label></div>
      <datalist id="experiment-ids">{offered.map(([name, seen]) => <option key={name} value={name} label={`${plural(seen.runs, 'run')}${seen.mock ? ', MOCK' : ''}`} />)}</datalist>
      {named && runs.length > 0 && (!namedSeen ? <p className="hint">No run listed here is in {named}: Start refuses an experiment that is not under the output root.</p>
        : taskMock !== null && namedSeen.mock !== taskMock && <p className="hint">{named} holds {namedSeen.mock ? 'MOCK' : 'real'} runs: Start of this {taskMock ? 'MOCK' : 'real'} task
          looks for it {taskMock ? "in the output root's mock/ folder" : 'in the output root itself, not its mock/ folder'} and refuses it.</p>)}
      {/* the run the tabs show, by its folder (branch record SIF-91: these settings are for the next Start since SIF-72) */}
      {paths && <details open><summary>Current run paths</summary>
        <p className="hint" title={activeRun.run_dir}>Of the run shown: {folderName(String(activeRun.run_dir ?? ''))}</p><table className="grid small"><tbody>
        {/* words, and the save in local time with the UTC in its tooltip, as Run status writes it (branch record SIF-60: the
            rows read "run_dir", "bytes written", "last successful save 2026-10-05T10:21:40+00:00"); a path says that a click
            copies it, as Run status's Run folder does (branch record SIF-64) */}
        {Object.entries(paths).map(([k, v]) => <tr key={k}><td title={k}>{pathName(k)}</td><td className="path" title="Click to copy" onClick={() => void copying.copyText(String(v), `path:${k}:${String(v)}`)}>{String(v)}{copying.word(`path:${k}:${String(v)}`)}</td></tr>)}
        <tr><td>Bytes written</td><td>{bytes(activeRun?.bytes_written ?? activeRun?.persistence?.bytes_written)}</td></tr>
        <tr><td>Last successful save</td><td title={saved ? `${saved} (UTC)` : undefined}>{stamp(saved) ?? saved ?? '-'}</td></tr>
        <tr><td>Remote Spectre work folder</td><td className="hint">local work/ for this task; final files are written directly here (sync: local)</td></tr>
      </tbody></table></details>}
      <p className="hint always-saved" title="Always saved: configuration/provenance snapshots, per-evaluation records, actual parameters, metrics, simulator-job accounting, run summary, event/error logs (Parquet + JSON).">Always saved: configuration, evaluations, logs.</p>
      <Check label="Learner-update log" value={out.save_learner_updates ?? true} onChange={v => set({ save_learner_updates: v })} />
      <Check label="Model checkpoints" value={out.save_checkpoints ?? true} onChange={v => set({ save_checkpoints: v })} />
      {/* Continue... and the Modes by their buttons' names, "weights only" in words (branch record SIF-60: "needed for a FULL
          resume", "checkpoints are weights_only: a full training-state resume of this run will NOT be possible") */}
      <Check label="Replay snapshots (needed to Continue a run exactly)" value={out.save_replay_snapshots ?? true} onChange={v => set({ save_replay_snapshots: v })} />
      {out.save_replay_snapshots === false && <p className="warn">Without replay snapshots this run's checkpoints are weights only: Continue... cannot pick it up exactly; Fine-tune and Evaluate only can still load its model.</p>}
      <Check label="Complete transition archive (independent of replay snapshots)" value={out.save_transition_archive ?? true} onChange={v => set({ save_transition_archive: v })} />
      <Check label="Experiment summary CSVs" value={out.export_summary_csv ?? true} onChange={v => set({ export_summary_csv: v })} />
      <Num label="Checkpoint every" nullable value={interval} placeholder="only at pause, stop, end" onChange={v => setEvery(by, v)}
        title="The model and its training state are saved every N evaluations or every S seconds - one of the two. Empty = only when the run pauses, stops or ends."
        after={<select aria-label="Checkpoint every: unit" value={by} onChange={e => { const unit = e.target.value as Every; setBy(unit);
          const carried = (unit === 'seconds' ? seconds : every) ?? interval; if (carried !== null) setEvery(unit, carried); }}>
          <option>evaluations</option><option>seconds</option></select>} />
      {both && <p className="warn">This configuration has both: every {every} evaluations and every {seconds} seconds. Only one can be kept - type a number or choose the unit, and the other is emptied.</p>}
      <label title="Raw PSF only; nothing is rendered. Applies to raw outputs that actually exist.">Raw waveform retention
        <select value={out.waveform_retention ?? 'best_and_failures'} onChange={e => set({ waveform_retention: e.target.value })}><option value="none">None</option>
          {/* the setting's words, its value unchanged (branch record SIF-35: the list showed "best_and_failures") */}
          <option value="best_and_failures">Best design and failures</option><option value="all">Every evaluation</option></select></label>
      {/* null is a real setting here (no limit); only a configuration without the field shows the backend's default. */}
      <ByteSize label="Waveform storage limit" empty="no limit" value={out.waveform_storage_limit_bytes === undefined ? 2147483648 : out.waveform_storage_limit_bytes}
        onChange={v => set({ waveform_storage_limit_bytes: v })}
        title="Oldest retained failures are removed first. The best design, models and primary data are never deleted automatically." />
    </Module>
  );
}
