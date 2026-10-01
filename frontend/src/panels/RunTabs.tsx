import { searchPhase } from './SearchSettings';
import { useEffect, useRef, useState } from 'react';
import { Icon } from './Icons';
import { api, bytes, copy, download, downloadPackage, Json, num, saveJson } from '../api';
import { usePolling, useRequest } from '../store';

const TABLES = ['evaluations', 'parameters', 'metrics', 'simulator_jobs', 'learner_updates', 'llm_calls', 'transitions', 'states'];

const runName = (runDir: string) => runDir.split(/[\\/]/).filter(Boolean).pop() ?? 'run';    // the run folder's own name, unique per run

// The spread needs two scored designs and the bonus a learner update: before that the line said "last 0 scored designs): ;".
// No check at all (a backend that sent none) shows nothing.
function SteeringCheck({ value }: { value: Json }) {
  if (!value) return null;
  if (value.reward_spread == null) return <div className="steering-check"><p className="hint">Reward spread: not enough scored designs yet.</p></div>;
  return <div className="steering-check"><p>Reward spread (p90 − p10, last {value.scored_designs} scored designs): <b>{num(value.reward_spread)}</b>;
    exploration bonus (latest update): <b>{value.exploration_bonus == null ? 'no update yet' : num(value.exploration_bonus)}</b>.</p>
    {value.verdict && <p className="warn">{value.verdict}</p>}</div>;
}

/** The run the bottom tabs show. Its run commands live in the header only (Save now, Pause, Abort, Force abort): the
 *  four copies this tab had went on 2026-09-29 (user: fewer duplicate buttons). Continue stays - it sets a new budget and
 *  also continues a stopped run, which the header cannot. `continueBlocked`: why Continue waits (the header is busy with
 *  another run), or null. */
