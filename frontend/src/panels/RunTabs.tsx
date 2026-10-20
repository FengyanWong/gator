import { memo, useEffect, useRef, useState } from 'react';
import { Icon } from './Icons';
import { api, copy, download, downloadPackage, Json, saveJson } from '../api';
import { si } from '../units';
import { bytes, num, runName, short, sig, stamp, stopWords } from '../format';
import { ENDED, restingShown } from '../runState';
import { usePolling, useRequest } from '../store';
import { APPLY_AND_SAVE, calibrationPlan, savingText } from './calibrationPlan';
import { requestTaskSave } from './TaskSave';
import { ContinueForm } from './ContinueForm';
import { LaunchRefusal } from './LaunchRefusal';
import { KeyTile } from './fields';
import { MODE_NAME } from './rlModelText';

// llm_calls - the AI calls a run of the LLM search methods recorded (removed 2026-10-06, record 7.226) - stays in its run folder.
const TABLES = ['evaluations', 'parameters', 'metrics', 'simulator_jobs', 'learner_updates', 'transitions', 'states'];


// The spread needs two scored designs and the bonus a learner update: before that the line said "last 0 scored designs): ;".
// No check at all (a backend that sent none) shows nothing.
function SteeringCheck({ value }: { value: Json }) {
  if (!value) return null;
  if (value.reward_spread == null) return <div className="steering-check"><p className="hint">Reward spread: not enough scored designs yet.</p></div>;
  return <div className="steering-check"><p>Reward spread (p90 − p10, last {value.scored_designs} scored designs): <b>{sig(value.reward_spread)}</b>;
    exploration bonus (latest update): <b>{value.exploration_bonus == null ? 'no update yet' : sig(value.exploration_bonus)}</b>.</p>
    {value.verdict && <p className="warn">{value.verdict}</p>}</div>;
}

const limitText = (row: Json) => row.lower != null && row.upper != null ? `${si(row.lower, row.unit)} to ${si(row.upper, row.unit)}`
  : row.lower != null ? `\u2265 ${si(row.lower, row.unit)}` : `\u2264 ${si(row.upper, row.unit)}`;

/** The calibration of a Baseline simulation (record 7.197, every one since 7.202; backend calibration.py): from the
 *  run's random designs, a Scale per Specs row (the typical miss among the designs that miss the row) and the Initial alpha
 *  (0.1 x the reward's spread among them). The run applies nothing. Apply writes the proposals into the configuration this
 *  page holds - the Scale of the Specs rows that still are the rows the run simulated, and Initial alpha in the RL model window - as
 *  ONE Undo step; a task saved from a Virtuoso cell then needs Save task before it starts. What Apply does is worked out
 *  in calibrationPlan.ts, shared with the "Calibration ready" line under the header (record 7.204). A run of another task
 *  than the page holds shows its own Scales and Initial alpha, never the page's rows of the same ID (record 7.214).
 *  Record 7.217: for a task saved from a Virtuoso cell the press is "Apply and save" - Apply, then Save task as a press
 *  on it - with "Apply only" beside it; Scales are written as every quantity of the page is; and a result the backend
 *  worked out again under today's rule says so. */
