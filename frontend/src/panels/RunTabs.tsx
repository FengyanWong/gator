import { memo, useEffect, useRef, useState } from 'react';
import { Icon } from './Icons';
import { api, copy, download, downloadPackage, Json, saveJson } from '../api';
import { quantity, si, variables } from '../units';
import { bytes, clock, CONNECTION_STATE, count, durationWhole, FAILED_WHERE, failedWhere, num, plural, runName, short, sig, stamp, stopWords, timeLine, TIME_LINE_HELP } from '../format';
import { cardLive, ENDED, restingShown } from '../runState';
import { usePolling, useRequest } from '../store';
import { APPLY_AND_SAVE, calibrationPlan, savingText } from './calibrationPlan';
import { requestTaskSave } from './TaskSave';
import { ContinueForm } from './ContinueForm';
import { LaunchRefusal } from './LaunchRefusal';
import { KeyTile } from './fields';
import { useCopied } from './copied';
import { MODE_NAME, REWARD_NAME, REWARD_NAMES, runMode, runTrains } from './rlModelText';
import { sortKeys, useTableView } from './TableView';

// llm_calls - the AI calls a run of the LLM search methods recorded (removed 2026-10-06, record 7.226) - stays in its run folder.
const TABLES = ['evaluations', 'parameters', 'metrics', 'simulator_jobs', 'learner_updates', 'transitions', 'states'];