export function StatusTab({ status, runDir, error, onContinue, continueBlocked }: { status: Json; runDir: string | null; error: string | null;
  onContinue: () => void; continueBlocked: string | null }) {
  // A run chosen whose answer is still on its way, or whose status cannot be read now, is said as such: this line used
  // to read "No run selected." while the strip below named the run.
  if (!status) return <p className="hint">{!runDir ? 'No run selected.' : error ? `The status of this run could not be read: ${error}` : 'Reading the run...'}</p>;
  const b = status.budget, best = status.best_design, first = status.first_feasible, conn = status.connection;
  const firstNominal = b?.first_nominal_feasible;
  const firstCost = (event: Json) => event
    ? `at ${event.first_feasible_eval_count} evaluations charged (dispatch #${event.dispatch_index}, ${event.completed_count} completed, ${event.in_flight_count} in flight, ${event.spectre_launches} launches)`
    : 'not observed';
  const executedReward = status.summary?.reward;
  const hasV2 = Object.prototype.hasOwnProperty.call(b ?? {}, 'first_nominal_feasible');
  const continuable = !status.worker_alive && ['paused', 'stopped', 'interrupted'].includes(status.state);
  return (<div className="status-grid">
    <SteeringCheck value={status.steering} />
    {status.manifest?.mock && <p className="mock">{status.manifest.mock_notice}</p>}
    <table className="grid small"><tbody>
      <tr><td>State</td><td><b>{status.state}</b>{status.stop_reason ? ` (${status.stop_reason})` : ''}{status.worker_alive ? ' - worker alive' : ''}</td></tr>
      {status.search && <tr><td>Search</td><td>{searchPhase(status.search)} · LLM {status.search.calls} / {status.search.max_calls}</td></tr>}
      <tr><td>Mode / model</td><td>{status.mode} {status.manifest?.source_model?.run_id ? `from ${status.manifest.source_model.run_id.slice(0, 12)} / ${status.manifest.source_model.checkpoint_id}` : '(no weights loaded)'}</td></tr>
      <tr><td>Budget</td><td>{b ? `${b.charged} charged / ${b.max_evaluations}  (in flight ${b.in_flight}, completed ${b.completed}, failed ${b.failed}, remaining ${b.remaining})` : '-'}</td></tr>
      <tr><td>Spectre launches</td><td>{b ? `${b.launches}${b.max_launches ? ' / ' + b.max_launches : ''}  (retries ${b.retries}, cache hits ${b.cache_hits})` : '-'}</td></tr>
      {b && <tr><td>Launch accounting</td><td>{b.confirmed_launches ?? b.launches} confirmed, {b.uncertain_launches ?? 0} uncertain, {b.reserved_launches ?? 0} reserved</td></tr>}
      <tr><td>Active workers</td><td>{(status.active_workers ?? []).map((w: Json) => `#${w.worker_id}: ${w.phase} attempt ${w.attempt}`).join('; ') || 'none'} (concurrency {status.concurrency})</td></tr>
      <tr><td>Learner updates</td><td>{status.learner_updates}</td></tr>
      {executedReward?.version === 'constraint_violation_v2' && <tr><td>Executed reward</td><td>{executedReward.settings.violation_shape}; worst hard-spec share {num(executedReward.settings.worst_spec_share)}; objective weight {num(executedReward.settings.objective_weight)}; margin weight {num(executedReward.settings.margin_weight)}</td></tr>}
      <tr><td>{hasV2 ? 'First full-plan feasibility' : 'First feasibility (recorded)'}</td><td>{firstCost(first)}</td></tr>
      <tr><td>First nominal feasibility</td><td>{firstNominal ? firstCost(firstNominal) : hasV2 ? 'not observed' : 'unknown (historical run)'}</td></tr>
      <tr><td>Best design</td><td>{best ? `${best.feasible ? best.conditions_complete === true ? 'Full-plan feasible' : 'Feasible (coverage unknown)' : best.nominal_feasible ? 'Nominal feasible only' : 'Infeasible'}; reward ${num(best.reward)}; hard violation ${num(best.violation)}` : 'none'}</td></tr>
      {best && <tr><td>Conditions</td><td>Nominal: {best.nominal_feasible == null ? 'unknown' : best.nominal_feasible ? 'pass' : 'fail'}; robust: {best.robust_feasible == null ? 'not evaluated' : best.robust_feasible ? 'pass' : 'fail'}; coverage: {best.conditions_complete == null ? 'unknown' : best.conditions_complete ? 'complete' : 'partial'}</td></tr>}
      {best && <tr><td>Conditions evaluated / planned</td><td>{best.conditions_evaluated ?? 'unknown'} / {best.conditions_planned ?? 'unknown'}</td></tr>}
      {best && <tr><td>{best.worst_metrics ? 'Worst applicable values' : 'Recorded values'}</td><td>{Object.entries(best.worst_metrics ?? best.metrics ?? {}).map(([k, v]) => `${k}=${num(v)} ${best.metric_units?.[k] ?? ''}`).join('; ')}</td></tr>}
      {best?.nominal_metrics && <tr><td>Nominal values</td><td>{Object.entries(best.nominal_metrics).filter(([k]) => k in (best.metrics ?? {})).map(([k, v]) => `${k}=${num(v)} ${best.metric_units?.[k] ?? ''}`).join('; ')}</td></tr>}
      {best && <tr><td>Tightest clearance</td><td>{num(best.clearance_margin)} {best.tightest_clearance_spec ?? ''}</td></tr>}
      <tr><td>Connection</td><td><span className={`badge state-${conn?.overall}`}>{conn?.overall}</span>{conn?.age_seconds != null && ` ${Math.round(conn.age_seconds)} s old`}</td></tr>
      <tr><td>Persistence</td><td className={status.persistence?.failed ? 'error' : ''}>{status.persistence ? `commit ${status.persistence.last_commit_seq}, flushed ${status.persistence.flushed_seq}, ${bytes(status.persistence.bytes_written)} table data; last save ${status.persistence.last_successful_save ?? '-'}` : '-'} {status.persistence?.failed ?? ''}</td></tr>
      <tr><td>Last checkpoint</td><td>{status.last_checkpoint_utc ?? '-'}
        {status.manual_save && <span className={status.manual_save.state === 'saved' ? 'ok' : 'warn'}> - Save now: {status.manual_save.state === 'saved'
          ? `saved at ${status.manual_save.evaluations} evaluations (${status.manual_save.checkpoint_id})`
          : 'requested, waiting for the simulation in flight to finish'}</span>}</td></tr>
      <tr><td>Run directory</td><td className="path" onClick={() => copy(status.run_dir)}>{status.run_dir}</td></tr>
      {status.error && <tr><td>Error</td><td className="error">{status.error}</td></tr>}
    </tbody></table>
    <div className="row">
      <button disabled={!continuable || !!continueBlocked} onClick={onContinue}
        title={continuable && continueBlocked ? `Continue: ${continueBlocked}`
          : 'Continue: A paused, stopped or interrupted run goes on in the same run folder, from its saved state, with its own saved configuration.'}><Icon name="play" label="Continue" /></button>
      <button onClick={() => saveJson(`${runName(status.run_dir)}__status.json`, { exported_utc: new Date().toISOString(), ...status })}
        title="Export status (JSON): Everything this tab shows, as it is right now, in one JSON file: state, budget, best design, connection, the run's manifest and summary."><Icon name="export" label="Export status (JSON)" /></button>
    </div>
  </div>);
}

