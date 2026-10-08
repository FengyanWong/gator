import { CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from 'react';
import { api, ApiError, Json, NO_ANSWER, plainError, saveJson, tasksShared } from './api';
import { Look, LOOK_NAMES, setLook, useLook } from './theme';
import { Icon } from './panels/Icons';
import { setUnitForms } from './units';
import { migrateConfig, rowsFrom, useConfig, usePolling, useRequest, useTaskSaves } from './store';
import { CircuitPanel, TaskLoad, TaskLoaded } from './panels/Left';
import { ConnectionButton } from './panels/Connection';
import { CheckSteps } from './panels/Consistency';
import { Editors } from './panels/Editors';
import { ValidationStatus } from './panels/Issues';
import { isLive, LIVE_STATES, RESUMABLE, RunButtons, useRunControl } from './panels/RunControl';
import { continueConsent, continueReadiness, featuresOf, launchKept, startReadiness, useContinuation, useLauncher } from './launch';
import { LaunchRefusal } from './panels/LaunchRefusal';
import { useRunBrief } from './panels/RunBrief';
import { RunListButton } from './panels/RunList';
import { MODE_NAME, NextModel, OutputPanel, ResearchPanel, RunPanel } from './panels/Right';
import { modelNameAt } from './panels/ModelChooser';
import { LOADS, readSavePoint, SavePoint, withSavePoint } from './savePoint';
import { folderName, two } from './format';
import { AgentWindowTab } from './panels/Agent';
import { DataTab, FilesTab, LogsTab, StatusTab } from './panels/RunTabs';
import { APPLY_AND_SAVE, calibrationPlan, savingText } from './panels/calibrationPlan';
import { requestTaskSave, TASK_BASELINE_STARTED } from './panels/TaskSave';
import { CornerCheckTab } from './panels/CornerCheck';
import { TrainingTab } from './panels/TrainingTab';
import { CrashPanel } from './panels/CrashPanel';

type BottomTab = 'status' | 'logs' | 'data' | 'files' | 'training' | 'corners';

/** A configuration the backend cannot even read (HTTP 422): one blocking issue per field it names, in its plain words
 *  (schema.describe_errors), at the place the validation report uses (parameters[1].variable_id), so the list names the
 *  row and the editor marks it. Before, all of them were one issue with pydantic's list as JSON (user report 2026-09-21).
 *  An older backend sends parameters.1.variable_id and pydantic's text: the path is rewritten the same way. Anything
 *  else (the backend unreachable...) stays one issue. */
function rejected(e: any): Json {
  const errors: Json[] = Array.isArray(e.detail?.errors) ? e.detail.errors : [];
  const issues = errors.length ? errors.map((x: Json) => ({ level: 'error', code: x.code ?? 'schema', message: x.message, technical: x.technical,
    path: String(x.path ?? '').replace(/\.(\d+)(?=\.|$)/g, '[$1]') }))
    : [e instanceof ApiError ? { level: 'error', code: 'schema', path: '', message: e.message } : { level: 'error', code: 'no_answer', path: '', message: NO_ANSWER }];
  return { blocks_run: true, issues, facts: {} };
}
const NO_RUNS: Json[] = [];                          // one empty list: a failed read does not make the model list read again
/** A run as a message names it: its task and when it was created, "ota7t 10-06 14:02" (the folder's name without a date). */
const runTitle = (row: Json) => { const d = row.created_utc ? new Date(row.created_utc) : null;
  return d && !Number.isNaN(d.getTime()) ? `${row.task_name ?? folderName(row.run_dir)} ${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}` : folderName(row.run_dir); };
/** The run settings New run like this copies (record 7.267; plan "Existing runs: continued in place"): the Mode, the name of the
 *  model it saves, the budget and limits, the seed, the network, the training values, reward and conditions. Not the
 *  connection, the concurrency or the source (that is the save point the run loaded, read from its lineage). */
const RUN_SETTINGS = ['model_label', 'max_evaluations', 'max_spectre_launches', 'max_wall_seconds', 'max_retries', 'max_consecutive_failures',
  'max_consecutive_infrastructure_failures', 'stop_at_first_feasible', 'seed', 'frozen_action', 'network', 'reward', 'conditions', 'advanced', 'rehearsal', 'continual_learning'];
/** A draft whose Mode is still `resume` (record 7.267; plan "The draft": "An old saved draft with mode: resume"): no Mode is
 *  chosen, and nothing starts until one is. The value stays `resume` in the configuration, which every backend route still
 *  reads (the command line still starts one); the page shows it as no Mode chosen. */
const NO_MODE = 'Choose a Mode in the RL model window first: this configuration still says resume, which is no longer a choice (Continue... in the Runs window continues a run).';

/** The header's look switch (record 7.158): Whiteprint by day, Silicon Night by night. An icon, like the run buttons. */
function LookSwitch() {
  const look = useLook();
  const other: Look = look === 'silicon' ? 'whiteprint' : 'silicon';
  return <button className="look-switch" aria-pressed={look === 'silicon'} onClick={() => setLook(other)}
    title={`Switch look: now ${LOOK_NAMES[look]}; press for ${LOOK_NAMES[other]}. Kept in this browser; the pop-up windows follow.`}>
    <Icon name={look === 'silicon' ? 'sun' : 'moon'} label="Switch look" /></button>;
}

/** The bottom panel's height (record 7.158): dragged at its top edge, folded to its tab line with a double click there.
 *  Kept in this browser, like the folded modules; null = the default third of the window. */
type Bottom = { height: number | null; folded: boolean };
const BOTTOM_KEY = 'gator-workbench-bottom-v1';
const storedBottom = (): Bottom => {
  try { const b = JSON.parse(localStorage.getItem(BOTTOM_KEY) ?? 'null'); return { height: typeof b?.height === 'number' && b.height > 0 ? b.height : null, folded: b?.folded === true }; }
  catch { return { height: null, folded: false }; }
};

/** Calibration evaluates only random designs. Task creation owns the fixed starting-design baseline. */
const CALIBRATION_DESIGNS = 64;
/** "Calibration ready" (record 7.204, user: "build the prompt when the run finishes"): when the header's Calibration run that has ended with proposals the page does not hold yet, a line under the header says so, with Apply
 *  calibration and Not now - so the proposals cannot be missed in Run status. Still the user's press: nothing is applied by
 *  itself. The run whose line was answered is kept in this browser, so a reload does not ask again. */
const CALIBRATION_ANSWERED_KEY = 'gator-workbench-calibration-answered-v1';
/** The run the bottom tabs show, kept in this browser with the header's run of that moment (record 7.212): a page loaded
 *  again shows the run it showed - or none, after a task without runs was chosen. Unless the header holds another run by
 *  then (started in another tab of the page, say): the page opens on the header's run then, as it always did, and so does a
 *  browser that never kept one. */
const SHOWN_RUN_KEY = 'gator-workbench-shown-run-v1';
const HEADER_RUN_KEY = 'gator-workbench-current-run-v1';      // RunControl.tsx: the run the header's buttons act on
const shownRun = (): string | null => {
  try {
    const header = localStorage.getItem(HEADER_RUN_KEY) || null, kept = JSON.parse(localStorage.getItem(SHOWN_RUN_KEY) ?? 'null');
    return kept && typeof kept === 'object' && (kept.header ?? null) === header ? kept.run ?? null : header;
  } catch { return null; }
};

/** Layout (specification section 2): left = project, connection, circuit; center = three editors;
 *  right = run configuration + output settings (always visible); bottom = status, logs, data, files, training, corner check,
 *  with the Agent window and the run window opened from its tab line (record 7.253: the Agent tab became "Agent...", drawn
 *  as a tab but opening a window - no tab view).
 *  Tables, numbers, status and file lists. On screen only, by user decision: two pictures of the circuit - the graph view
 *  (2026-09-21) and the circuit picture in the left column (2026-10-03) - and the Training tab's charts of a run's
 *  recorded numbers (2026-10-05, record 7.193); nothing drawn is written. */
/** The page under its crash panel (record 7.188, design advice): the configuration and its Undo history live above the panel,
 *  so a failure to draw any part of the page - this function's own work included - is shown with Undo, Export JSON and Reload
 *  instead of a blank page, and Undo draws the page again from the configuration before the last change. */
export function App() {
  const store = useConfig();
  return <CrashPanel undo={store.undo} canUndo={store.canUndo} config={store.config}><Page store={store} /></CrashPanel>;
}

function Page({ store }: { store: ReturnType<typeof useConfig> }) {
  const { config, setConfig } = store;
  const [schema, setSchema] = useState<Json>(null);
  const [meta, setMeta] = useState<Json>(null);
  const [circuit, setCircuit] = useState<Json>(null);
  const [runs, setRuns] = useState<Json[]>(NO_RUNS);
  const [runsError, setRunsError] = useState<string | null>(null);   // the run list could not be read: said, not shown as "no run yet"
  const [runDir, setRunDir] = useState<string | null>(shownRun);
  const [tab, setTab] = useState<BottomTab>('status');
  const [bottom, setBottom] = useState<Bottom>(storedBottom);
  // Folded while no run is shown (record 7.179, design advice 1): its tabs show a run, and with none it was a third of the page
  // saying "No run selected". A tab, the splitter, a started or a chosen run opens it; the kept height and fold stay.
  const [opened, setOpened] = useState(false);
  const folded = bottom.folded || (!runDir && !opened);
  const changeBottom = useCallback((change: (b: Bottom) => Bottom) => setBottom(b => {
    const next = change(b);
    if (next !== b) try { localStorage.setItem(BOTTOM_KEY, JSON.stringify(next)); } catch { /* a private window: not remembered */ }
    return next;
  }), []);
  // A press that asks to see something in the bottom panel (one of its tabs, the header's run) opens it.
  const unfold = useCallback(() => { setOpened(true); changeBottom(b => (b.folded ? { ...b, folded: false } : b)); }, [changeBottom]);
  const toggleBottom = () => (folded ? unfold() : changeBottom(b => ({ ...b, folded: true })));
  const [titleSlot, setTitleSlot] = useState<HTMLElement | null>(null);            // the header's title block: the circuit panel puts the task's facts there
  const [taskSlot, setTaskSlot] = useState<HTMLElement | null>(null);              // editors' tab line: where the circuit panel puts "Save task"
  const [taskNotes, setTaskNotes] = useState<HTMLElement | null>(null);            // under the editors' toolbar: its messages and questions
  const [message, setMessage] = useState<Json>(null);
  const [fatal, setFatal] = useState<string | null>(null);
  const profileId: string | null = config.run.connection_profile_id ?? null;

  useEffect(() => {
    Promise.all([api.schema(), api.meta()]).then(([s, m]) => {
      setUnitForms(s.unit_forms);                    // how quantities are written and read (record 7.208)
      setSchema(s); setMeta(m);
      // Restore the previous concurrency on a fresh browser (default 1 when none was ever used). Blocked site storage
      // counts as a fresh browser: the page then starts from the default configuration too (useConfig).
      // "Fresh" is decided when the page opens (the 0.8 s autosave may have written the default configuration by now).
      const remembered = m.remembered?.concurrency;
      if (remembered && store.fresh) setConfig((c: Json) => ({ ...c, run: { ...c.run, concurrency: remembered } }), false);
    }).catch(e => setFatal(e.message));
  }, []);
  // Only the newest read of the run list may answer: while the output root is typed, a half-typed path outside the roots
  // (403) used to empty the list when its answer came last.
  const listing = useRef(0);
  // One function for the whole page (useCallback; the output root through a ref), so the panels that take it are not drawn
  // again at every status update (record 7.275). A list that is the same as the one held keeps that array: what depends
  // on the runs (the saved models, the Training tab) is not asked again for nothing. `fresh`: the backend reads every
  // run folder anew (Refresh list; record 7.274).
  const outputRoot = useRef(config.output.output_root);
  outputRoot.current = config.output.output_root;
  const readRuns = useCallback((fresh = false): Promise<{ list: Json[]; error: string | null }> => {
    const mine = ++listing.current;
    return api.runs(outputRoot.current ?? undefined, fresh).then(r => ({ list: r.runs as Json[], error: null }), e => ({ list: NO_RUNS, error: plainError(e) }))
      .then(read => {
        if (mine === listing.current) { setRuns(held => (JSON.stringify(held) === JSON.stringify(read.list) ? held : read.list)); setRunsError(read.error); }
        return read;
      });
  }, []);
  const refreshRuns = useCallback((fresh = false): Promise<Json[]> => readRuns(fresh).then(read => read.list), [readRuns]);

  // Debounce validation and ignore replies for a configuration that has since changed. `sent`: the configuration the
  // report is about - its row paths (targets[3]) name rows of THAT configuration, which Delete, Undo or Import may have
  // moved by the time it is drawn (the editors check the row before they mark it). Asked again after a save of the task too
  // (record 7.222): the rows may not change, but what they are compared with did.
  const configKey = useMemo(() => JSON.stringify(config), [config]);
  const taskSaves = useTaskSaves();
  const validationRead = useRequest<Json>(signal => api.validate(config, signal, rowsFrom(config.circuit?.task_id)).catch(rejected).then(v => ({ ...v, sent: config })), [configKey, taskSaves],
    { delay: 500, keepPrevious: true });
  const validation = useMemo(() => validationRead.error ? { blocks_run: true, issues: [{ level: 'error', code: 'no_answer', path: '', message: validationRead.error }], facts: {} }
    : validationRead.value, [validationRead.value, validationRead.error]);

  // How often the run shown is read: see the effect after useRunControl below.
  const [statusEvery, setStatusEvery] = useState(1500);
  // The run shown is gone (deleted, or outside the allowed roots by now - it may be the remembered one the page opened
  // with): it is let go, as the header lets go of its own, instead of being asked for every 1.5 s for ever while the strip
  // still names its folder. Two answers in a row: on the 9p-mounted D: drive a stat right after a rename can fail once,
  // and one 404 of a run that is there must not take it off the page.
  const gone = useRef(0);
  useEffect(() => { gone.current = 0; }, [runDir]);
  const readStatus = (dir: string, signal: AbortSignal) => api.status(dir, signal).then(value => { gone.current = 0; return value; }, e => {
    if (e instanceof ApiError && (e.status === 403 || e.status === 404) && ++gone.current >= 2) setRunDir(shown => (shown === dir ? null : shown));
    throw e;
  });
  const { value: polledStatus, error: statusError } = usePolling(signal => readStatus(runDir!, signal), statusEvery, !!runDir, [runDir]);
  const status = polledStatus?.run_dir === runDir ? polledStatus : null;
  // Corner check only where corners can be used (record 7.182, design advice): the loaded circuit simulates at corners, or the run
  // shown is MOCK (its corners are analytic). No registered circuit does since 2026-09-30 (record 7.128); the tab comes back by
  // itself with one that does.
  const cornersUsable = circuit?.training_capabilities?.corners === true || !!status?.manifest?.mock;
  useEffect(() => { if (tab === 'corners' && !cornersUsable) setTab('status'); }, [tab, cornersUsable]);
  const isReal = circuit?.loaded && circuit.mock === false;
  // The run the header buttons act on (Start -> Pause -> Resume, Abort). It is not the run the bottom tabs show.
  const [looked, setLooked] = useState(false);
  const control = useRunControl(status, looked);
  // The run shown, kept with the header's run (shownRun above); again when the header takes or lets go of one.
  useEffect(() => {
    try { localStorage.setItem(SHOWN_RUN_KEY, JSON.stringify({ run: runDir, header: control.dir })); } catch { /* a private window: not kept */ }
  }, [runDir, control.dir]);
  // The header's run at rest, its calibration result, and what Apply would do with the rows the page holds now.
  const [calibrationAnswered, setCalibrationAnswered] = useState<string | null>(() => { try { return localStorage.getItem(CALIBRATION_ANSWERED_KEY); } catch { return null; } });
  const calibrated: Json = control.phase === 'idle' && control.dir && control.dir !== calibrationAnswered ? control.status?.calibration?.result ?? null : null;
  const calibrationOffer = calibrated ? calibrationPlan(calibrated, config) : null;
  const calibrationReady = !!calibrationOffer && !calibrationOffer.otherTask && (calibrated.status !== 'calibrated' || calibrationOffer.pending > 0);
  // 'save' (record 7.217, a task saved from a Virtuoso cell): Apply, then Save task as a press on it - asked in the same
  // click, sent with the rows of the next render (TaskSave.tsx), so the page is not left differing from its saved task.
  const answerCalibration = (how: 'save' | 'apply' | 'no') => {
    const dir = control.dir;
    if (!dir || !calibrationOffer) return;
    if (how !== 'no') setConfig(calibrationOffer.apply);
    const after = how === 'save' ? savingText(requestTaskSave(config.circuit.task_id)) : calibrationOffer.afterwards;
    setCalibrationAnswered(dir);
    try { localStorage.setItem(CALIBRATION_ANSWERED_KEY, dir); } catch { /* a private window: asked again after a reload */ }
    if (calibrated.status === 'calibrated') setMessage({ level: 'info', text: how !== 'no' ? `Calibration applied: ${calibrationOffer.what}, as one Undo step.${after}`
      : 'Nothing was changed. The proposals stay under Run status of that run, with Apply calibration.' });
  };
  // The run shown is read every 1.5 s while it can change by itself: a worker is alive, its state is a live one, or the
  // header is starting, resuming, pausing or ending a run. Otherwise it waits for a press on this page: every 15 s while
  // it could still be continued (paused, stopped, interrupted - another browser may continue it), once a minute once it
  // has ended for good (completed, failed, cancelled). Until 2026-09-30 a paused or stopped run was read every 1.5 s, and
  // each read re-reads its tables. The header's phase counts only when the header's run IS the run shown (record 7.125:
  // a finished run in the tabs was read every 1.5 s while the header paused or aborted another one).
  const transitional = control.dir === runDir && ['starting', 'resuming', 'pausing', 'aborting', 'finishing'].includes(control.phase);
  useEffect(() => setStatusEvery(!status || status.worker_alive || LIVE_STATES.includes(status.state) || transitional ? 1500
    : ['completed', 'failed', 'cancelled'].includes(status.state) ? 60000 : 15000), [status?.worker_alive, status?.state, transitional]);
  // When the header's run comes to rest, the Project column reads its task again (a finished Baseline simulation
  // records the task's reference by itself, status record 7.78): a counter the column follows. Not on the page's first look,
  // and not after a start that never ran (refused or declined) or a paused run let go: nothing about the task changed.
  const [taskEpoch, setTaskEpoch] = useState(0);
  const lastPhase = useRef(control.phase);
  useEffect(() => {
    if (control.phase === 'idle' && ['starting', 'resuming', 'running', 'pausing', 'aborting', 'finishing'].includes(lastPhase.current)) setTaskEpoch(n => n + 1);
    lastPhase.current = control.phase;
  }, [control.phase]);
  const adopted = useRef(false);
  const controlNow = useRef(control);              // the header as it is when the list arrives (a launch recovered after a reload may hold one by then)
  controlNow.current = control;
  useEffect(() => {
    // The list follows the output root while it is typed: read 1 s after the last keystroke, not once per key (each read
    // looks at every run under the root; record 7.275). The first read, when the page opens, goes at once.
    const timer = setTimeout(() => refreshRuns().then(list => {
      // Once, when the page opens: a run that is live although this page does not hold it (started from another browser or
      // the CLI, or the browser's memory was cleared) is taken over, so the header offers Pause and Abort, not a second Start.
      if (adopted.current) return;
      adopted.current = true;
      const header = controlNow.current;
      const running = list.some(r => r.run_dir === header.dir && isLive(r)) ? null : list.find(isLive);
      if (running) {
        // Said (record 7.261), with the paused run the header held: it stays paused, and Runs continues it.
        const resting = list.find(r => r.run_dir === header.dir && RESUMABLE.includes(r.state));
        header.take(running.run_dir); setRunDir(running.run_dir);
        // A launch of this tab sent before a reload may have made it: the launcher says so once it has asked.
        const where = launchKept() ? 'a live run' : 'a live run started elsewhere (another browser tab, the command line or a task\'s baseline)';
        setMessage({ level: 'info', text: `The header took over ${folderName(running.run_dir)}, ${where}: its Pause and Abort act on it.`
          + (resting ? ` ${folderName(resting.run_dir)} stays paused; continue it from Runs.` : '') });
      }
      setLooked(true);
    }), adopted.current ? 1000 : 0);
    return () => clearTimeout(timer);
  }, [config.output.output_root]);
  // The bottom tabs follow the registered task (record 7.212, user: "after selecting specific task, it automatically load the
  // most recent corresponding run of the registered task. If there is no recent run, then leave run selection and run status
  // default blank unless you choose other runs"). When the page's task changes - chosen under Task, saved for the first time,
  // a choice taken back with Undo - the run list is read again and the task's newest run is shown (a Baseline simulation is
  // one of its runs), or no run. Not when the page opens: the run it showed is kept. A run chosen in the run window or
  // started while the list is read stays, and so does the run shown when the read fails or the page leaves its tasks for a
  // Virtuoso cell. The header's Start / Pause / Abort keep their own run. A server older than this page lists runs without
  // their task: the run shown stays then, instead of every choice showing none.
  const taskKey: string | null = config.circuit?.source === 'registered_task' ? config.circuit.task_id ?? null : null;
  const followedTask = useRef(taskKey);
  // The generation of the Runs window's Load run / New run like this (record 7.270, Astra's review of 2026-10-07): each one
  // takes the next number and goes on only while it is still the newest - a task chosen elsewhere lets it go too.
  const loadSerial = useRef(0);
  const shownNow = useRef(runDir);
  shownNow.current = runDir;
  useEffect(() => {
    if (taskKey === followedTask.current) return;
    followedTask.current = taskKey;
    loadSerial.current++;                                // a task chosen elsewhere: a Load run still on its way is let go
    if (!taskKey) return;
    const before = shownNow.current;
    readRuns().then(({ list, error }) => {
      if (error || followedTask.current !== taskKey || shownNow.current !== before) return;
      if (list.length && !list.some(r => 'task_key' in r)) return;
      setRunDir(list.find(r => r.task_key === taskKey)?.run_dir ?? null);
    });
  }, [taskKey]);

  const showRun = (started: Json, as: 'start' | 'resume', note = '') => {
    setRunDir(started.run_dir); setTab('status'); unfold(); refreshRuns();
    const said = note ? ` ${note}` : '';
    setMessage(as === 'resume' ? { level: 'info', text: `Continuing in the original run directory: ${started.run_dir}${said}` }
      : { level: started.mock ? 'mock' : 'info', text: `${started.mock ? started.mock_notice + ' ' : ''}Run directory: ${started.run_dir}${said}` });
  };
  // On success the run becomes the header's run and the shown run, in one place, and the message names it (record 7.261);
  // a paused run the header lets go of for it is named too - it stays paused, and Runs continues it.
  const launchedRun = (started: Json, as: 'start' | 'resume', note?: string) => {
    const resting = control.dir && control.dir !== started.run_dir && RESUMABLE.includes(control.status?.state) ? control.dir : null;
    control.take(started.run_dir, as);
    showRun(started, as, [note, resting && `${folderName(resting)} stays paused; continue it from Runs.`].filter(Boolean).join(' '));
  };
  // A task's baseline simulation, started by Save task (TaskSave.tsx), is taken into the header only when the header is free
  // or holds a run at rest (record 7.261): it used to replace a paused run without a word, and a live one too. A header that
  // holds no run is free while the page still reads the run list ("checking").
  const adoptBaseline = (started: Json) => {
    if (!control.dir || control.phase === 'idle' || control.phase === 'paused') { launchedRun(started, 'start', "The task's baseline simulation has started."); return; }
    refreshRuns();
    setMessage({ level: 'info', text: `The task's baseline simulation runs as ${folderName(started.run_dir)}; the header keeps its own run. The baseline is under Runs.` });
  };
  const automaticRun = useRef(adoptBaseline);
  automaticRun.current = adoptBaseline;
  useEffect(() => {
    const started = (event: Event) => automaticRun.current((event as CustomEvent<Json>).detail);
    window.addEventListener(TASK_BASELINE_STARTED, started);
    return () => window.removeEventListener(TASK_BASELINE_STARTED, started);
  }, []);

  // The run brief (record 7.264): the header's run chip opens it; Show results there does what the chip's press did.
  const brief = useRunBrief({ control, runs, onRefreshRuns: refreshRuns, onShow: dir => { setRunDir(dir); setTab('status'); unfold(); } });

  // ---- the launcher (record 7.261, launch.ts): Start, Calibration, Resume and Continue -------------------------------------
  const features = useMemo(() => featuresOf(meta), [meta]);
  const launcher = useLauncher({ control, features, onLaunched: launchedRun, onMessage: setMessage });
  // The backend's continuation check (when it has one): of the run shown, for Continue..., and of the header's paused run,
  // for Resume - the reason either cannot go on is said before the press.
  const shownCheck = useContinuation(features, runDir, status);
  const heldCheck = useContinuation(features, control.dir, control.phase === 'paused' ? control.status : null);
  const startBlocked = startReadiness(control.phase, validation) ?? (config.run.mode === 'resume' ? NO_MODE : null);
  // What Start would start (record 7.269; plan "The draft": "What Start will start is one line beside it ... It is also Start's
  // tooltip, with the reason when Start is disabled"): the task, Run configuration's model and network, the budget.
  const [nextModel, setNextModel] = useState<NextModel | null>(null);
  const nextTask: string | null = config.circuit?.source === 'registered_task' ? (config.circuit.task_id ? String(config.circuit.task_id).replace(/^real:/, '') : null)
    : config.circuit?.cell ? `${config.circuit.library}/${config.circuit.cell}` : null;
  const nextLine = nextModel ? `Next: ${nextTask ?? 'no task chosen'} · ${nextModel.model} · ${nextModel.network} · ${config.run.max_evaluations} evaluations` : null;
  const resumeBlocked = control.phase === 'paused'
    ? continueReadiness({ status: control.status, check: heldCheck, phase: control.phase, held: true, total: 'unchanged' }) : null;
  const continueBlocked = continueReadiness({ status, check: shownCheck, phase: control.phase, held: control.dir === runDir, total: 'form' });
  // What a refusal depends on: the configuration for Start and Calibration; for Resume and Continue the run - its state, save
  // point and total (a heartbeat is no reason: a paused run's status is read again and again without a change).
  const continueKey = (dir: string | null, of: Json) => `continue|${dir}|${of?.state}|${of?.worker_alive}|${of?.save_point}|${of?.budget?.max_evaluations}`;
  const refusal = launcher.refusal;
  const headerRefusal = refusal && ((refusal.action === 'start' || refusal.action === 'calibration') ? refusal.key === configKey
    : refusal.action === 'resume' && refusal.key === continueKey(control.dir, control.status)) ? refusal : null;
  const shownRefusal = refusal?.action === 'continue' && refusal.key === continueKey(runDir, status) ? refusal : null;
  // An ngspice netlist task is real too (circuit simulations, counted and recorded as such), only without a license.
  const start = (calibration_only: boolean) => {
    setMessage(null);
    const calibration_designs = calibration_only ? CALIBRATION_DESIGNS : 0;
    const budget = calibration_only ? calibration_designs : config.run.max_evaluations;
    const calibrationText = calibration_only ? `\n(${calibration_designs} random designs for calibration; no starting-design baseline.)` : '';
    launcher.go(calibration_only ? 'calibration' : 'start', configKey, null,
      flags => api.start({ config, calibration_only, ...(calibration_designs ? { calibration_designs } : {}), ...flags }), { real: !!isReal, transfer: true,
        authorizeText: (!isReal ? `Start ${budget} synthetic MOCK evaluations?` : circuit?.simulator === 'ngspice' ? `This starts ngspice simulations of the task (no license; every one is counted as a real evaluation).\nRun a budget of ${budget} candidate evaluation(s)?`
          : `This starts REAL Virtuoso/Spectre simulations.\nAuthorize a budget of ${budget} candidate evaluation(s)?`) + calibrationText },
      'Not started: you answered no, so nothing was created.');
  };
  // Continue... of the Run status tab: the run shown there, with the total of the budget form (null = unchanged). The
  // header's Resume is Continue of its own paused run with the total unchanged. Both go on from the run's own saved
  // configuration; the run becomes the header's run.
  const continueShown = (total: number | null) => {
    const dir = runDir;
    if (!dir) return;
    setMessage(null);
    launcher.go('continue', continueKey(dir, status), dir, flags => api.continueRun({ run_dir: dir, max_evaluations: total, ...flags }),
      continueConsent(status, shownCheck, total), 'Not continued: you answered no. The run stays as it was.');
  };
  const resumeHeld = () => {
    const dir = control.dir;
    if (!dir) return;
    setMessage(null);
    launcher.go('resume', continueKey(dir, control.status), dir, flags => api.continueRun({ run_dir: dir, max_evaluations: null, ...flags }),
      continueConsent(control.status, heldCheck, null), 'Not resumed: you answered no. The run stays paused.');
  };
  // The backend's alternative when Continue cannot go on (a changed task, older optimizer code...): the next run on this
  // page fine-tunes from the run's newest save point - pinned, as one Undo step. Nothing starts until Start.
  const fineTuneFrom = (alternative: Json) => {
    setConfig((c: Json) => ({ ...c, run: { ...c.run, mode: 'fine_tune',
      model_source: { ...(c.run.model_source ?? {}), run_dir: alternative.run_dir, checkpoint_id: alternative.checkpoint_id } } }));
    setMessage({ level: 'info', text: `The next run fine-tunes from ${folderName(alternative.run_dir)} at its save point ${alternative.checkpoint_id}, as a new `
      + 'run (Undo takes it back). Look at RL model..., then press Start.' });
  };

  // ---- the Runs window's actions (record 7.267; plan "Load run" and "Existing runs: continued in place") ---------------------------
  const taskLoad = useRef<TaskLoad | null>(null);
  /** The model a run ended with, pinned: a trained run's newest save point; an Evaluate-only run's the one it evaluated - its
   *  weights never changed -, else its own; a run with no save point (a baseline, one stopped before its first save) the
   *  one it started from. None of these: null, and the model stays as it is. */
  // A save point that is not there (404), or not under the allowed output folders (403), is absent: the next one is tried.
  // Any other failure - the server restarting, a timeout - stops the load, and nothing changes (record 7.270, Astra's review
  // of 2026-10-07: a passing failure used to load the run's parent model instead, and say it had worked).
  const readOrAbsent = (run_dir: string, checkpoint_id: string): Promise<SavePoint | null> =>
    readSavePoint(run_dir, checkpoint_id).catch(e => { if (e instanceof ApiError && (e.status === 404 || e.status === 403)) return null; throw e; });
  const endModel = async (row: Json): Promise<SavePoint | null> => {
    const own = () => readOrAbsent(row.run_dir, 'latest');
    const parent = () => (row.parent?.run_dir && row.parent?.checkpoint_id ? readOrAbsent(row.parent.run_dir, row.parent.checkpoint_id) : Promise.resolve(null));
    return row.mode === 'frozen' ? (await parent()) ?? (await own()) : (await own()) ?? (await parent());
  };
  /** When the run's task was saved again after the run began, or null. */
  const savedSince = async (row: Json): Promise<string | null> => {
    const task = (await tasksShared().catch(() => null))?.tasks?.find((t: Json) => t.task_key === row.task_key);
    return task?.saved_utc && row.created_utc && Date.parse(task.saved_utc) > Date.parse(row.created_utc) ? task.saved_utc : null;
  };
  /** The run's task, through the Tasks window's task load, with `change` in its one draft change; when it is the page's task
   *  already, `change` alone - the editors stay as they are, edits included. The task-run link (7.212) gives way: this task
   *  change comes with its run, and the caller decides what the bottom tabs show. */
  const withRunTask = async (row: Json, change: (c: Json) => Json, changes: boolean, stale: () => boolean): Promise<TaskLoaded> => {
    if (stale()) return { loaded: false, why: 'another choice came first' };
    if (taskKey === row.task_key) { if (changes) setConfig(change); return { loaded: true }; }
    const before = followedTask.current;
    followedTask.current = row.task_key;
    const result = await (taskLoad.current?.(row.task_key, change, stale) ?? Promise.resolve<TaskLoaded>({ loaded: false, why: 'the task panel is not ready yet' }));
    if (!result.loaded && followedTask.current === row.task_key) followedTask.current = before;
    return result;
  };
  const nameOf = (point: SavePoint) => modelNameAt(runs, point.run_dir);
  const sinceText = (since: string | null, what: string) => since
    ? ` The task was saved again after ${what} began (${new Date(since).toLocaleString()}): the RL model window's check says whether the model still fits.` : '';
  /** Load run: its task, the model it ended with (in a Mode that loads one) and its results - one Undo step for the task and
   *  the model, all or nothing. The header's run is never touched. */
  const loadRun = async (row: Json) => {
    const mine = ++loadSerial.current, stale = () => mine !== loadSerial.current;      // a newer choice wins, silently
    setMessage(null);
    let point: SavePoint | null, since: string | null;
    try { [point, since] = await Promise.all([endModel(row), savedSince(row)]); }
    catch (e: any) {
      if (!stale()) setMessage({ level: 'error', text: `Run ${runTitle(row)} was not loaded: its model could not be read (${plainError(e)}). Nothing changed.` });
      return;
    }
    if (stale()) return;
    const mode = LOADS.includes(config.run.mode) ? config.run.mode : 'fine_tune';
    const same = taskKey === row.task_key;
    const result = await withRunTask(row, c => (point ? { ...c, run: withSavePoint({ ...c.run, mode: LOADS.includes(c.run.mode) ? c.run.mode : 'fine_tune' }, point) } : c), !!point, stale);
    if (stale()) return;
    if (!result.loaded) { setMessage({ level: 'info', text: `Run ${runTitle(row)} was not loaded: ${result.why}. Nothing changed.` }); return; }
    setRunDir(row.run_dir); setTab('status'); unfold();
    setMessage({ level: 'info', text: `Loaded run ${runTitle(row)}: task ${row.task_key}${same ? ' (already on the page: the editors stay as they were)' : ''}, `
      + (point ? `${MODE_NAME[mode]} from ${nameOf(point)} @ ${point.evaluations ?? point.checkpoint_id}.` : 'the model as it was: this run has no save point and loaded none.')
      + `${sinceText(since, 'this run')} Undo takes it back.` });
  };
  /** New run like this: the next run repeats the run - its task, Mode, the save point it started from and its run settings.
   *  The shown run stays. */
  const newRunLike = async (row: Json) => {
    const mine = ++loadSerial.current, stale = () => mine !== loadSerial.current;
    setMessage(null);
    let settings: Json = null;
    try { settings = migrateConfig(await api.runConfig(row.run_dir))?.run ?? null; }
    catch (e: any) { if (!stale()) setMessage({ level: 'error', text: `New run like ${runTitle(row)}: its configuration could not be read (${e.message}). Nothing changed.` }); return; }
    if (stale()) return;
    if (!settings) { setMessage({ level: 'error', text: `New run like ${runTitle(row)}: the run has no configuration of its own. Nothing changed.` }); return; }
    // A run continued under the old Mode resume repeats as what it was: a fine-tune of its model, or a new model.
    const mode = settings.mode === 'resume' ? (row.parent?.run_dir ? 'fine_tune' : 'scratch') : settings.mode;
    const from = LOADS.includes(mode) ? row.parent : null;
    const [point, since] = await Promise.all([from?.run_dir && from?.checkpoint_id ? readSavePoint(from.run_dir, from.checkpoint_id).catch(() => null) : Promise.resolve(null), savedSince(row)]);
    if (stale()) return;
    const copied = Object.fromEntries(RUN_SETTINGS.filter(k => k in settings).map(k => [k, settings[k]]));
    const result = await withRunTask(row, c => {
      const run = { ...c.run, ...copied, mode };
      return { ...c, run: point ? withSavePoint(run, point) : { ...run, model_source: { ...(c.run.model_source ?? {}),
        run_dir: from?.run_dir ?? null, checkpoint_id: from?.run_dir ? from.checkpoint_id ?? 'latest' : 'latest' } } };
    }, true, stale);
    if (stale()) return;
    if (!result.loaded) { setMessage({ level: 'info', text: `New run like ${runTitle(row)}: not taken, ${result.why}. Nothing changed.` }); return; }
    setMessage({ level: 'info', text: `The next run repeats ${runTitle(row)}: task ${row.task_key}, ${MODE_NAME[mode] ?? mode}`
      + (from ? ` from ${point ? `${nameOf(point)} @ ${point.evaluations ?? point.checkpoint_id}` : `${folderName(from.run_dir)}'s save point ${from.checkpoint_id} (it could not be read now)`}` : '')
      + `, ${settings.max_evaluations} evaluations, seed ${settings.seed}, with its network, training values, reward, conditions and limits.`
      + `${sinceText(since, 'that run')} A model name already taken gets a number at the start. Undo takes it back.` });
  };
  /** Continue... of the Runs window: the run is shown under Run status with its budget form open, where it goes on. */
  const [askContinue, setAskContinue] = useState<{ runDir: string; serial: number } | null>(null);
  const continueFrom = (row: Json) => { setRunDir(row.run_dir); setTab('status'); unfold(); setAskContinue(a => ({ runDir: row.run_dir, serial: (a?.serial ?? 0) + 1 })); };

  // ---- the splitter above the bottom panel (record 7.158): nothing moves unless it is dragged, double-clicked or keyed --------
  const layoutRef = useRef<HTMLDivElement>(null);
  const fitBottom = (px: number) => {
    const tabs = layoutRef.current?.querySelector<HTMLElement>('footer > .tabs')?.offsetHeight ?? 34;
    return Math.round(Math.max(tabs + 60, Math.min(px, window.innerHeight - 280)));   // the editors keep room
  };
  const dragBottom = (e: ReactPointerEvent<HTMLDivElement>) => {
    const layout = layoutRef.current, foot = e.currentTarget.parentElement;
    if (e.button !== 0 || !layout || !foot) return;
    e.preventDefault();
    const handle = e.currentTarget, edge = foot.getBoundingClientRect().bottom;
    handle.setPointerCapture(e.pointerId);
    let height: number | null = null;          // drawn while dragged, remembered once let go
    const move = (m: PointerEvent) => { height = fitBottom(edge - m.clientY); layout.style.setProperty('--foot', `${height}px`); layout.classList.remove('bottom-folded'); };
    const end = () => {
      handle.removeEventListener('pointermove', move); handle.removeEventListener('pointerup', end); handle.removeEventListener('pointercancel', end);
      const dragged = height;
      if (dragged !== null) { setOpened(true); changeBottom(() => ({ height: dragged, folded: false })); }
    };
    handle.addEventListener('pointermove', move); handle.addEventListener('pointerup', end); handle.addEventListener('pointercancel', end);
  };
  const keyBottom = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleBottom(); return; }
    const step = e.key === 'ArrowUp' ? 24 : e.key === 'ArrowDown' ? -24 : 0;
    if (!step) return;
    e.preventDefault();
    const now = e.currentTarget.parentElement?.getBoundingClientRect().height ?? 0;
    setOpened(true); changeBottom(() => ({ height: fitBottom(now + step), folded: false }));
  };

  if (fatal) return <p className="error">Backend not reachable: {fatal}</p>;
  if (!schema) return <p>Loading schema...</p>;
  return (
    <div className={`layout${folded ? ' bottom-folded' : ''}`} ref={layoutRef} style={bottom.height ? { '--foot': `${bottom.height}px` } as CSSProperties : undefined}>
      <header>
        {/* The title block (record 7.158): the page names what it works on - the task's facts come from the circuit panel. The
            version and the environment are one hover away, on the name. */}
        <div className="title-block">
          <span className="tb-brand" title={`GATOR workbench ${meta?.version ?? ''} | ${meta?.environment?.environment ?? ''} | data-only outputs (no plots)`}>
            <b>GATOR</b><span className="tb-sub">workbench</span></span>
          <LookSwitch />
          <span className="tb-facts" ref={setTitleSlot} />
          {/* The Connection button in the title block (record 7.182, user: "move the conection button to the header"): its name
              over the connection and its state, as the cells beside it; it opens the connection window as before. */}
          <ConnectionButton profileId={profileId} setProfileId={(id, record) => setConfig((c: Json) => ({ ...c, run: { ...c.run, connection_profile_id: id } }), record)} />
        </div>
        {/* The hand-edited settings.json is not valid JSON: the backend works on defaults and leaves the file alone. Said on a
            line of its own under the header, as /api/meta said it when the page opened - never hidden, not dismissable. */}
        {meta?.settings_problem && <p className="settings-problem warn">{meta.settings_problem}</p>}
        {store.saveError && <div className="settings-problem persistence-problem error" role="alert">
          <span>{store.saveError}</span><button onClick={store.retrySave}>Retry save</button>
          <button onClick={() => saveJson(`${config.project.task_name || 'configuration'}.json`, config)}>Export JSON</button>
        </div>}
        {/* "Calibration ready" (record 7.204): the Calibration run the header holds has ended. A line of its own under the
            header, like the two above; it goes when it is answered, when the page holds the values, or with the next run. */}
        {/* A refusal of Start, Calibration or Resume (record 7.261): it stays on a line of its own until what it depends on
            changes - the configuration, or the header's run - or it is closed. */}
        {headerRefusal && <LaunchRefusal refusal={headerRefusal} onDismiss={() => launcher.setRefusal(null)} />}
        {calibrationReady && calibrationOffer && <div className="calibration-ready" role="status">
          {calibrated.status === 'calibrated'
            ? <><span><b>Calibration ready</b>{calibrated.task_key ? ` for ${calibrated.task_key}` : ''}: {calibrationOffer.values}. <span className="hint">Proposed
                from {calibrated.designs?.scored} random designs; nothing has changed yet. The table is under Run status.</span></span>
              {calibrationOffer.saves
                ? <><button className="primary" onClick={() => answerCalibration('save')} title={`Apply and save: Writes ${calibrationOffer.what} into the page, as one Undo step, ${APPLY_AND_SAVE}`}>Apply and save</button>
                    <button onClick={() => answerCalibration('apply')} title={`Apply only: Writes ${calibrationOffer.what} into the page, as one Undo step. Nothing is simulated and no task is saved.${calibrationOffer.afterwards}`}>Apply only</button></>
                : <button onClick={() => answerCalibration('apply')} title={`Apply calibration: Writes ${calibrationOffer.what} into the page, as one Undo step. Nothing is simulated and no task is saved.${calibrationOffer.afterwards}`}>Apply calibration</button>}
              <button onClick={() => answerCalibration('no')} title="Not now: Leaves everything as it is. The proposals stay under Run status of this run, with Apply calibration.">Not now</button></>
            : <><span><b>Calibration finished:</b> nothing is proposed. {calibrated.reason}</span>
              <button onClick={() => answerCalibration('no')} title="Closes this line. The run's numbers stay under Run status.">OK</button></>}
        </div>}
        <span className="spacer" />
        <ValidationStatus validation={validation} config={config} schema={schema} />
        <button disabled={!!startBlocked} onClick={() => start(true)}
          title={startBlocked ? `Calibration: ${startBlocked}`
            : `${CALIBRATION_DESIGNS} random designs over the Parameters ranges, each costed. No starting-design baseline. `
              + 'Proposes a Scale for each Specs row and the Initial alpha; Run status shows them with Apply, nothing changes by itself.'}>Calibration</button>
        <RunButtons control={control} startBlocked={startBlocked} resumeBlocked={resumeBlocked} onStart={() => start(false)} onResume={resumeHeld}
          onMessage={setMessage} onChip={brief.open} next={nextLine} />
        {brief.element}
      </header>
      {message && <div className={`banner ${message.level}`} onClick={() => setMessage(null)}>
        {/* A start refused by the check before every run: its steps say it all (what differs, what to do). */}
        {message.detail?.code === 'consistency' && message.detail.report?.steps ? <CheckSteps result={message.detail.report} refused />
          : <>{message.text}{(message.detail?.code || message.detail?.report) && <details onClick={e => e.stopPropagation()}><summary>Technical details</summary>
            <pre>{[message.detail.code && `code: ${message.detail.code}`, message.detail.report && JSON.stringify(message.detail.report, null, 1)].filter(Boolean).join('\n')}</pre></details>}</>}</div>}
      <aside className="left">
        <CircuitPanel config={config} setConfig={setConfig} circuit={circuit} setCircuit={setCircuit} profileId={profileId}
          taskSlot={taskSlot} taskNotes={taskNotes} titleSlot={titleSlot}
          taskEpoch={taskEpoch} runs={runs} refreshRuns={refreshRuns} taskLoad={taskLoad} />
      </aside>
      <main>
        <Editors schema={schema} config={config} setConfig={setConfig} undo={store.undo} redo={store.redo} canUndo={store.canUndo} canRedo={store.canRedo}
          validation={validation} taskSlot={setTaskSlot} taskNotes={setTaskNotes} />
      </main>
      <aside className="right">
        <RunPanel schema={schema.json_schema} config={config} setConfig={setConfig} runs={runs} circuit={circuit} onNext={setNextModel} />
        <OutputPanel config={config} setConfig={setConfig} meta={meta} activeRun={status} />
        <ResearchPanel config={config} setConfig={setConfig} />
      </aside>
      <footer>
        <div className="splitter" role="separator" aria-orientation="horizontal" tabIndex={0} aria-label="Height of the bottom panel"
          aria-valuemin={0} aria-valuemax={100} aria-valuenow={folded ? 0 : bottom.height ? Math.min(100, Math.round(bottom.height / window.innerHeight * 100)) : 34}
          title="Drag to give the bottom panel more or less room. Double-click: fold it down to its tab line, or open it again. Kept in this browser."
          onPointerDown={dragBottom} onDoubleClick={toggleBottom} onKeyDown={keyBottom} />
        <div className="tabs">
          <AgentWindowTab config={config} />
          {(['status', 'logs', 'data', 'files', 'training', 'corners'] as BottomTab[]).filter(t => t !== 'corners' || cornersUsable).map(t => <button key={t} className={t === tab ? 'active' : ''} onClick={() => { setTab(t); unfold(); }}>
            {{ status: 'Run status', logs: 'Logs', data: 'Data tables', files: 'Output files', training: 'Training', corners: 'Corner check' }[t]}</button>)}
          <span className="spacer" />
          <RunListButton runs={runs} runsError={runsError} runDir={runDir} status={status} onChoose={dir => { setRunDir(dir); if (dir) unfold(); }} onRefresh={refreshRuns}
            onLoad={row => void loadRun(row)} onNewLike={row => void newRunLike(row)} onContinue={continueFrom} />
        </div>
        <div className="bottom-body">
          {tab === 'status' && <StatusTab status={status} runDir={runDir} error={statusError} check={shownCheck} continueBlocked={continueBlocked} refusal={shownRefusal}
            onContinue={continueShown} onDismissRefusal={() => launcher.setRefusal(null)} onFineTune={fineTuneFrom} config={config} setConfig={setConfig} ask={askContinue} />}
          {tab === 'logs' && <LogsTab runDir={runDir} alive={!!status?.worker_alive} />}
          {tab === 'data' && <DataTab runDir={runDir} status={status} />}
          {tab === 'files' && <FilesTab runDir={runDir} />}
          {/* Stays mounted: its recorded numbers and chosen charts survive a look at another tab; hidden - another
              tab, or the panel folded to its tab line - it reads and draws nothing (record 7.193). */}
          <TrainingTab hidden={tab !== 'training' || folded} runDir={runDir} status={status} runs={runs} />
          {tab === 'corners' && cornersUsable && <CornerCheckTab runDir={runDir} />}
        </div>
      </footer>
    </div>
  );
}