// The spread needs two scored designs and the bonus a learner update: before that the line said "last 0 scored designs): ;".
// No check at all (a backend that sent none) shows nothing. Said for the run it is, `status` (branch record SIF-137): a
// Baseline, a Calibration and an Evaluate only run make no learner update and read "no update yet" to their end, and an
// ended run said "yet" too, as "First feasible design" did before SIF-54. An ended run's verdict - the backend's words, as
// they are - read in present-tense orange with nothing to act on: it is said as what it was at the end, with what gives
// the next run room to learn.
const ROOM_TO_LEARN = 'A larger Evaluation budget, or the Initial alpha a Calibration proposes, gives the next run room to learn.';
function SteeringCheck({ status }: { status: Json }) {
  const value = status?.steering;
  if (!value) return null;
  const ended = ENDED.includes(status.state) && !status.worker_alive, trains = runTrains({ run_kind: status.manifest?.run_kind, mode: status.mode });
  if (value.reward_spread == null) return <div className="steering-check"><p className="hint">Reward spread: not enough scored designs{ended ? '' : ' yet'}.</p></div>;
  return <div className="steering-check"><p>Reward spread (p90 − p10, last {value.scored_designs} scored designs): <b>{sig(value.reward_spread)}</b>;
    {trains ? <> exploration bonus (latest update): <b>{value.exploration_bonus != null ? sig(value.exploration_bonus) : ended ? 'no update was made' : 'no update yet'}</b>.</>
      : <> exploration bonus: <b>none</b> (this run does not train).</>}</p>
    {trains && value.verdict && (ended ? <p className="hint steering-verdict">At its end: {value.verdict} {ROOM_TO_LEARN}</p>
      : <p className="warn steering-verdict">{value.verdict}</p>)}</div>;
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

/** What "First feasible design" counts (branch record SIF-116): the evaluations used when the first design meeting every hard
 *  spec came back (budget.py mark_first_feasible: those charged, in flight included), the design an episode starts from
 *  among them. Beside the Training tab's "First passing design", an evaluation number that leaves episode starts out, its
 *  "at 4 evaluations" for one run read as a contradiction. */
const FIRST_FEASIBLE_TIP = 'The evaluations used by the time the first design that met every hard spec came back: every design sent to the simulator '
  + 'by then counts, those still in flight too, and so does the design an episode starts from. The facts below give its dispatch number. The Training '
  + 'tab\'s "First passing design" is an evaluation number instead, and leaves episode starts out.';

/** The run the bottom tabs show. Its run commands live in the header only (Save now, Pause, Abort, Force abort): the
 *  four copies this tab had went on 2026-09-29 (user: fewer duplicate buttons). Continue... stays - it sets a new budget
 *  and also continues a stopped run, which the header cannot. Record 7.261 (the launcher): it opens the budget form
 *  instead of the browser's prompt; `continueBlocked` - why it cannot go now, the backend's continuation check included -
 *  is said beside it before any press, with the backend's `alternative` (a new run that fine-tunes from the save point)
 *  as a button; a refusal of the press stays under it (`refusal`) until the run changes. `check`: that continuation check.
 *  `onShowCause`: a failed run's Show errors or Show evaluations - the bottom panel opens Logs on the errors log, or Data
 *  tables on the evaluations (branch record SIF-137). */
export function StatusTab({ status, runDir, error, check, continueBlocked, refusal, onContinue, onDismissRefusal, onFineTune, config, setConfig, ask = null, onAsked, onShowCause }: {
  status: Json; runDir: string | null; error: string | null; check: Json | null; continueBlocked: string | null; refusal: Json | null;
  onContinue: (total: number | null) => void; onDismissRefusal: () => void; onFineTune: (alternative: Json) => void;
  config: Json; setConfig: (next: Json | ((c: Json) => Json)) => void; ask?: { runDir: string; serial: number } | null;
  onAsked?: (serial: number) => void; onShowCause?: (where: 'evaluations' | 'errors') => void }) {
  const [asking, setAsking] = useState(false);                // the budget form is open
  useEffect(() => setAsking(false), [runDir]);
  // Continue... of the Runs window (record 7.267): the form opens for the run it was pressed for, once - `onAsked` marks the
  // request answered, so a return to this tab does not open it again (branch record SIF-90).
  useEffect(() => { if (ask && ask.runDir === runDir) { setAsking(true); onAsked?.(ask.serial); } }, [ask?.serial]);
  // The form closed by Cancel, Escape or its Continue gives the keyboard back to Continue... (branch record SIF-90): the
  // focused field went with the form, and focus fell to the page's top. A run that went on has Continue... off by then, so
  // its tab button takes the focus instead.
  const continueRef = useRef<HTMLButtonElement>(null);
  const closeForm = () => {
    setAsking(false);
    requestAnimationFrame(() => (continueRef.current && !continueRef.current.disabled ? continueRef.current
      : document.querySelector<HTMLButtonElement>('footer .tabs button.active'))?.focus());
  };
  // The run folder's path was copied by a click, for 1.5 s, as the Runs window says it (branch record SIF-54: it copied unsaid);
  // a refused copy says "could not copy" (branch record SIF-94). Keyed by the path: another run's folder says nothing.
  const copying = useCopied();
  // A run chosen whose answer is still on its way, or whose status cannot be read now, is said as such: this line used
  // to read "No run selected." while the strip below named the run.
  if (!status) return <p className="hint">{!runDir ? 'No run selected.' : error ? `The status of this run could not be read: ${error}` : 'Reading the run...'}</p>;
  const b = status.budget, best = status.best_design, first = status.first_feasible, conn = status.connection, saved = status.persistence;
  const firstNominal = b?.first_nominal_feasible;
  // "used", as the Continue... form and the Abort question count the budget (branch record SIF-76: here alone it read "charged");
  // one as one (SIF-76 review: a baseline feasible at once read "at 1 evaluations used"); the counts as the page writes them,
  // the dispatch number as it is: it names one design (branch record SIF-117)
  const firstCost = (event: Json) => event
    ? `at ${plural(event.first_feasible_eval_count, 'evaluation')} used (dispatch #${event.dispatch_index}, ${count(event.completed_count)} completed, ${count(event.in_flight_count)} in flight, ${plural(event.spectre_launches, 'launch', 'launches')})`
    : 'not observed';
  const executedReward = status.summary?.reward;
  // The facts below in the page's words (branch record SIF-38): a number to three digits, a value in its unit as the editors
  // write it (1.28 GHz, not "1.28318e+9 Hz"; a ratio without a "1"), times in this computer's time with UTC in the tooltip.
  const few = (v: Json) => typeof v === 'number' ? sig(v) : v == null ? '-' : String(v);
  const metric = (k: string, v: Json) => { const u = best?.metric_units?.[k];
    return `${k} = ${typeof v === 'number' && u && u !== '1' ? quantity(v, u, 3) : few(v)}`; };
  const metricKeys = Object.keys(best?.worst_metrics ?? best?.metrics ?? {});
  const nominalKeys = [...metricKeys, ...Object.keys(best?.nominal_metrics ?? {}).filter(k => !metricKeys.includes(k))]
    .filter(k => k in (best?.nominal_metrics ?? {}) && k in (best?.metrics ?? {}));   // the order of the row above
  const hasV2 = Object.prototype.hasOwnProperty.call(b ?? {}, 'first_nominal_feasible');
  // The run's kind first (branch record SIF-44): a baseline or a calibration has mode "scratch" and read "New model - no
  // weights loaded"; it loads no model at all, so it is named alone.
  const modeWords = runMode({ run_kind: status.manifest?.run_kind, mode: status.mode });
  // Continue... is worth a word while the run is at rest in a state it can go on from: a completed run too, once the
  // backend's continuation check can say whether a higher total is allowed (record 7.261).
  const resting = restingShown(status, check);
  // The working time and the time left, as the run brief's card says them (branch record SIF-98: they stood only there, a
  // window to open for the one number asked for most); live by the brief's rule, so the two agree on one status.
  const time = b ? timeLine(status.active_seconds, b.charged, b.max_evaluations, cardLive(status, null)) : null;
  // The best design's sizes, as the Runs window's Details list them (branch record SIF-98: the fact a sizing run exists for was
  // there alone, a window, a run among hundreds and Details away); copied by a click, as the Run folder.
  const sizes = best?.variables ? variables(best.variables) : '', sizesKey = `best design variables of ${status.run_dir}`;
  // What to do after a failure (branch record SIF-137): Run status said only that a failed run cannot be continued, and every
  // real failure ends there. Where the run wrote what went wrong (format.ts `failedWhere`), with a Show button that opens
  // that log or table - only where the panel looks -, then the next run by the button that starts it: a Calibration or a
  // baseline is no run Start makes, and has no model for Load run to bring (lineage.ts).
  const failed = !status.worker_alive && status.state === 'failed', where = failed ? failedWhere(status.stop_reason) : null;
  const kind = status.manifest?.run_kind;
  const nextRun = kind === 'calibration' ? 'press Calibration again.' : kind === 'baseline_preflight' ? 'run the baseline again (Retry baseline, shown with its task).'
    : `Start a new run${status.save_point ? `; Load run in Runs... brings this run's model into it (${MODE_NAME.fine_tune} or ${MODE_NAME.frozen}).` : '.'}`;
  return (<div className="status-grid">
    <SteeringCheck status={status} />
    {status.manifest?.mock && <p className="mock">{status.manifest.mock_notice}</p>}
    {status.calibration && <Calibration value={status.calibration} live={!!status.worker_alive || !ENDED.includes(status.state)} config={config} setConfig={setConfig} />}
    {/* The run at a glance (record 7.360, the Roadster look): how far it is, then four numbers; the table below holds them all.
        Its counts and the table's as the page writes every count, from 10,000 up in groups of three (branch record SIF-117:
        "Learner updates 6024" here beside the RL model window's "6,024 learner updates" for the same model); a count the
        status does not give is "?", as the run brief writes one (SIF-117 review: an offline-trained model's status gives its
        budget as the evaluations used and the launches alone, and the others read "0 / undefined", "undefined in flight"). */}
    {b && <div className="status-hero">
      <div className="status-hero-count">
        <span className="status-hero-state" title={status.stop_reason ?? undefined}>{status.state}{status.stop_reason ? ` · ${stopWords(status.stop_reason)}` : ''}</span>
        <span className="status-hero-number">{count(b.charged)}<span className="of"> / {b.max_evaluations != null ? count(b.max_evaluations) : '?'}</span></span>
        <span className="hint" title="A design counts against the budget once it is sent to the simulator, whether it then completes, fails or is cancelled.">
          evaluations used · {b.in_flight != null ? count(b.in_flight) : '?'} in flight · {b.failed != null ? count(b.failed) : '?'} failed</span>
        <span className={`status-hero-bar${status.state === 'completed' ? ' done' : ['failed', 'cancelled', 'interrupted'].includes(status.state) ? ' bad'
          : ['paused', 'stopped'].includes(status.state) ? ' rest' : ''}`}><span style={{ width: `${b.max_evaluations ? Math.min(100, (100 * b.charged) / b.max_evaluations) : 0}%` }} /></span>
        {/* under the bar, apart from the budget's words above it (export_check reads those whole) */}
        {time && <span className="status-hero-time" title={`${TIME_LINE_HELP} The time left is the working time per evaluation so far, times the evaluations left.`}>{time}</span>}
      </div>
      <div className="key-tiles">
        <KeyTile label="Spectre launches" value={count(b.launches)} after={`retries ${count(b.retries)} · cache hits ${count(b.cache_hits)}`} />
        <KeyTile label="Learner updates" value={count(status.learner_updates ?? 0)} />
        {/* "none yet" only while the run can still find one (branch record SIF-54: an ended run said it too). What it counts, in
            its words - "at 4 evaluations used", as the facts below - and in its tooltip (branch record SIF-116); one as one
            (SIF-76 review): the noun is plural()'s, its number the tile's value */}
        <KeyTile label="First feasible design" value={first ? count(first.first_feasible_eval_count) : ENDED.includes(status.state) && !status.worker_alive ? 'none' : 'none yet'} before={first ? 'at' : undefined}
          after={first ? `${plural(first.first_feasible_eval_count, 'evaluation').replace(/^\S+ /, '')} used` : undefined} title={FIRST_FEASIBLE_TIP} />
        {/* Its reward, and the hard violation only while it misses (branch record SIF-76: a feasible one read "feasible hard
            violation 0", always 0, and no reward); three digits, as the facts below (SIF-42) */}
        <KeyTile label="Best design" value={!best ? 'none' : best.feasible ? 'feasible' : best.nominal_feasible ? 'nominal only' : 'infeasible'}
          after={best ? [best.reward != null && `reward ${few(best.reward)}`, !best.feasible && `hard violation ${few(best.violation)}`].filter(Boolean).join(' · ') || undefined : undefined} />
      </div>
    </div>}
    {/* What went wrong and what to do next, under the run at a glance (branch record SIF-89): a failure's reason was the last
        row of the facts below and Continue... came after all of them, out of sight in a panel that shows about four rows.
        The Error row stays in the table, beside the other facts. */}
    {status.error && <p className="error status-error">{status.error}</p>}
    <div className="row">
      <button ref={continueRef} className="continue-open" disabled={!!continueBlocked || asking} onClick={() => setAsking(true)}
        title={continueBlocked ? `Continue: ${continueBlocked}` : 'Continue: A paused, stopped or interrupted run - or a completed one, with a higher total - goes on in the '
          + 'same run folder, from its saved state, with its own saved configuration. The form asks for the total first.'}><Icon name="play" label="Continue..." /></button>
      {/* a failed or cancelled run says why too (branch record SIF-90): it is no state Continue goes on from, so the reason
          stood only in the tooltip of a greyed Continue... */}
      {(resting || (!status.worker_alive && ['failed', 'cancelled'].includes(status.state))) && continueBlocked && <span className="hint continue-why">{continueBlocked}</span>}
      {failed && <span className="hint failed-next">{where ? `${FAILED_WHERE[where]} ` : ''}Fix the cause, then {nextRun}</span>}
      {where && onShowCause && <button className="failed-show" onClick={() => onShowCause(where)}
        title={where === 'errors' ? 'Show errors: Logs opens on this run\'s errors log. Nothing else changes.'
          : 'Show evaluations: Data tables opens on this run\'s evaluations, newest first; their status and diagnostics say why each failed. Nothing else changes.'}>
        {where === 'errors' ? 'Show errors' : 'Show evaluations'}</button>}
      {resting && check?.alternative && <button className="continue-alternative" onClick={() => onFineTune(check.alternative)}
        title={`${check.alternative.label}: The next run on this page loads this run's save point ${check.alternative.checkpoint_id} in Mode Fine-tune, as one Undo step. Nothing starts until Start.`}>{check.alternative.label}</button>}
      <button onClick={() => saveJson(`${runName(status.run_dir)}__status.json`, { exported_utc: new Date().toISOString(), ...status })}
        title="Export status (JSON): Everything this tab shows, as it is right now, in one JSON file: state, budget, best design, connection, the run's manifest and summary."><Icon name="export" label="Export status (JSON)" /></button>
    </div>
    {asking && <ContinueForm used={check?.used ?? b?.charged ?? null} total={check?.total ?? b?.max_evaluations ?? null} blocked={continueBlocked}
      onContinue={total => { closeForm(); onContinue(total); }} onCancel={closeForm} />}
    {refusal && <LaunchRefusal refusal={refusal} onDismiss={onDismissRefusal} />}
    <table className="grid small"><tbody>
      <tr><td>State</td><td title={status.stop_reason ?? undefined}><b>{status.state}</b>{status.stop_reason ? ` (${stopWords(status.stop_reason)})` : ''}{status.worker_alive ? ' - worker alive' : ''}</td></tr>
      {/* The Mode as the RL model window names it (branch record SIF-14: it wrote the key, "scratch (no weights loaded)"). */}
      <tr><td>Mode / model</td><td>{modeWords}{status.manifest?.source_model?.run_id ? ` - from run ${status.manifest.source_model.run_id.slice(0, 12)}, save point ${status.manifest.source_model.checkpoint_id}`
        : ['Baseline', 'Calibration'].includes(modeWords) ? '' : ' - no weights loaded'}</td></tr>
      <tr><td>Budget</td><td>{b ? `${count(b.charged)} used / ${count(b.max_evaluations)}  (in flight ${count(b.in_flight)}, completed ${count(b.completed)}, failed ${count(b.failed)}, remaining ${count(b.remaining)})` : '-'}</td></tr>
      <tr><td>Spectre launches</td><td>{b ? `${count(b.launches)}${b.max_launches ? ' / ' + count(b.max_launches) : ''}  (retries ${count(b.retries)}, cache hits ${count(b.cache_hits)})` : '-'}</td></tr>
      {b && <tr><td>Launch accounting</td><td>{count(b.confirmed_launches ?? b.launches)} confirmed, {count(b.uncertain_launches ?? 0)} uncertain, {count(b.reserved_launches ?? 0)} reserved</td></tr>}
      {/* The setting by Run configuration's name (branch record SIF-54: "none (concurrency 4)", the configuration's key). */}
      <tr><td>Active workers</td><td>{(status.active_workers ?? []).map((w: Json) => `#${w.worker_id}: ${w.phase} attempt ${w.attempt}`).join('; ') || 'none'}{status.concurrency != null
        ? `; up to ${plural(status.concurrency, 'concurrent Spectre job')}` : ''}</td></tr>
      <tr><td>Learner updates</td><td>{status.learner_updates != null && count(status.learner_updates)}</td></tr>
      {/* Named, and its settings as the reward block names them (branch record SIF-54: it began with a bare "compressed"). */}
      {executedReward?.version === 'constraint_violation_v2' && <tr><td>Executed reward</td><td>{REWARD_NAME[executedReward.version]}; {REWARD_NAMES.violation_shape} {executedReward.settings.violation_shape};
        {' '}{REWARD_NAMES.worst_spec_share} {few(executedReward.settings.worst_spec_share)}; {REWARD_NAMES.objective_weight} {few(executedReward.settings.objective_weight)};
        {' '}{REWARD_NAMES.margin_weight} {few(executedReward.settings.margin_weight)}</td></tr>}
      <tr><td>{hasV2 ? 'First full-plan feasibility' : 'First feasibility (recorded)'}</td><td>{firstCost(first)}</td></tr>
      <tr><td>First nominal feasibility</td><td>{firstNominal ? firstCost(firstNominal) : hasV2 ? 'not observed' : 'unknown (historical run)'}</td></tr>
      <tr><td>Best design</td><td>{best ? `${best.feasible ? best.conditions_complete === true ? 'Full-plan feasible' : 'Feasible (coverage unknown)' : best.nominal_feasible ? 'Nominal feasible only' : 'Infeasible'}${best.reward != null ? `; reward ${few(best.reward)}` : ''}; hard violation ${few(best.violation)}` : 'none'}</td></tr>
      {best && <tr><td>Conditions</td><td>Nominal: {best.nominal_feasible == null ? 'unknown' : best.nominal_feasible ? 'pass' : 'fail'}; robust: {best.robust_feasible == null ? 'not evaluated' : best.robust_feasible ? 'pass' : 'fail'}; coverage: {best.conditions_complete == null ? 'unknown' : best.conditions_complete ? 'complete' : 'partial'}</td></tr>}
      {best && <tr><td>Conditions evaluated / planned</td><td>{best.conditions_evaluated ?? 'unknown'} / {best.conditions_planned ?? 'unknown'}</td></tr>}
      {best && <tr><td>{best.worst_metrics ? 'Worst applicable values' : 'Recorded values'}</td><td>{metricKeys.map(k => metric(k, (best.worst_metrics ?? best.metrics)[k])).join('; ')}</td></tr>}
      {best?.nominal_metrics && <tr><td>Nominal values</td><td>{nominalKeys.map(k => metric(k, best.nominal_metrics[k])).join('; ')}</td></tr>}
      {sizes && <tr><td>Best design variables</td><td className="copy-cell" title="Click to copy" onClick={() => void copying.copyText(sizes, sizesKey)}>
        {sizes}{copying.word(sizesKey)}</td></tr>}
      {/* Branch record SIF-54: "Tightest margin", as the Training tab's chart and the reward block's bonus name it (it read
          "Tightest clearance" here alone); the connection's state in the Connection window's words (it printed the key,
          "not_applicable", and an empty badge without one); what was saved, with the store's counters in the tooltip (it
          read "Persistence: commit 812, flushed 812, ...") and a failure first. */}
      {best && <tr><td>Tightest margin</td><td>{few(best.clearance_margin)}{best.tightest_clearance_spec ? `, on ${best.tightest_clearance_spec}` : ''}</td></tr>}
      <tr><td>Connection</td><td>{conn?.overall ? <><span className={`badge state-${conn.overall}`}>{CONNECTION_STATE[conn.overall] ?? String(conn.overall).replace(/_/g, ' ')}</span>
        {conn.age_seconds != null && ` ${durationWhole(conn.age_seconds)} old`}</> : 'not reported'}</td></tr>
      <tr><td>Saved to disk</td><td className={saved?.failed ? 'error' : ''}
        title={saved ? `${saved.last_successful_save ? `last save ${saved.last_successful_save} (UTC); ` : ''}commit ${saved.last_commit_seq}, flushed ${saved.flushed_seq}` : undefined}>
        {saved ? `${saved.failed ? `failed: ${saved.failed} · ` : ''}last save ${stamp(saved.last_successful_save) ?? saved.last_successful_save ?? '-'} · ${bytes(saved.bytes_written)} of table data` : '-'}</td></tr>
      {/* A "save point", as the Runs window's Details and the RL model window name one (branch record SIF-70: it read "Last
          checkpoint" here, "Last model save" there); a Save now by its evaluations, its id on hover (it said both) */}
      <tr><td>Last save point</td><td title={status.last_checkpoint_utc ? `${status.last_checkpoint_utc} (UTC)` : undefined}>{stamp(status.last_checkpoint_utc) ?? status.last_checkpoint_utc ?? '-'}
        {status.manual_save && <span className={status.manual_save.state === 'saved' ? 'ok' : 'warn'}
          title={status.manual_save.state === 'saved' ? `save point ${status.manual_save.checkpoint_id}` : undefined}> - Save now: {status.manual_save.state === 'saved'
          ? `saved at ${count(status.manual_save.evaluations)} evaluations`
          : 'requested, waiting for the simulation in flight to finish'}</span>}</td></tr>
      {/* named, and said when copied, as the Runs window's Details do (branch record SIF-54) */}
      <tr><td>Run folder</td><td className="path" title="Click to copy" onClick={() => void copying.copyText(status.run_dir)}>
        {status.run_dir}{copying.word(status.run_dir)}</td></tr>
      {status.error && <tr><td>Error</td><td className="error">{status.error}</td></tr>}
    </tbody></table>
  </div>);
}

/** A tab that reads the shown run's files follows the run (branch record SIF-99): it reads again when `mark` - what the run
 *  has written so far - moves on, or when its worker ends. Data tables and Output files were read once, when they opened,
 *  and went stale unsaid while Logs and Training followed the run. Not on a timer: a run at rest is still read once, and a
 *  live one only when there is something new to read. `mark` and `alive` are null while the run's status is not read; that
 *  is no change. */
function useFollow(runDir: string | null, mark: string | number | null, alive: boolean | null, refresh: () => void) {
  const known = useRef({ runDir, mark, alive });
  useEffect(() => {
    const was = known.current, same = was.runDir === runDir;
    known.current = { runDir, mark: mark ?? (same ? was.mark : null), alive: alive ?? (same ? was.alive : null) };
    if (same && ((mark != null && was.mark != null && mark !== was.mark) || (alive === false && was.alive === true))) refresh();
  }, [runDir, mark, alive]);
}
/** This computer's time of day when the tab's answer came (branch record SIF-99): said on its count line, so a read - pressed
 *  or made by the run's progress - shows, and an answer that did not change says how old it is. */
function useReadAt(value: unknown) {
  const [at, setAt] = useState<string | null>(null);
  useEffect(() => { if (value) setAt(clock()); }, [value]);
  return at;
}

/** The table as read, memoised apart from the tool line above it (record 7.379): a status update still redraws the steering
 *  line and the tool line, but not the table's rows (up to 500 since branch record SIF-99). The rows change with a read's
 *  answer - Refresh, another table, row count or order, or the run's new rows (branch record SIF-99) - and with the order;
 *  `onNote` is the tab's note setter, the same at every draw. */
const DataSnapshot = memo(function DataSnapshot({ data, newest, onNote }: { data: Json; newest: boolean; onNote: (note: string) => void }) {
  // A column of numbers only (no id) is right-aligned in figures of one width (branch record SIF-32), as a spreadsheet's.
  const numeric = new Set<string>(data.columns.filter((c: string) => !/_id$/.test(c) && (data.rows as Json[]).some(r => r[c] != null)
    && (data.rows as Json[]).every(r => r[c] == null || typeof r[c] === 'number')));
  return (<div className="scroll"><table className="grid small data-table"><thead><tr>{data.columns.map((c: string) => <th key={c} className={numeric.has(c) ? 'num-cell' : undefined}>{c}</th>)}</tr></thead>
    <tbody>{(newest ? [...data.rows].reverse() : data.rows as Json[]).map((r: Json, i: number) => <tr key={i}>{data.columns.map((c: string) => {
      // One line per row (record 7.158): an id ends in "..." - the whole value on hover, a click copies it - a time keeps
      // its full width, and no word is cut in two; a long hash used to wrap into a column of letters as tall as a paragraph.
      // A time in this computer's time, as Logs and Output files write it, its UTC value on hover (branch record SIF-76: it
      // read "2026-10-16T17:17:20.704501+", cut at the panel's edge and an hour off the same moment in Logs).
      const time = /_(at|utc)$/.test(c), local = time && typeof r[c] === 'string' ? stamp(r[c]) : null;
      const object = typeof r[c] === 'object' && r[c] !== null, text = object ? JSON.stringify(r[c]) : local ?? num(r[c]);
      const id = /_id$/.test(c) && text !== '';
      // A JSON value keeps to one line too (branch record SIF-4): it wrapped into a block 200 px tall. A click's copy is said
      // on the tool line, or that the browser refused it (branch record SIF-94: it copied unsaid either way).
      return <td key={c} className={id ? 'id-cell' : time ? 'time-cell' : object ? 'json-cell' : numeric.has(c) ? 'num-cell' : undefined}
        title={id || object ? `${text}\nClick to copy` : local ? `${r[c]} (UTC)` : undefined}
        onClick={id || object ? () => copy(text).then(() => onNote(`Copied ${c}.`),
          () => onNote(`Could not copy ${c}: the browser refused the clipboard; select the cell's text instead.`)) : undefined}>{text}</td>; })}</tr>)}</tbody></table></div>);
});

/** What Data tables shows: the table, how many rows and from which end (branch record SIF-99: always the newest 25, so an
 *  earlier evaluation of a run needed the whole table exported and opened elsewhere; the route reads up to 500, from either
 *  end). Held by the bottom panel since branch record SIF-105: the tab is drawn only while chosen, and a look at another
 *  tab put it back to the newest 25 evaluations. */
export type DataChoice = { table: string; limit: number; newest: boolean };
export const DATA_CHOICE: DataChoice = { table: 'evaluations', limit: 25, newest: true };

/** `status`: the shown run's status as the page already polls it (App.tsx) - for the steering line, and since branch record
 *  SIF-99 for when to read the table again. This tab used to poll the same file again every 2 s, finished runs too.
 *  `choice`: what it shows, kept by the bottom panel (branch record SIF-105). */
export function DataTab({ runDir, status, choice, setChoice }: { runDir: string | null; status: Json; choice: DataChoice;
  setChoice: (change: (choice: DataChoice) => DataChoice) => void }) {
  const { table, limit, newest } = choice;
  const choose = (change: Partial<DataChoice>) => setChoice(now => ({ ...now, ...change }));
  const { value: data, error, refresh, loading } = useRequest<Json>(signal => api.table(runDir!, table, limit, signal, newest), [runDir, table, limit, newest], { enabled: !!runDir });
  // Read again when the run has published more rows: its tables reach the disk at flushes (record 7.280, every 64
  // evaluations), so the store's flushed sequence moving on is the moment there is something new (0: none flushed yet).
  const shown = status?.run_dir === runDir ? status : null;
  useFollow(runDir, shown ? shown.persistence?.flushed_seq ?? 0 : null, shown ? !!shown.worker_alive : null, refresh);
  const readAt = useReadAt(data);
  const end = newest ? 'newest' : 'oldest';
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
    <SteeringCheck status={status} />
    <div className="row"><select className="tab-choice" value={table} onChange={e => choose({ table: e.target.value })}>{TABLES.map(t => <option key={t}>{t}</option>)}</select>
      <select className="table-limit" aria-label="Rows shown" value={limit} onChange={e => choose({ limit: Number(e.target.value) })}
        title="Rows shown: How many of the table's rows are read and listed here. Export detailed CSV saves every row.">{[25, 100, 500].map(n => <option key={n} value={n}>{n} rows</option>)}</select>
      <select className="table-order" aria-label="Order" value={end} onChange={e => choose({ newest: e.target.value === 'newest' })}
        title="Order: Newest first - the table's newest rows, the newest on top. Oldest first - its first rows, in the order they were written (an early evaluation of the run).">
        <option value="newest">newest first</option><option value="oldest">oldest first</option></select>
      {/* the hourglass while a read is on its way (branch record SIF-99: a press that found nothing new looked like one that did nothing) */}
      <button onClick={refresh} title="Refresh: Read this table again. While the run works it is read again by itself each time the run writes its rows to disk.">
        <Icon name={loading ? 'wait' : 'refresh'} label={loading ? 'Reading...' : 'Refresh'} /></button>
      <button disabled={!!busy} onClick={exportCsv} title="Export detailed CSV: The whole table, every row and not only the ones shown here. Written to the run folder (exports/) and downloaded."><Icon name={busy === 'csv' ? 'wait' : 'csv'} label={busy === 'csv' ? 'Exporting...' : 'Export detailed CSV'} /></button>
      <button disabled={!!busy} onClick={exportResearch} title="Export research CSVs: The summary tables over every run of this experiment: run summary, success per budget, paired runs, transfer summary, cumulative cost. Written to the experiment's aggregates folder and downloaded as one zip."><Icon name={busy === 'research' ? 'wait' : 'zip'} label={busy === 'research' ? 'Exporting...' : 'Export research CSVs'} /></button>
      {/* the store's commit in the tooltip, a row as one (branch record SIF-54: "1 rows (snapshot at commit 3)"); the newest
          row on top, as Logs lists its lines (branch record SIF-76: the backend sends the tail oldest first, and during a run
          each new row landed below the fold of a panel six rows tall) - or the first rows in their order; then when it was
          read (branch record SIF-99) */}
      <span className="hint" title={data ? `Snapshot at commit ${data.cutoff_commit_seq}` : undefined}>{data ? `${plural(data.total_rows, 'row')}${data.rows.length < data.total_rows
        ? `; the ${end} ${data.rows.length} shown` : ''}${data.rows.length > 1 ? `, ${end} first` : ''}.${readAt ? ` Read at ${readAt}.` : ''}` : ''} {error ?? note}</span></div>
    {data && <DataSnapshot data={data} newest={newest} onNote={setNote} />}
  </div>);
}

