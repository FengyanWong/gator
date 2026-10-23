import { CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, ApiError, Json, NO_ANSWER, plainError, saveJson } from './api';
import { setUnitForms } from './units';
import { rowsFrom, useConfig, useRequest, useTaskSaves } from './store';
import { CircuitPanel } from './panels/Left';
import { ConnectionButton } from './panels/Connection';
import { CheckSteps } from './panels/Consistency';
import { Editors } from './panels/Editors';
import { ValidationStatus } from './panels/Issues';
import { otherTask, RunButtons, RunChip } from './panels/RunControl';
import { WindowsMenu } from './panels/WindowsMenu';
import { ENDED, RESUMABLE } from './runState';
import { CALIBRATION_DESIGNS, useLaunchActions } from './launch';
import { LaunchRefusal } from './panels/LaunchRefusal';
import { useRunBrief } from './panels/RunBrief';
import { RunPanel } from './panels/Right';
import { OutputPanel } from './panels/OutputPanel';
import { ResearchPanel } from './panels/ResearchPanel';
import { folderName } from './format';
import { APPLY_AND_SAVE } from './panels/calibrationPlan';
import { TASK_BASELINE_STARTED } from './panels/TaskSave';
import { CrashPanel } from './panels/CrashPanel';
import { BottomPanel, type BottomTab, useBottomPanel } from './panels/BottomPanel';
import { useCalibrationOffer } from './page/calibrationOffer';
import { useRunWindowActions } from './page/runWindowActions';
import { shownRun, useRunList, useShownRun } from './page/shownRun';
import { type Takeover, useLiveRunAdoption } from './page/liveRunAdoption';
import { useTaskRunFollow } from './page/taskRunFollow';
import { keep, oncePerBrowser, readKept } from './kept';
import { CIRCUIT_SHOWN_KEY } from './contract';

/** How long a click on the message line waits for a second one before it closes the line: Windows' default double-click
 *  time (the page cannot read the user's own). */
const DOUBLE_CLICK_MS = 500;

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

/** The page's name as a chip (record 7.360, Draft A of the Roadster look; user: "the icon looks nice"): the name in a package
 *  outline with five pins along each long edge, and the red dot that marks pin 1 on a real chip. */
function GatorChip() {
  return (<svg className="gator-chip" width="86" height="34" viewBox="0 0 116 46" role="img" aria-label="GATOR">
    <path d="M26 2v5M42 2v5M58 2v5M74 2v5M90 2v5M26 39v5M42 39v5M58 39v5M74 39v5M90 39v5" className="gator-chip-pins" />
    <rect x="8" y="7" width="100" height="32" rx="8" className="gator-chip-body" />
    <circle cx="17" cy="15" r="2.5" className="gator-chip-pin1" />
    <text x="58" y="28.5" textAnchor="middle" className="gator-chip-name">GATOR</text>
  </svg>);
}