/** `status`: the shown run's status as the page already polls it (App.tsx) - for the steering line only. This tab used to
 *  poll the same file again every 2 s, finished runs too. */
export function DataTab({ runDir, status }: { runDir: string | null; status: Json }) {
  const [table, setTable] = useState('evaluations');
  const { value: data, error, refresh } = useRequest<Json>(() => api.table(runDir!, table), [runDir, table], { enabled: !!runDir });
  const [note, setNote] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  useEffect(() => setNote(null), [runDir, table]);
  if (!runDir) return <p className="hint">No run selected.</p>;
  // An export writes the file(s) on the backend's disk AND hands the browser a copy: nobody has to look the file up afterwards.
  const exporting = (what: string, work: () => Promise<string>) => { setBusy(what); setNote(null); work().then(setNote, e => setNote(e.message)).finally(() => setBusy(null)); };
  const exportCsv = () => exporting('csv', async () => {
    const written = await api.exportCsv(runDir, table);
    return `Downloaded ${await download(api.downloadUrl(runDir, written.relative), `${table}.csv`)}. Also kept in the run folder: ${written.relative}`; });
  const exportResearch = () => exporting('research', async () => {
    const written = await api.exportAggregates(runDir);
    return `Downloaded ${await download(api.aggregatesUrl(runDir), 'aggregates.zip')} (${Object.keys(written.files).length} tables). Also kept in ${written.experiment_dir}/aggregates`; });
  return (<div>
    <SteeringCheck value={status?.steering} />
    <div className="row"><select value={table} onChange={e => setTable(e.target.value)}>{TABLES.map(t => <option key={t}>{t}</option>)}</select>
      <button onClick={refresh} title="Refresh: Read this table again."><Icon name="refresh" label="Refresh" /></button>
      <button disabled={!!busy} onClick={exportCsv} title="Export detailed CSV: The whole table, every row and not only the ones shown here. Written to the run folder (exports/) and downloaded."><Icon name={busy === 'csv' ? 'wait' : 'csv'} label={busy === 'csv' ? 'Exporting...' : 'Export detailed CSV'} /></button>
      <button disabled={!!busy} onClick={exportResearch} title="Export research CSVs: The summary tables over every run of this experiment: run summary, success per budget, paired runs, transfer summary, cumulative cost. Written to the experiment's aggregates folder and downloaded as one zip."><Icon name={busy === 'research' ? 'wait' : 'zip'} label={busy === 'research' ? 'Exporting...' : 'Export research CSVs'} /></button>
      <span className="hint">{data ? `${data.total_rows} rows (snapshot at commit ${data.cutoff_commit_seq}); last ${data.rows.length} shown.` : ''} {error ?? note}</span></div>
    {data && <div className="scroll"><table className="grid small"><thead><tr>{data.columns.map((c: string) => <th key={c}>{c}</th>)}</tr></thead>
      <tbody>{data.rows.map((r: Json, i: number) => <tr key={i}>{data.columns.map((c: string) => <td key={c}>{typeof r[c] === 'object' && r[c] !== null ? JSON.stringify(r[c]) : num(r[c])}</td>)}</tr>)}</tbody></table></div>}
  </div>);
}