/** Output files' columns, each sorted by a press on its title as the Runs window's are (branch record SIF-99: a run's ~500
 *  files stood in folder order only, in a panel six rows tall). */
const FILE_COLUMNS: { key: string; title: string; help: string; numeric?: boolean; value: (f: Json) => string | number | null }[] = [
  { key: 'path', title: 'File', help: 'File: its path in the run folder.', value: f => f.path },
  { key: 'bytes', title: 'Size', help: 'Size: what the file holds now.', numeric: true, value: f => f.bytes },
  { key: 'modified', title: 'Modified', help: "Modified: when the file was last written, in this computer's time.", value: f => { const t = Date.parse(f.modified_utc); return Number.isNaN(t) ? null : t; } }];

/** `alive` and `savePoint`: whether the run's worker lives and its last save point ('' for none yet), null while its status
 *  is not read. */
function FilesTabBody({ runDir, alive = null, savePoint = null }: { runDir: string | null; alive?: boolean | null; savePoint?: string | null }) {
  const { value: files, error, refresh, loading } = useRequest<Json>(signal => api.files(runDir!, signal), [runDir], { enabled: !!runDir });
  // A live run's folder is read again at each new save point, and once more when its worker ends (branch record SIF-99);
  // a run at rest is read once, as before: each read walks its ~500 files on the 9p-mounted D: drive.
  useFollow(runDir, savePoint, alive, refresh);
  const readAt = useReadAt(files);
  const view = useTableView('path', false);                         // the backend lists them by path
  const [note, setNote] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);          // the file whose download is on its way
  useEffect(() => { setNote(null); view.setFilter(''); }, [runDir]);
  if (!runDir) return <p className="hint">No run selected.</p>;
  const column = FILE_COLUMNS.find(c => c.key === view.sort.key) ?? FILE_COLUMNS[0];
  const shown: Json[] = files ? view.arrange(files.files as Json[], () => true, f => f.path.toLowerCase(), column.value) : [];
  // The count says how many the filter leaves (branch record SIF-99), then when the folder was read.
  const count = !files ? '' : `${view.filter.trim() ? `${shown.length} of ${plural(files.files.length, 'file')} shown, ${bytes(files.total_bytes)} in all`
    : `${plural(files.files.length, 'file')}, ${bytes(files.total_bytes)}`}.${readAt ? ` Read at ${readAt}.` : ''}`;
  const pack = () => { setNote('Packing...'); downloadPackage(runDir).then(name => setNote(`Downloaded ${name}.`), e => setNote(e.message)); };
  // A copy's word leaves "Packing..." standing (branch record SIF-94 review): that note is the package button's busy state,
  // and a copy said over it took the hourglass away and let a second pack start while the first was still zipping.
  const copied = (text: string) => setNote(n => n === 'Packing...' ? n : text);
  // One file (user request 2026-09-26: a button with the download icon in each row, not a "download" text link), saved
  // like the package and the logs: the browser's own download, named by the backend, and said in the hint.
  const save = (file: string) => { setSaving(file); download(api.downloadUrl(runDir, file), file.split('/').pop() ?? file)
    .then(name => setNote(`Downloaded ${name}.`), e => setNote(e.message)).finally(() => setSaving(null)); };
  return (<div><div className="row"><button onClick={refresh} title="Refresh: Read the run folder again. While the run works it is read again by itself at each new save point.">
    <Icon name={loading ? 'wait' : 'refresh'} label={loading ? 'Reading...' : 'Refresh'} /></button>
    <button disabled={note === 'Packing...'} onClick={pack} title="Download data-only package (.zip): Every data file of this run in one zip, named after the run; no plots, nothing drawn."><Icon name={note === 'Packing...' ? 'wait' : 'download'} label="Download data-only package (.zip)" /></button>
    {/* The count and the notes alone on the tool line (branch record SIF-48): it ended, on every visit, with a sentence about an
        "Open local folder" button that does not exist; why there is none now sits in Copy run path's tooltip. Copy run path says
        on it how it went, the path itself when the browser refused the clipboard (branch record SIF-94: it copied unsaid). */}
    <button onClick={() => copy(runDir).then(() => copied('Copied the run path.'), () => copied(`Could not copy: the browser refused the clipboard. The run path: ${runDir}`))} title="Copy run path: The run folder's path, as text, to the clipboard. A browser cannot open a folder itself."><Icon name="copy" label="Copy run path" /></button>
    <input className="files-filter" aria-label="Filter files" placeholder="Filter: a file or folder name ..." value={view.filter} onChange={e => view.setFilter(e.target.value)}
      title="Filter files: Only the files whose path holds every word typed here." />
    <span className="hint">{count} {error ?? note}</span></div>
    {/* The column titles take Tab, Enter and Space, as the Tasks, Runs and saved models tables' do (branch record SIF-109). */}
    <div className="scroll"><table className="grid small files-table"><thead><tr>{FILE_COLUMNS.map(c => <th key={c.key} className={c.numeric ? 'sortable num-cell' : 'sortable'}
      title={`${c.help} Press to sort.`} aria-sort={view.sort.key === c.key ? (view.sort.down ? 'descending' : 'ascending') : undefined} onClick={() => view.sortBy(c.key)}
      {...sortKeys(view, c.key)}>
      {c.title}{view.sort.key === c.key && <span className="sort-mark">{view.sort.down ? ' ▼' : ' ▲'}</span>}</th>)}<th></th></tr></thead>
      <tbody>{shown.map((f: Json) => <tr key={f.path}><td>{f.path}</td><td className="num-cell">{bytes(f.bytes)}</td><td title={`${f.modified_utc} (UTC)`}>{stamp(f.modified_utc) ?? f.modified_utc.slice(0, 19)}</td><td><button disabled={saving === f.path} onClick={() => save(f.path)}
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

/** `kind`: the log shown, events or errors, kept by the bottom panel (branch record SIF-105: the tab is drawn only while
 *  chosen, and the errors log went back to events at every return). `hidden`: the panel is folded to its tab line, the tab
 *  out of sight (branch record SIF-127). */
function LogsTabBody({ runDir, alive, kind, setKind, hidden }: { runDir: string | null; alive: boolean; kind: string; setKind: (kind: string) => void;
  hidden: boolean }) {
  const [note, setNote] = useState<string | null>(null);
  // Read every 2 s while the worker lives; a run at rest is read once (when the tab opens, and once more when its worker
  // ends) - it used to be re-read every minute for as long as the tab stayed open. Not on the timer while the panel is
  // folded, as the Training tab (branch record SIF-127): a live run's newest 200 entries were read every 2 s for nobody to
  // see, and the panel folds by itself when a cell is entered with little room. The fold changes the interval, so one more
  // read comes in (the one on its way, or one at once), then none; opened again, it reads at once, then every 2 s. The read
  // when the worker ends stays.
  const { value, error, refresh } = usePolling(signal => api.logs(runDir!, kind, signal), alive && !hidden ? 2000 : 0, !!runDir, [runDir, kind]);
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
  return (<div><div className="row"><select className="tab-choice" value={kind} onChange={e => setKind(e.target.value)}><option>events</option><option>errors</option></select>
    <button onClick={save} title={`Download full log (${kind}.jsonl): The whole log file of this run, not only the newest 200 entries listed here. One JSON record per line.`}><Icon name="download" label={`Download full log (${kind}.jsonl)`} /></button>
    <span className="hint">{note ?? 'Newest first, the newest 200 entries at most.'}</span></div>
    {error && <p className="error">{error} <button onClick={refresh}>Retry read</button></p>}
    <div className="scroll log">{logLines(value?.entries ?? []).map(line =>
      <LogLine key={line.key} time={line.time} name={line.name} text={line.text} error={kind === 'errors'} />)}</div></div>);
}

/** Memoised (record 7.279): their props are the run and whether its worker lives - and Output files' last save point, which
 *  changes as rarely (branch record SIF-99), the log chosen, whose setter stays the same (SIF-105), and whether the panel is
 *  folded (SIF-127) - so a status update - every 1.5 s while a run works - no longer draws the 200 log lines or the run's
 *  ~450 files again; their own reads still do. */
export const LogsTab = memo(LogsTabBody);
export const FilesTab = memo(FilesTabBody);