/** Layout (specification section 2; record 7.362, Option D of the user's preview): the task across the left and the centre - its
 *  name, revision and actions on the editors' tab line, the three editors under it - with the circuit beside them on request;
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
  const [runDir, setRunDir] = useState<string | null>(shownRun);
  const [tab, setTab] = useState<BottomTab>('status');
  const panel = useBottomPanel(runDir);
  const { bottom, folded, unfold, layoutRef } = panel;
  const [titleSlot, setTitleSlot] = useState<HTMLElement | null>(null);            // the header's title block: the circuit panel puts the task's facts there
  const [taskSlot, setTaskSlot] = useState<HTMLElement | null>(null);              // editors' tab line: where the circuit panel puts "Save task"
  const [taskNotes, setTaskNotes] = useState<HTMLElement | null>(null);            // under the editors' toolbar: its messages and questions
  const [taskHead, setTaskHead] = useState<HTMLElement | null>(null);              // the tab line's start: the task, by name (record 7.362)
  const [taskTools, setTaskTools] = useState<HTMLElement | null>(null);            // the tab line's end, before Save task: Check now (record 7.362)
  const [taskStatus, setTaskStatus] = useState<HTMLElement | null>(null);          // under the editors' toolbar: the task's own lines (record 7.362)
  // The circuit column (record 7.362, user: "go with D"): folded away by default, so the task's rows take the width; "Show
  // circuit" on the tab line brings it back beside them. The choice is kept in this browser.
  const [circuitShown, setCircuitShown] = useState(() => readKept(s => s.getItem(CIRCUIT_SHOWN_KEY) === 'shown', () => false));
  const toggleCircuit = useCallback(() => setCircuitShown(now => !now), []);      // stable: the editors are memoised (record 7.275)
  useEffect(() => keep(s => { if (circuitShown) s.setItem(CIRCUIT_SHOWN_KEY, 'shown'); else s.removeItem(CIRCUIT_SHOWN_KEY); }), [circuitShown]);
  const [message, setMessage] = useState<Json>(null);
  // The message line closes a moment after a click, not on it (review of branch record SIF-56): the first click of a double
  // click - how one word, such as a run's folder name, is taken - comes before anything is selected, and closed the line
  // before the second. A second or third click cancels the close; a selection made by then (a drag, a double click) keeps
  // the line, and a click that only collapses one closes it.
  const closing = useRef(0);
  const closeMessage = (clicks: number) => {
    window.clearTimeout(closing.current);
    if (clicks > 1) return;
    const shown = message;                                                         // a newer message is not closed by this click
    closing.current = window.setTimeout(() => {
      if (!window.getSelection()?.toString()) setMessage((now: Json) => (now === shown ? null : now));
    }, DOUBLE_CLICK_MS);
  };
  // Two output defaults changed (record 7.280): a save point every 200 evaluations (50 before) and the data tables written
  // every 64 (16 before). A draft keeps the values it was made with, so, once per browser, a draft that still holds an old
  // default exactly gets the new one - as one Undo step, and said; a value chosen otherwise is kept.
  useEffect(() => {
    if (!oncePerBrowser('gator-workbench-output-defaults-2026-10-08')) return;   // without lasting storage a value the user restored would be changed again
    const out = config.output ?? {};
    const saves = out.checkpoint_every_evaluations === 50 && out.checkpoint_every_seconds == null, tables = out.flush_every_evaluations === 16;
    if (!saves && !tables) return;
    setConfig((c: Json) => ({ ...c, output: { ...c.output, ...(saves ? { checkpoint_every_evaluations: 200 } : {}),
      ...(tables ? { flush_every_evaluations: 64 } : {}) } }));
    setMessage({ level: 'info', text: `Updated to the new defaults (record 7.280): ${[saves && 'a save point every 200 evaluations (was 50)',
      tables && 'the data tables written every 64 evaluations (was 16)'].filter(Boolean).join(' and ')}. Undo restores the old values.` });
  }, []);
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
    }).catch(e => setFatal(plainError(e)));     // said as the rest of the page says it: how to start the backend again (branch record SIF-56)
  }, []);
  const { runs, runsError, readRuns, refreshRuns } = useRunList(config.output.output_root);

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

  const { status, statusError, cornersUsable, isReal, control, setLooked } = useShownRun({ runDir, setRunDir, tab, setTab, circuit });
  const { calibrated, calibrationOffer, calibrationReady, answerCalibration } = useCalibrationOffer({ control, config, setConfig, setMessage });
  // When the header's run comes to rest, the Project column reads its task again (a finished Baseline simulation
  // records the task's reference by itself, status record 7.78): a counter the column follows. Not on the page's first look,
  // and not after a start that never ran (refused or declined) or a paused run let go: nothing about the task changed.
  const [taskEpoch, setTaskEpoch] = useState(0);
  const lastPhase = useRef(control.phase);
  useEffect(() => {
    if (control.phase === 'idle' && ['starting', 'resuming', 'running', 'pausing', 'aborting', 'finishing'].includes(lastPhase.current)) setTaskEpoch(n => n + 1);
    lastPhase.current = control.phase;
  }, [control.phase]);
  const [takeover, setTakeover] = useState<Takeover | null>(null);             // the run taken over when the page opened (record 7.372)
  useLiveRunAdoption({ control, outputRoot: config.output.output_root, refreshRuns, setRunDir, setTakeover, setLooked });
  // The bottom tabs follow the registered task (record 7.212): page/taskRunFollow.ts.
  const { taskKey, loadSerial, followTask } = useTaskRunFollow({ config, runDir, readRuns, setRunDir });

  const showRun = (started: Json, as: 'start' | 'resume', note = '') => {
    setRunDir(started.run_dir); setTab('status'); unfold(); refreshRuns();
    // Which Virtuoso session the run went to, when its connection has more than one (record 7.351).
    const said = [note, started.virtuoso_session?.said].filter(Boolean).map(text => ` ${text}`).join('');
    // The run by its folder's name, as the other messages name runs; the full path is the line's tooltip, and Run status
    // shows it (branch record SIF-56: the line led with the absolute path, the words that mattered at its end).
    setMessage(as === 'resume' ? { level: 'info', text: `Continuing ${folderName(started.run_dir)} in its own folder.${said}`, title: started.run_dir }
      : { level: started.mock ? 'mock' : 'info', text: `${started.mock ? started.mock_notice + ' ' : ''}Started ${folderName(started.run_dir)}.${said}`, title: started.run_dir });
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
    if (!control.dir || control.phase === 'idle' || control.phase === 'paused') { launchedRun(started, 'start', "It is the task's baseline simulation."); return; }
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
  // The task's name as the header's title gives it, which the circuit panel says, for the "Next:" line (branch record SIF-71).
  const [taskShown, setTaskShown] = useState<string | null>(null);
  const { launcher, shownCheck, startBlocked, setNextModel, nextLine, resumeBlocked, continueBlocked, headerRefusal, shownRefusal, start,
    continueShown, resumeHeld, fineTuneFrom } = useLaunchActions({ control, meta, config, setConfig, configKey, validation, runDir, status, circuit,
    isReal: !!isReal, launchedRun, setMessage, taskShown });
  // Branch record SIF-72 (the survey found a run of graphgps_ldo1 in the header under the title mscr_vco_lin_c, the bottom tabs
  // on yet another run, and nothing that told the three apart): the header's run is named by its task when the title names
  // another (its chip and Abort's question); while it works or is paused, the bottom tabs offer it when they show another, and
  // Run configuration says that it is for the next Start.
  // Not while a launch is on its way to another run (review of SIF-72): the chip reads "starting" at once, but the header holds
  // the run it held before until the backend answers (launchedRun) - an ended run, or a paused one it then lets go of. Start
  // always makes a new run; a Continue while the header's run has ended is of the run the tabs show. Resume of the header's
  // paused run is of that run, and keeps it.
  const launching = control.pending === 'start' || (control.pending === 'resume' && ENDED.includes(control.status?.state));
  const headerTask = launching ? null : otherTask(runs.find(r => r.run_dir === control.dir), taskKey, taskShown);
  const headerHeld = !!control.dir && !launching && control.phase !== 'idle' && control.phase !== 'checking';
  // Branch record SIF-91: the output root locks while the header's run works, or a Start or Resume is on its way (the header
  // then still holds the run before, whose status is not the new one's) - it followed the run the tabs show, so with an ended
  // run shown the root could be changed under a live run, and the run list moved away from it.
  const headerWorks = !!control.status?.worker_alive || control.phase === 'starting' || control.phase === 'resuming';

  // ---- the Runs window's actions (record 7.267; plan "Load run" and "Existing runs: continued in place"): page/runWindowActions.ts
  const { taskLoad, askContinue, runWindow } = useRunWindowActions({ config, setConfig, runs, taskKey, followTask, loadSerial, setMessage, setRunDir, setTab, unfold });

  // Branch record SIF-56: a page whose backend does not answer as it opens says what to do, with Reload; it read the browser's
  // own "Backend not reachable: Failed to fetch". And the page opens in words, not "Loading schema...".
  if (fatal) return <p className="error">The workbench could not open. {fatal} <button onClick={() => window.location.reload()}>Reload</button></p>;
  if (!schema) return <p className="hint">Opening the workbench...</p>;
  return (
    <div className={`layout${folded ? ' bottom-folded' : ''}${circuitShown ? ' circuit-shown' : ''}`} ref={layoutRef} style={bottom.height ? { '--foot': `${bottom.height}px` } as CSSProperties : undefined}>
      <header>
        {/* The title block (record 7.158; the banner of the Roadster look, record 7.360): the name as a chip, then what the page
            works on - the task and its facts come from the circuit panel. The version and the environment are one hover away,
            on the chip. One look since record 7.360: the look switch went with the day look. */}
        <div className="title-block">
          <span className="tb-brand" title={`GATOR workbench ${meta?.version ?? ''} | ${meta?.environment?.environment ?? ''} | data-only outputs (no plots)`}>
            <GatorChip /></span>
          <span className="tb-facts" ref={setTitleSlot} />
          {/* The Connection button in the title block (record 7.182, user: "move the conection button to the header"): its name
              over the connection and its state, as the cells beside it; it opens the connection window as before. */}
          <ConnectionButton profileId={profileId} setProfileId={(id, record) => setConfig((c: Json) => ({ ...c, run: { ...c.run, connection_profile_id: id } }), record)} />
        </div>
        <RunChip control={control} onChip={brief.open} takeover={takeover} task={headerTask} />
        <WindowsMenu />
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
              <button onClick={() => answerCalibration('no')} title="Not now: Leaves everything as it is. The proposals stay under Run status of this run, with its Apply buttons.">Not now</button></>
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
          onMessage={setMessage} next={nextLine} task={headerTask} />
        {brief.element}
      </header>
      {/* The message line: a click closes it, a click that ends a selection of its text (to copy it) keeps it, and its tooltip
          says so, under the full path when the message names a run by its folder (branch record SIF-56: dragging across the
          line to copy it took it away). The close mark is drawn by CSS (roadster.css), so the line's text is the message alone.
          "Technical details" opens without closing the line, so its empty title keeps the line's tooltip off it (review of SIF-56). */}
      {message && <div className={`banner ${message.level}`} title={[message.title, 'Click to close (selecting text keeps it).'].filter(Boolean).join('\n')}
        onClick={e => closeMessage(e.detail)}>
        {/* A start refused by the check before every run: its steps say it all (what differs, what to do). */}
        {message.detail?.code === 'consistency' && message.detail.report?.steps ? <CheckSteps result={message.detail.report} refused />
          : <>{message.text}{(message.detail?.code || message.detail?.report) && <details title="" onClick={e => e.stopPropagation()}><summary>Technical details</summary>
            <pre>{[message.detail.code && `code: ${message.detail.code}`, message.detail.report && JSON.stringify(message.detail.report, null, 1)].filter(Boolean).join('\n')}</pre></details>}</>}</div>}
      <aside className="left">
        <CircuitPanel config={config} setConfig={setConfig} circuit={circuit} setCircuit={setCircuit} profileId={profileId} schema={schema}
          taskSlot={taskSlot} taskNotes={taskNotes} taskHead={taskHead} taskTools={taskTools} taskStatus={taskStatus} titleSlot={titleSlot}
          taskEpoch={taskEpoch} runs={runs} refreshRuns={refreshRuns} taskLoad={taskLoad} onTaskName={setTaskShown} />
      </aside>
      <main>
        <Editors schema={schema} config={config} setConfig={setConfig} undo={store.undo} redo={store.redo} canUndo={store.canUndo} canRedo={store.canRedo}
          lastStep={store.lastStep} validation={validation} taskSlot={setTaskSlot} taskNotes={setTaskNotes} taskHead={setTaskHead} taskTools={setTaskTools}
          taskStatus={setTaskStatus} circuitShown={circuitShown} onCircuit={toggleCircuit} onCramped={panel.foldForRows} />
      </main>
      <aside className="right">
        {/* The RL model window it holds has Undo and Redo of its own (branch record SIF-97): the page's one history. */}
        <RunPanel schema={schema.json_schema} config={config} setConfig={setConfig} runs={runs} refreshRuns={refreshRuns} circuit={circuit} onNext={setNextModel} runHeld={headerHeld}
          undo={store.undo} redo={store.redo} canUndo={store.canUndo} canRedo={store.canRedo} />
        <OutputPanel config={config} setConfig={setConfig} meta={meta} activeRun={status} headerWorks={headerWorks} runs={runs}
          taskMock={circuit?.loaded && typeof circuit.mock === 'boolean' ? circuit.mock : null} />
        <ResearchPanel config={config} setConfig={setConfig} />
      </aside>
      <BottomPanel panel={panel} tab={tab} setTab={setTab} cornersUsable={cornersUsable} config={config} setConfig={setConfig} runs={runs} runsError={runsError}
        runDir={runDir} status={status} statusError={statusError} runWindow={runWindow} refreshRuns={refreshRuns} shownCheck={shownCheck}
        continueBlocked={continueBlocked} shownRefusal={shownRefusal} continueShown={continueShown} launcher={launcher} fineTuneFrom={fineTuneFrom}
        askContinue={askContinue} headerDir={headerHeld ? control.dir : null} />
    </div>
  );
}