function Calibration({ value, live, config, setConfig }: { value: Json; live: boolean; config: Json; setConfig: (next: Json | ((c: Json) => Json)) => void }) {
  const result: Json = value.result, request: Json = value.request ?? {};
  const [said, setSaid] = useState<string | null>(null);                      // what "Apply and save" answered, for this result
  useEffect(() => setSaid(null), [result?.run_id]);
  if (!result) return <div className="calibration"><h4>Calibration</h4><p className="hint">{live
    ? `${request.random_only ? "" : "After the baseline, "}${request.designs} random designs are simulated; the proposals appear here when the run has ended.`
    : 'This run ended without a calibration result.'}</p></div>;
  const designs: Json = result.designs ?? {};
  const { rows, scales, alpha, alphaNow, otherTask, pending, proposals, what, afterwards, saves, apply } = calibrationPlan(result, config);
  const applyAndSave = () => { setConfig(apply); setSaid(`Applied ${what}, as one Undo step.${savingText(requestTaskSave(config.circuit.task_id))}`); };
  return <div className="calibration">
    <h4>Calibration <span className="hint">from this run's random designs: {designs.scored} of {designs.simulated} gave a reward, {designs.passing} pass{designs.passing === 1 ? 'es' : ''} every hard spec</span></h4>
    {result.status !== 'calibrated' && <p className="warn">Nothing is proposed. {result.reason}</p>}
    {result.recalculated && <p className="hint recalculated">Worked out again from this run's recorded designs with today's rule; the run's own file keeps what it
      said at its end.</p>}
    {otherTask && <p className="hint other-task">This run calibrated <b>{result.task_key}</b>; the page holds {config.circuit.task_id}. The table shows the
      Scales the run had. To apply the proposals, choose {result.task_key} in the Tasks window.</p>}
    {result.scale_note && <p className="hint">{result.scale_note}</p>}
    {rows.length > 0 && <table className="grid small calibration-rows"><thead><tr>
      <th title="The Specs row, by its ID.">Specs row</th><th title="The row's limit, as the run had it.">Limit</th>
      <th title="How many of the random designs that measured this row are outside its limit.">Random designs that miss it</th>
      <th title="The median distance outside the limit, among the designs that miss it, in the row's unit.">Typical miss</th>
      {otherTask ? <th title="What the Scale box of this row held in the run. Empty = the size of the limit.">Scale in the run</th>
        : <th title="What the Scale box of this row holds on the page now. Empty = the size of the limit.">Scale now</th>}
      <th title="The typical miss, rounded to two digits: with it a typical failing random design counts as a miss of 1 on this row. A smaller Scale makes a miss on the row cost more, so the search keeps more distance from that limit.">Proposed Scale</th></tr></thead>
      <tbody>{rows.map(r => <tr key={r.metric_id}>
        <td>{r.metric_id}</td><td>{limitText(r)}</td><td>{r.misses} of {r.measured}{r.measured < designs.simulated && <span className="hint"> ({designs.simulated - r.measured} gave no value)</span>}</td>
        <td>{r.median_miss == null ? '-' : si(r.median_miss, r.unit)}</td>
        <td>{otherTask ? (r.scale_stated != null ? si(r.scale_stated, r.unit) : <span className="hint">empty</span>)
          : !r.target ? <span className="hint">no such row on the page</span> : r.target.normalization_scale != null ? si(r.target.normalization_scale, r.target.unit) : <span className="hint">empty</span>}</td>
        <td>{r.proposed_scale != null && <b>{si(r.proposed_scale, r.unit)}</b>}
          {r.proposed_scale != null && !r.same && !otherTask && <span className="warn"> not applied: {r.target ? 'the limits of this row were changed after the run' : 'the page has no row with this ID'}</span>}
          {r.note && <span className="hint">{r.proposed_scale != null ? ' ' : ''}{r.note}</span>}</td></tr>)}</tbody></table>}
    <p className="calibration-alpha">Initial alpha (RL model): {otherTask ? 'the run had' : 'now'} <b>{(otherTask ? alpha.used : alphaNow) ?? "the encoder's saved value"}</b>; proposed {alpha.proposed != null
      ? <><b>{short(alpha.proposed)}</b> <span className="hint">= 0.1 x the reward's spread among the random designs ({short(Number(Number(alpha.reward_sd).toPrecision(3)))}{scales.length || rows.some(r => r.proposed_scale != null) ? ', with the proposed scales' : ''})</span></>
      : <span className="hint">nothing{alpha.note ? `: ${String(alpha.note).replace(/^Not proposed: /, '')}` : '.'}</span>}{alpha.proposed != null && alpha.note && <span className="hint"> {alpha.note}</span>}</p>
    <div className="row">
      {saves ? <>
          <button className="primary" onClick={applyAndSave}
            title={`Apply and save: Writes ${what} into the page, as one Undo step, ${APPLY_AND_SAVE}`}>Apply and save</button>
          <button onClick={() => { setSaid(null); setConfig(apply); }}
            title="Apply only: Writes the proposed Scale into those Specs rows and the proposed Initial alpha into the RL model's Advanced, as one Undo step. Nothing is simulated and no task is saved. Use Apply and save to update this task, or Save as for a new task.">Apply only</button></>
        : <button disabled={!pending || otherTask} onClick={() => setConfig(apply)}
            title="Apply calibration: Writes the proposed Scale into those Specs rows and the proposed Initial alpha into the RL model's Advanced, as one Undo step. Nothing is simulated and no task is saved.">Apply calibration</button>}
      <span className="hint">{otherTask ? `Apply waits until the page holds ${result.task_key}.`
        : !proposals ? 'There is nothing to apply.'
        : !pending ? `The page holds these values.${said ? '' : afterwards}`
        : saves ? `Sets ${what}, as one Undo step; Apply and save also saves the task, so it can start.`
        : `Sets ${what}, as one Undo step.${afterwards}`}</span>
    </div>
    {said && <p className="hint calibration-said" role="status">{said}</p>}
  </div>;
}

