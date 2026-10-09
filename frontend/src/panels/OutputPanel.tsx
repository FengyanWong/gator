// The right column's Output settings (plan-refactoring C4, out of Right.tsx).
import { useEffect, useState } from 'react';
import { useRequest } from '../store';
import { api, ApiError, copy, Json } from '../api';
import { bytes } from '../format';
import { OUTPUT_ROOT_ID } from '../contract';
import { ByteSize, Check, Module, Num } from './fields';
import { useNewest } from '../newest';

type Every = 'evaluations' | 'seconds';

export function OutputPanel({ config, setConfig, meta, activeRun }: { config: Json; setConfig: (f: (c: Json) => Json) => void; meta: Json; activeRun: Json }) {
  const out = config.output;
  const set = (fields: Json) => setConfig(c => ({ ...c, output: { ...c.output, ...fields } }));
  const root = out.output_root ?? meta?.output_root ?? '';
  const [browse, setBrowse] = useState<Json>(null);
  const locked = !!activeRun?.worker_alive;
  // The root is looked at 0.5 s after the last keystroke, and an answer for text typed before is dropped (useRequest):
  // whichever answer came last used to win, a half-typed path's too. A look no longer walks the folder for its size (record
  // 7.189: 0.7 to 2 s of disk work on D: at every page open, for one number in a closed fold): "Measure" asks for it.
  const { value: looked, error: lookError, refresh: retryLook } = useRequest<Json>(signal => api.checkOutput(root, false, signal), [root], { enabled: !!root, delay: 500 });
  const [tested, setTested] = useState<{ root: string; value: Json } | null>(null);     // "Test writability", for the root it was pressed for
  useEffect(() => setTested(null), [root]);                                             // another root: its own look replaces it, as before
  const [sized, setSized] = useState<{ root: string; bytes: number | null } | null>(null);   // "Measure", for the root it was pressed for
  const check: Json = tested && tested.root === root ? tested.value : looked;
  // Browse, a folder of its list and Test writability say what went wrong, as the other panels do (they used to say nothing).
  const [problem, setProblem] = useState<string | null>(null);
  // Only the newest press answers (two quick clicks in the folder list showed whichever came last), and a problem is
  // about the root it was pressed for: another root clears it.
  const pressed = useNewest();
  const ask = <T,>(work: () => Promise<T>, done: (value: T) => void) => { const mine = pressed.next(); setProblem(null);
    work().then(v => { if (mine()) done(v); }, e => { if (mine()) setProblem(e.message); }); };
  useEffect(() => { pressed.drop(); setProblem(null); }, [root]);
  const paths = activeRun?.paths;
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
  return (
    <Module id="output" title="Output settings" summary={[out.experiment_name, tail ? `.../${tail}` : 'no output root'].filter(Boolean).join(' - ')}>
      {/* "Copy path" is a sibling of the label, not inside it: a button inside would become what the label's text clicks. */}
      <div className="field-head"><label htmlFor={OUTPUT_ROOT_ID} title="A backend directory inside an allowed root. Not a browser upload folder.">Output root</label>
        <button className="text-link" title="Copy the output root to the clipboard" onClick={() => copy(root)}>Copy path</button></div>
      <input id={OUTPUT_ROOT_ID} value={root} disabled={locked} onChange={e => set({ output_root: e.target.value })} />
      <div className="row"><button disabled={locked} onClick={() => ask(() => api.browse(), setBrowse)}>Browse allowed roots...</button>
        <button onClick={() => { const at = root; if (at) ask(() => api.checkOutput(at, true), value => setTested({ root: at, value })); }}>Test writability</button></div>
      {problem && <p className="error">{problem}</p>}
      {!tested && lookError && <p className="error">{lookError} <button onClick={retryLook}>Retry read</button></p>}
      {locked && <p className="hint">The run directory is locked while a run is active. A resumed run writes back to its original directory.</p>}
      {browse && <ul className="tree">{browse.parent && <li onClick={() => ask(() => api.browse(browse.parent), setBrowse)}>..</li>}
        {browse.entries.map((e: Json) => <li key={e.path}><span onClick={() => ask(() => api.browse(e.path), setBrowse)}>{e.name}</span> <button onClick={() => { set({ output_root: e.path }); setBrowse(null); }}>select</button></li>)}</ul>}
      {/* What the backend found for the root, as one line; the table behind it (record 7.179, design advice 3). Open at once when
          the root cannot be written. */}
      {check && <details className="more output-facts" open={!(check.allowed && check.writable)}><summary>{check.allowed && check.writable ? 'writable' : 'NOT writable'} · {bytes(check.free_bytes)} free{check.windows_path ? ` · ${check.windows_path}` : ''}</summary>
      <table className="grid small"><tbody>
        <tr><td>Resolved</td><td className="path">{check.resolved ?? '-'}</td></tr>
        <tr><td>Allowed / writable</td><td className={check.allowed && check.writable ? '' : 'error'}>{String(check.allowed)} / {String(check.writable)} {check.error ?? ''}</td></tr>
        <tr><td>Backend host</td><td>{check.host} ({check.environment}, {check.filesystem})</td></tr>
        <tr><td>Free space</td><td>{bytes(check.free_bytes)}; used here {sized && sized.root === root ? bytes(sized.bytes)
          : <button className="text-link" title="Adds up the files under the output root (on D: this takes a while for many runs)."
              onClick={() => { const at = root; ask(() => api.checkOutput(at, false, undefined, true)
                // a backend from before record 7.189 refuses `usage` (422), and its plain look still carries the size
                .catch(e => e instanceof ApiError && e.status === 422 ? api.checkOutput(at, false) : Promise.reject(e)),
              v => setSized({ root: at, bytes: v.bytes_used ?? null })); }}>Measure</button>}</td></tr>
        <tr><td>Windows path</td><td>{check.windows_path ?? <span className="hint">not shown: {check.windows_mapping}</span>}{check.windows_path && <span className="hint"> (verified by read-back)</span>}</td></tr>
        <tr><td>Mock data root</td><td className="path">{check.mock_data_root}</td></tr>
      </tbody></table></details>}
      <div className="row"><label>Experiment name<input value={out.experiment_name ?? ''} onChange={e => set({ experiment_name: e.target.value })} /></label>
        <label title="Set to append runs to an existing experiment; empty creates a new unique ID.">Experiment ID<input value={out.experiment_id ?? ''} placeholder="new" onChange={e => set({ experiment_id: e.target.value || null })} /></label></div>
      {paths && <details open><summary>Current run paths</summary><table className="grid small"><tbody>
        {Object.entries(paths).map(([k, v]) => <tr key={k}><td>{k}</td><td className="path" onClick={() => copy(String(v))}>{String(v)}</td></tr>)}
        <tr><td>bytes written</td><td>{bytes(activeRun?.bytes_written ?? activeRun?.persistence?.bytes_written)}</td></tr>
        <tr><td>last successful save</td><td>{activeRun?.persistence?.last_successful_save ?? '-'}</td></tr>
        <tr><td>remote Spectre work dir</td><td className="hint">local work/ for this task; final files are written directly here (sync: local)</td></tr>
      </tbody></table></details>}
      <p className="hint always-saved" title="Always saved: configuration/provenance snapshots, per-evaluation records, actual parameters, metrics, simulator-job accounting, run summary, event/error logs (Parquet + JSON).">Always saved: configuration, evaluations, logs.</p>
      <Check label="Learner-update log" value={out.save_learner_updates ?? true} onChange={v => set({ save_learner_updates: v })} />
      <Check label="Model checkpoints" value={out.save_checkpoints ?? true} onChange={v => set({ save_checkpoints: v })} />
      <Check label="Replay snapshots (needed for a FULL resume)" value={out.save_replay_snapshots ?? true} onChange={v => set({ save_replay_snapshots: v })} />
      {out.save_replay_snapshots === false && <p className="warn">Without replay snapshots checkpoints are weights_only: a full training-state resume of this run will NOT be possible.</p>}
      <Check label="Complete transition archive (independent of replay snapshots)" value={out.save_transition_archive ?? true} onChange={v => set({ save_transition_archive: v })} />
      <Check label="Experiment summary CSVs" value={out.export_summary_csv ?? true} onChange={v => set({ export_summary_csv: v })} />
      <Num label="Checkpoint every" nullable value={interval} placeholder="only at pause, stop, end" onChange={v => setEvery(by, v)}
        title="The model and its training state are saved every N evaluations or every S seconds - one of the two. Empty = only when the run pauses, stops or ends."
        after={<select aria-label="Checkpoint every: unit" value={by} onChange={e => { const unit = e.target.value as Every; setBy(unit);
          const carried = (unit === 'seconds' ? seconds : every) ?? interval; if (carried !== null) setEvery(unit, carried); }}>
          <option>evaluations</option><option>seconds</option></select>} />
      {both && <p className="warn">This configuration has both: every {every} evaluations and every {seconds} seconds. Only one can be kept - type a number or choose the unit, and the other is emptied.</p>}
      <label title="Raw PSF only; nothing is rendered. Applies to raw outputs that actually exist.">Raw waveform retention
        <select value={out.waveform_retention ?? 'best_and_failures'} onChange={e => set({ waveform_retention: e.target.value })}><option>none</option><option>best_and_failures</option><option>all</option></select></label>
      {/* null is a real setting here (no limit); only a configuration without the field shows the backend's default. */}
      <ByteSize label="Waveform storage limit" empty="no limit" value={out.waveform_storage_limit_bytes === undefined ? 2147483648 : out.waveform_storage_limit_bytes}
        onChange={v => set({ waveform_storage_limit_bytes: v })}
        title="Oldest retained failures are removed first. The best design, models and primary data are never deleted automatically." />
    </Module>
  );
}