export function FilesTab({ runDir }: { runDir: string | null }) {
  const { value: files, error, refresh } = useRequest<Json>(() => api.files(runDir!), [runDir], { enabled: !!runDir });
  const [note, setNote] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);          // the file whose download is on its way
  useEffect(() => setNote(null), [runDir]);
  if (!runDir) return <p className="hint">No run selected.</p>;
  const pack = () => { setNote('Packing...'); downloadPackage(runDir).then(name => setNote(`Downloaded ${name}.`), e => setNote(e.message)); };
  // One file (user request 2026-09-26: a button with the download icon in each row, not a "download" text link), saved
  // like the package and the logs: the browser's own download, named by the backend, and said in the hint.
  const save = (file: string) => { setSaving(file); download(api.downloadUrl(runDir, file), file.split('/').pop() ?? file)
    .then(name => setNote(`Downloaded ${name}.`), e => setNote(e.message)).finally(() => setSaving(null)); };
  return (<div><div className="row"><button onClick={refresh} title="Refresh: Read the run folder again."><Icon name="refresh" label="Refresh" /></button>
    <button disabled={note === 'Packing...'} onClick={pack} title="Download data-only package (.zip): Every data file of this run in one zip, named after the run; no plots, nothing drawn."><Icon name={note === 'Packing...' ? 'wait' : 'download'} label="Download data-only package (.zip)" /></button>
    <button onClick={() => copy(runDir)} title="Copy run path: The run folder's path, as text, to the clipboard."><Icon name="copy" label="Copy run path" /></button><span className="hint">{files && `${files.files.length} files, ${bytes(files.total_bytes)}.`} {error ?? note} "Open local folder" is not offered: no desktop integration is available from a browser.</span></div>
    <div className="scroll"><table className="grid small"><thead><tr><th>File</th><th>Size</th><th>Modified (UTC)</th><th></th></tr></thead>
      <tbody>{files?.files.map((f: Json) => <tr key={f.path}><td>{f.path}</td><td>{bytes(f.bytes)}</td><td>{f.modified_utc.slice(0, 19)}</td><td><button disabled={saving === f.path} onClick={() => save(f.path)}
        title={`Download ${f.path}: This file as it is now, to the browser's download folder.`}><Icon name={saving === f.path ? 'wait' : 'download'} label={`Download ${f.path}`} /></button></td></tr>)}</tbody></table></div></div>);
}

export function LogsTab({ runDir, alive }: { runDir: string | null; alive: boolean }) {
  const [kind, setKind] = useState('events');
  const [note, setNote] = useState<string | null>(null);
  // Read every 2 s while the worker lives; a run at rest is read once (when the tab opens, and once more when its worker
  // ends) - it used to be re-read every minute for as long as the tab stayed open.
  const { value, refresh } = usePolling(() => api.logs(runDir!, kind), alive ? 2000 : 0, !!runDir, [runDir, kind]);
  // That last read starts after the worker ended: a read already on its way then was kept, and could miss the last lines
  // (review of 2026-10-01).
  const before = useRef({ runDir, alive });
  useEffect(() => {
    const was = before.current; before.current = { runDir, alive };
    if (was.alive && !alive && was.runDir === runDir) refresh();
  }, [runDir, alive]);
  useEffect(() => setNote(null), [runDir, kind]);
  if (!runDir) return <p className="hint">No run selected.</p>;
  // The list below is only the newest 200 entries; the file is the whole log, one JSON record per line. A healthy run has an
  // errors file with nothing in it: that is said, not saved as an empty file.
  const nothing = `Nothing to download: this run has logged no ${kind} so far.`;
  const save = () => value?.kind === kind && !value.entries.length ? setNote(nothing)
    : download(api.downloadUrl(runDir, `logs/${kind}.jsonl`), `${kind}.jsonl`).then(name => setNote(`Downloaded ${name}.`), e => setNote(e.status === 404 ? nothing : e.message));
  return (<div><div className="row"><select value={kind} onChange={e => setKind(e.target.value)}><option>events</option><option>errors</option></select>
    <button onClick={save} title={`Download full log (${kind}.jsonl): The whole log file of this run, not only the newest 200 entries listed here. One JSON record per line.`}><Icon name="download" label={`Download full log (${kind}.jsonl)`} /></button>
    <span className="hint">{note ?? 'Newest first, the newest 200 entries at most.'}</span></div>
    <div className="scroll log">{(value?.entries ?? []).slice().reverse().map((e: Json, i: number) => <div key={i} className={kind === 'errors' ? 'error' : ''}>
      <b>{(e.time_utc ?? '').slice(11, 19)} {e.event ?? e.error}</b> {JSON.stringify(Object.fromEntries(Object.entries(e).filter(([k]) => !['time_utc', 'event', 'error', 'run_id', 'traceback'].includes(k))))}</div>)}</div></div>);
}