/** The run the bottom tabs show. Its run commands live in the header only (Save now, Pause, Abort, Force abort): the
 *  four copies this tab had went on 2026-09-29 (user: fewer duplicate buttons). Continue... stays - it sets a new budget
 *  and also continues a stopped run, which the header cannot. Record 7.261 (the launcher): it opens the budget form
 *  instead of the browser's prompt; `continueBlocked` - why it cannot go now, the backend's continuation check included -
 *  is said beside it before any press, with the backend's `alternative` (a new run that fine-tunes from the save point)
 *  as a button; a refusal of the press stays under it (`refusal`) until the run changes. `check`: that continuation check. */
export function StatusTab({ status, runDir, error, check, continueBlocked, refusal, onContinue, onDismissRefusal, onFineTune, config, setConfig, ask = null }: {
  status: Json; runDir: string | null; error: string | null; check: Json | null; continueBlocked: string | null; refusal: Json | null;
  onContinue: (total: number | null) => void; onDismissRefusal: () => void; onFineTune: (alternative: Json) => void;
  config: Json; setConfig: (next: Json | ((c: Json) => Json)) => void; ask?: { runDir: string; serial: number } | null }) {
  const [asking, setAsking] = useState(false);                // the budget form is open
  useEffect(() => setAsking(false), [runDir]);
  // Continue... of the Runs window (record 7.267): the form opens for the run it was pressed for.
  useEffect(() => { if (ask && ask.runDir === runDir) setAsking(true); }, [ask?.serial]);
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
  // Continue... is worth a word while the run is at rest in a state it can go on from: a completed run too, once the
  // backend's continuation check can say whether a higher total is allowed (record 7.261).
  const resting = restingShown(status, check);
  return (<div className="status-grid">
    <SteeringCheck value={status.steering} />
    {status.manifest?.mock && <p className="mock">{status.manifest.mock_notice}</p>}
    {status.calibration && <Calibration value={status.calibration} live={!!status.worker_alive || !ENDED.includes(status.state)} config={config} setConfig={setConfig} />}
    {/* The run at a glance (record 7.360, the Roadster look): how far it is, then four numbers; the table below holds them all. */}
    {b && <div className="status-hero">
      <div className="status-hero-count">
        <span className="status-hero-state" title={status.stop_reason ?? undefined}>{status.state}{status.stop_reason ? ` · ${stopWords(status.stop_reason)}` : ''}</span>
        <span className="status-hero-number">{b.charged}<span className="of"> / {b.max_evaluations}</span></span>
        <span className="hint">evaluations charged · {b.in_flight} in flight · {b.failed} failed</span>
        <span className={`status-hero-bar${status.state === 'completed' ? ' done' : ['failed', 'cancelled', 'interrupted'].includes(status.state) ? ' bad'
          : ['paused', 'stopped'].includes(status.state) ? ' rest' : ''}`}><span style={{ width: `${b.max_evaluations ? Math.min(100, (100 * b.charged) / b.max_evaluations) : 0}%` }} /></span>
      </div>
      <div className="key-tiles">
        <KeyTile label="Spectre launches" value={b.launches} after={`retries ${b.retries} · cache hits ${b.cache_hits}`} />
        <KeyTile label="Learner updates" value={status.learner_updates ?? 0} />
        <KeyTile label="First feasible design" value={first ? first.first_feasible_eval_count : 'none yet'} before={first ? 'at' : undefined} after={first ? 'evaluations' : undefined} />
        <KeyTile label="Best design" value={!best ? 'none' : best.feasible ? 'feasible' : best.nominal_feasible ? 'nominal only' : 'infeasible'}
          after={best ? `hard violation ${num(best.violation)}` : undefined} />
      </div>
    </div>}
    <table className="grid small"><tbody>
      <tr><td>State</td><td title={status.stop_reason ?? undefined}><b>{status.state}</b>{status.stop_reason ? ` (${stopWords(status.stop_reason)})` : ''}{status.worker_alive ? ' - worker alive' : ''}</td></tr>
      {/* The Mode as the RL model window names it (branch record SIF-14: it wrote the key, "scratch (no weights loaded)"). */}
      <tr><td>Mode / model</td><td>{MODE_NAME[status.mode] ?? status.mode}{status.manifest?.source_model?.run_id ? ` - from run ${status.manifest.source_model.run_id.slice(0, 12)}, save point ${status.manifest.source_model.checkpoint_id}` : ' - no weights loaded'}</td></tr>
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
      <button className="continue-open" disabled={!!continueBlocked || asking} onClick={() => setAsking(true)}
        title={continueBlocked ? `Continue: ${continueBlocked}` : 'Continue: A paused, stopped or interrupted run - or a completed one, with a higher total - goes on in the '
          + 'same run folder, from its saved state, with its own saved configuration. The form asks for the total first.'}><Icon name="play" label="Continue..." /></button>
      {resting && continueBlocked && <span className="hint continue-why">{continueBlocked}</span>}
      {resting && check?.alternative && <button className="continue-alternative" onClick={() => onFineTune(check.alternative)}
        title={`${check.alternative.label}: The next run on this page loads this run's save point ${check.alternative.checkpoint_id} in Mode fine_tune, as one Undo step. Nothing starts until Start.`}>{check.alternative.label}</button>}
      <button onClick={() => saveJson(`${runName(status.run_dir)}__status.json`, { exported_utc: new Date().toISOString(), ...status })}
        title="Export status (JSON): Everything this tab shows, as it is right now, in one JSON file: state, budget, best design, connection, the run's manifest and summary."><Icon name="export" label="Export status (JSON)" /></button>
    </div>
    {asking && <ContinueForm used={check?.used ?? b?.charged ?? null} total={check?.total ?? b?.max_evaluations ?? null} blocked={continueBlocked}
      onContinue={total => { setAsking(false); onContinue(total); }} onCancel={() => setAsking(false)} />}
    {refusal && <LaunchRefusal refusal={refusal} onDismiss={onDismissRefusal} />}
  </div>);
}

/** `status`: the shown run's status as the page already polls it (App.tsx) - for the steering line only. This tab used to
 *  poll the same file again every 2 s, finished runs too. */
export function DataTab({ runDir, status }: { runDir: string | null; status: Json }) {
  const [table, setTable] = useState('evaluations');
  const { value: data, error, refresh } = useRequest<Json>(signal => api.table(runDir!, table, 25, signal), [runDir, table], { enabled: !!runDir });
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
    {data && <div className="scroll"><table className="grid small data-table"><thead><tr>{data.columns.map((c: string) => <th key={c}>{c}</th>)}</tr></thead>
      <tbody>{data.rows.map((r: Json, i: number) => <tr key={i}>{data.columns.map((c: string) => {
        // One line per row (record 7.158): an id ends in "..." - the whole value on hover, a click copies it - a time keeps
        // its full width, and no word is cut in two; a long hash used to wrap into a column of letters as tall as a paragraph.
        const object = typeof r[c] === 'object' && r[c] !== null, text = object ? JSON.stringify(r[c]) : num(r[c]);
        const id = /_id$/.test(c) && text !== '', time = /_(at|utc)$/.test(c);
        // A JSON value keeps to one line too (branch record SIF-4): it wrapped into a block 200 px tall.
        return <td key={c} className={id ? 'id-cell' : time ? 'time-cell' : object ? 'json-cell' : undefined} title={id || object ? `${text}\nClick to copy` : undefined}
          onClick={id || object ? () => copy(text) : undefined}>{text}</td>; })}</tr>)}</tbody></table></div>}
  </div>);
}

function FilesTabBody({ runDir }: { runDir: string | null }) {
  const { value: files, error, refresh } = useRequest<Json>(signal => api.files(runDir!, signal), [runDir], { enabled: !!runDir });
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
    <div className="scroll"><table className="grid small"><thead><tr><th>File</th><th>Size</th><th>Modified</th><th></th></tr></thead>
      <tbody>{files?.files.map((f: Json) => <tr key={f.path}><td>{f.path}</td><td>{bytes(f.bytes)}</td><td title={`${f.modified_utc} (UTC)`}>{stamp(f.modified_utc) ?? f.modified_utc.slice(0, 19)}</td><td><button disabled={saving === f.path} onClick={() => save(f.path)}
        title={`Download ${f.path}: This file as it is now, to the browser's download folder.`}><Icon name={saving === f.path ? 'wait' : 'download'} label={`Download ${f.path}`} /></button></td></tr>)}</tbody></table></div></div>);
}

const LOG_HIDDEN = ['time_utc', 'event', 'error', 'run_id', 'traceback'];
/** The log's lines, newest first. Each is keyed by what it says and how many identical lines came before it (record
 *  7.279): keyed by its place, every line was drawn again whenever one arrived at the top. */
function logLines(entries: Json[]) {
  const count = new Map<string, number>();
  return entries.map((e: Json) => {
    // This computer's time of day, as every other time on the page (branch record SIF-2; it was UTC, unsaid).
    const time = stamp(e.time_utc)?.slice(11) ?? (e.time_utc ?? '').slice(11, 19), name = e.event ?? e.error ?? '';
    const text = JSON.stringify(Object.fromEntries(Object.entries(e).filter(([k]) => !LOG_HIDDEN.includes(k))));
    const base = `${e.time_utc}|${name}|${text}`, n = (count.get(base) ?? 0) + 1;
    count.set(base, n);
    return { key: `${base}#${n}`, time, name, text };
  }).reverse();
}
const LogLine = memo(function LogLine({ time, name, text, error }: { time: string; name: string; text: string; error: boolean }) {
  return <div className={error ? 'error' : ''}><b>{time} {name}</b> {text}</div>;
});

function LogsTabBody({ runDir, alive }: { runDir: string | null; alive: boolean }) {
  const [kind, setKind] = useState('events');
  const [note, setNote] = useState<string | null>(null);
  // Read every 2 s while the worker lives; a run at rest is read once (when the tab opens, and once more when its worker
  // ends) - it used to be re-read every minute for as long as the tab stayed open.
  const { value, error, refresh } = usePolling(signal => api.logs(runDir!, kind, signal), alive ? 2000 : 0, !!runDir, [runDir, kind]);
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
    {error && <p className="error">{error} <button onClick={refresh}>Retry read</button></p>}
    <div className="scroll log">{logLines(value?.entries ?? []).map(line =>
      <LogLine key={line.key} time={line.time} name={line.name} text={line.text} error={kind === 'errors'} />)}</div></div>);
}

/** Memoised (record 7.279): their props are the run and whether its worker lives, so a status update - every 1.5 s while
 *  a run works - no longer draws the 200 log lines or the run's ~450 files again; their own reads still do. */
export const LogsTab = memo(LogsTabBody);
export const FilesTab = memo(FilesTabBody);
