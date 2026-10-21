// One launcher (record 7.261; plan docs/plan-frontend-run-workflow.md, "One launcher" and "Existing runs: continued in
// place"). Start, Calibration, Resume and Continue go through here, where each did every step its own way in App.start,
// App.continueRun and RunButtons.resume until then:
//   1. readiness - one pure function per action says whether it can run and why not, in words the button shows;
//   2. one pending state - the header's (useRunControl.setPending), so a second press anywhere finds "Starting...";
//   3. the questions the backend asks (launchWithConsent), as before;
//   4. a request id for each launch, kept in this tab until it is answered: a repeat gets the run the first one made,
//      and after a reload during a launch the page asks what became of it instead of sending it again;
//   5. on success the run becomes the header's run and the shown run, in one place, named in the message;
//   6. on refusal the backend's reason stays beside the action until what it depends on changes - no fallback.
// Request ids and the continuation check are used only where the backend lists them (GET /api/meta `features`): a page
// newer than its backend works as before until the backend is restarted.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, ApiError, Json, plainError } from './api';
import { useRequest } from './store';
import { restingFor, type RunControl } from './runState';
import { BLOCKING_LEVELS, LAUNCH_KEY } from './contract';
import { keepInTab, readKeptInTab } from './kept';
import { folderName, layerWords, plural } from './format';
import type { NextModel } from './panels/rlModelText';

export type Action = 'start' | 'calibration' | 'resume' | 'continue';
export type Features = { requests: boolean; continuation: boolean };
export const featuresOf = (meta: Json): Features => {
  const listed: unknown[] = Array.isArray(meta?.features) ? meta.features : [];
  return { requests: listed.includes('launch_requests'), continuation: listed.includes('continuation_check') };
};

// ---- the launch on its way, kept in this tab (sessionStorage) until its answer has arrived ----------------------------------
type SentLaunch = { id: string; action: Action; run_dir: string | null; at: number };
const sentLaunch = (): SentLaunch | null => readKeptInTab(s => {
  const kept = JSON.parse(s.getItem(LAUNCH_KEY) ?? 'null');
  return kept && typeof kept.id === 'string' ? kept : null;
}, () => null);
const keepLaunch = (launch: SentLaunch | null) => {
  keepInTab(s => { if (launch) s.setItem(LAUNCH_KEY, JSON.stringify(launch)); else s.removeItem(LAUNCH_KEY); });   // blocked storage: no recovery after a reload
};
/** A launch of this tab is still waiting for its answer (or for the page to ask after a reload). */
export const launchKept = () => sentLaunch() !== null;
const newRequestId = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 14)}`;

/** The question when the BACKEND says a run is real although the page took it for MOCK (a task chosen a moment ago
 *  whose circuit had not been read yet, or a run whose status was not known): worded from the backend's own report,
 *  never from the page's MOCK text - an OK here authorizes real simulations (audit 2026-09-30). The questions count in the
 *  right number, "1 candidate evaluation" / "600 candidate evaluations" (they said "evaluation(s)"; branch record SIF-45). */
const realQuestion = (report: Json) => `This runs REAL simulations${report?.task_key ? ` of ${report.task_key}` : ''} (the page had taken it for a MOCK run).\n`
  + `Authorize a total budget of ${report?.requested_max_evaluations != null ? plural(report.requested_max_evaluations, 'candidate evaluation') : 'its candidate evaluations'}?`;

/** The question when the connection test could not say whether parts the run needs work (their state unknown, busy or not
 *  checked): the parts in words, and the button that tests them - "Full test (Spectre, license)" for the Spectre parts, which
 *  "Test connection" leaves out. It read "Connection layers are UNKNOWN: session_readiness, spectre_license. Unknown is not OK.
 *  Proceed anyway?" (branch record SIF-55); the button's name follows it ("+ Spectre / license" until branch record SIF-79). */
const connectionQuestion = (uncertain: string[]) => `These parts of the connection are not known to work: ${uncertain.map(layerWords).join(', ')}.\n`
  + `Cancel, then press ${uncertain.some(layer => layer.startsWith('spectre')) ? '"Full test (Spectre, license)"' : '"Test connection"'} in the Connection window; or OK to go ahead anyway.`;

/** The backend never starts on a guess: it refuses, creates nothing, and names what it needs - the budget of a REAL
 *  simulation, a model trained on another task, connection layers it could not check. Each question is put to the
 *  user once and the request is repeated with the answers. Returns null when the user said no. A Mode is named as its
 *  button names it, "Fine-tune" (the question said "fine_tune"; branch record SIF-53). */
export async function launchWithConsent(send: (flags: Json) => Promise<Json>, options: { real: boolean; authorizeText: string; transfer?: boolean }): Promise<Json | null> {
  const flags: Json = {};
  if (options.real) {
    if (!window.confirm(options.authorizeText)) return null;
    flags.authorize_real_simulation = true;
  }
  for (;;) {
    try { return await send(flags); } catch (e: any) {
      const detail = e?.detail ?? {};
      let flag: string | null = null, question = '';
      if (detail.code === 'real_authorization_required')
        [flag, question] = ['authorize_real_simulation', options.real ? options.authorizeText : realQuestion(detail.report)];
      else if (detail.code === 'confirm_transfer' && options.transfer) [flag, question] = ['confirm_transfer', `${detail.report?.reason}\n\nLoad this model for a NEW task? (Fine-tune makes a new run that starts from this model; the model's own run is not changed.)`];
      else if (detail.code === 'connection_gate_acknowledge') [flag, question] = ['acknowledge_unknown_connection', connectionQuestion(detail.report?.uncertain ?? [])];
      if (!flag || flags[flag]) throw e;                                          // not a question, or already answered
      if (!window.confirm(question)) return null;
      flags[flag] = true;
    }
  }
}

// ---- the budget form's number ------------------------------------------------------------------------------------------------
/** The new total of the budget form (plan: "Whole numbers only; '1,200' reads as 1200"). Digits, or digits in groups of three
 *  (1,200 - also with a space, an underscore or an apostrophe); a separator elsewhere (12,00) is a typo and is said, never
 *  guessed. Empty = the run's own total, unless that is used up. The total has to be more than the evaluations used: one
 *  equal to them would end the run at once. `value` null with no error = unchanged. (Number("1,200") is not a number: the
 *  browser's prompt silently kept the budget then.) */
export function parseTotal(text: string, used: number | null, total: number | null): { value: number | null; error: string | null } {
  const plain = text.trim();
  if (!plain) return used != null && total != null && used >= total
    ? { value: null, error: `All ${total} evaluations are used: type a new total above ${used}.` } : { value: null, error: null };
  const grouped = /^\d{1,3}([,\s_']\d{3})+$/.test(plain);
  if (!/^\d+$/.test(plain) && !grouped) return { value: null, error: /^\d*\.\d+$/.test(plain) ? 'Whole evaluations only: a total has no fractions.'
    : /^[\d,\s_'.]+$/.test(plain) ? 'A separator belongs between groups of three digits: write 1,200 or 1200.'
    : 'Type the new total as a whole number, for example 1200.' };
  const value = Number(plain.replace(/[,\s_']/g, ''));
  if (used != null && value <= used) return { value: null, error: value === used
    ? `${used} evaluations are used already: the new total must be more than that.` : `The total cannot be below the ${used} evaluations already used.` };
  return { value, error: null };
}

/** The question before a run goes on (Resume, Continue...), with the numbers of the budget form: the evaluations the save
 *  point has used, the new total, and how many more that allows. A MOCK run asks nothing. */
export function continueConsent(status: Json, check: Json | null, newTotal: number | null): { real: boolean; authorizeText: string } {
  const real = (status?.mock ?? status?.manifest?.mock) === false;
  const used: number | null = check?.used ?? status?.budget?.charged ?? null;
  const total: number | null = newTotal ?? check?.total ?? status?.budget?.max_evaluations ?? null;
  const left = used != null && total != null ? Math.max(0, total - used) : null;
  return { real, authorizeText: (real ? 'This continues REAL simulations (Virtuoso/Spectre, or ngspice for an ngspice netlist task).\n' : 'This continues the synthetic run.\n')
    + (left === null ? 'Authorize the rest of its evaluation budget?' : `Authorize up to ${left} more candidate evaluation${left === 1 ? '' : 's'}? (${used} of ${total} are used.)`) };
}

// ---- readiness: why each action cannot run now, or null ------------------------------------------------------------------------
const HEADER_BUSY: Record<string, string> = {
  checking: 'The header is still looking up which run is live; a moment.',
  starting: 'The header is starting a run; a moment.',
  resuming: 'The header is continuing a run; a moment.',
  running: 'A run is live in the header: pause it or let it finish first.',
  pausing: 'The header\'s run is pausing; a moment.',
  aborting: 'The header\'s run is ending; a moment.',
  finishing: 'The header\'s run is writing its last files; a moment.',
};

/** Start and Calibration: a new run, from the configuration on this page. One live run at a time on this page; a paused one
 *  is let go of first (the header's second button). The backend's session lock stays the real guard for real simulations. */
export function startReadiness(phase: string, validation: Json): string | null {
  if (phase === 'paused') return 'Not while the header holds a paused run: Let go of it first (the button beside Resume), or Resume it.';
  if (phase !== 'idle') return HEADER_BUSY[phase] ?? 'A run is live in the header.';
  if (validation?.blocks_run) {
    // The levels the header's button counts, and the button by its words (branch record SIF-45: errors alone were counted,
    // so an error and a blocker made this say "1 blocking issue ... lists it" beside a button that said 2).
    const count = (validation.issues ?? []).filter((i: Json) => BLOCKING_LEVELS.includes(i.level)).length;
    return `The configuration has ${count === 1 ? 'a blocking issue' : `${count || 'some'} blocking issues`}: the red "${plural(count, 'blocking issue')}" button in the header lists ${count === 1 ? 'it' : 'them'}.`;
  }
  return null;
}

/** Continue of a run (the Run status tab's Continue..., and the header's Resume, which is Continue with the total
 *  unchanged). `check`: the backend's continuation check of THAT run (null: not asked yet, or an older backend - the
 *  status decides then, as before). `held`: the header holds this run. */
export function continueReadiness({ status, check, phase, held, total }: { status: Json; check: Json | null; phase: string; held: boolean; total: 'unchanged' | 'form' }): string | null {
  if (!status) return 'Reading the run...';
  if (status.worker_alive) return 'This run is running now.';
  const resting = restingFor(status, check, total);
  if (!resting) return status.state === 'completed' ? 'This run has completed.' : `A ${status.state ?? 'new'} run cannot be continued.`;
  // One live run at a time on this page: a continued run becomes the header's run.
  if (phase === 'checking' || phase === 'starting' || phase === 'resuming') return HEADER_BUSY[phase];
  if (!held && phase !== 'idle' && phase !== 'paused')
    return 'Another run is live in the header: pause it or let it finish first (a second live run would have no Pause or Abort on this page).';
  if (check) {
    if (!check.eligible) return check.reason ?? 'The backend says this run cannot be continued.';
    if (total === 'unchanged' && check.exhausted) return `All ${check.total} evaluations are used: raise the total with Continue... under Run status.`;
    return null;
  }
  if (status.save_point === null) return 'This run folder holds no save point - a copy made without them, or they were deleted - so there is nothing to go on from.';
  // the page's own words name the Modes as their buttons do (it said "fine-tune or frozen"; branch record SIF-53); the
  // backend's check, once it answers, gives its own reason, shown as sent
  if (status.save_point_code === 'older') return 'This run was saved by an older version of the optimizer code, and continuing it needs exactly that version. Its model still loads in a new run: Fine-tune or Evaluate only.';
  return null;
}

/** The continuation check of one run at rest (GET /api/runs/continuation), asked again when its status changes: the
 *  reason Continue cannot go on, BEFORE the press, and the numbers of the budget form. Null while unknown, while the run is
 *  live, and with a backend that has no such check. */
export function useContinuation(features: Features, runDir: string | null, status: Json): Json | null {
  const key = runDir && status?.run_dir === runDir && !status.worker_alive
    ? [runDir, status.state, status.heartbeat_utc, status.save_point, status.save_point_code, status.last_checkpoint_utc, status.budget?.max_evaluations].join('|') : null;
  const { value } = useRequest<Json>(signal => api.continuation(runDir!, null, signal), [key], { enabled: features.continuation && !!key });
  return key && value?.run_dir === runDir ? value : null;
}

/** A launch the backend refused: its words stay beside the action until what it depends on changes (`key`). */
export type Refusal = { action: Action; text: string; detail: Json; key: string };

/** The launcher. `onLaunched(started, as, note)`: make the run the header's run and the shown run, and name it. */
export function useLauncher({ control, features, onLaunched, onMessage }: {
  control: RunControl; features: Features; onMessage: (m: Json) => void;
  onLaunched: (started: Json, as: 'start' | 'resume', note?: string) => void }) {
  const [refusal, setRefusal] = useState<Refusal | null>(null);
  const going = useRef(false);
  const latest = useRef({ control, onLaunched, onMessage });
  latest.current = { control, onLaunched, onMessage };
  const mounted = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  /** What became of a launch kept in this tab - after a reload during it, or when its answer did not arrive. Done: the run
   *  it made is taken. On its way: "Starting..." until it is answered (a quarter of an hour at most, the backend's own
   *  limit). Unknown: it never arrived, was refused, or failed before anything was made - nothing to take. The QUESTION
   *  itself unanswered (the backend is restarting): the id stays kept and the question is asked again - for five minutes
   *  here, and again on the next press or reload. A failed question used to count as "unknown", and the run that launch
   *  had made was forgotten (review of 2026-10-07). */
  const askAbout = useCallback((sent: SentLaunch, when: string, tries = 0, failures = 0): void => {
    const as = sent.action === 'start' || sent.action === 'calibration' ? 'start' : 'resume';
    const still = () => mounted.current && sentLaunch()?.id === sent.id;        // not replaced by a newer launch meanwhile
    api.launchRequest(sent.id).then(answer => {
      if (!still()) return;
      if (answer?.state === 'done' && answer.answer?.run_dir) {
        keepLaunch(null);
        setRefusal(null);                                 // the error of the launch itself, if any: its run is here
        latest.current.onLaunched(answer.answer, as, `The ${sent.action === 'calibration' ? 'Calibration' : sent.action} sent ${when} made this run; it was not sent again.`);
      } else if (answer?.state === 'pending' && tries < 600) {
        latest.current.control.setPending(as);
        setTimeout(() => askAbout(sent, when, tries + 1, failures), 1500);
      } else {
        keepLaunch(null);
        latest.current.control.setPending(null);
      }
    }, () => {
      if (!still()) return;
      if (failures < 100) { latest.current.control.setPending(as); setTimeout(() => askAbout(sent, when, tries, failures + 1), 3000); }
      else latest.current.control.setPending(null);
    });
  }, []);

  /** Every launch: one at a time, one pending state, its request id kept until it is answered, the backend's questions,
   *  and the run handed to the header - or the refusal kept with `key`. */
  const go = useCallback(async (action: Action, key: string, runDir: string | null, send: (flags: Json) => Promise<Json>,
    consent: { real: boolean; authorizeText: string; transfer?: boolean }, declined: string, note?: (started: Json) => string | undefined) => {
    if (going.current) return;                                // a second press anywhere finds the first one on its way
    going.current = true;
    setRefusal(null);                                         // a new attempt: the reason of the last one goes until this one is answered
    const { control: header } = latest.current;
    const as = action === 'start' || action === 'calibration' ? 'start' : 'resume';
    header.setPending(as);
    let handed = false, answered = true, asking = false, launch: SentLaunch | null = null;
    try {
      // A launch of this page that got no answer at all is asked about first: it may have arrived and made a run.
      const earlier = features.requests ? sentLaunch() : null;
      if (earlier) {
        let known: Json;
        try { known = await api.launchRequest(earlier.id); } catch (e: any) {
          // The question got no answer (the backend is restarting): that launch may have made a run, so nothing new is sent
          // and its id stays kept for the next press. Taken for "unknown", as it used to be, a second launch went out here.
          answered = false;
          setRefusal({ action, text: `Not sent: what became of an earlier launch of this page could not be checked (${plainError(e)}). Try again in a moment.`, detail: e?.detail ?? null, key });
          return;
        }
        if (known?.state === 'done' && known.answer?.run_dir) {
          keepLaunch(null);
          setRefusal(null);
          handed = true;
          latest.current.onLaunched(known.answer, earlier.action === 'start' || earlier.action === 'calibration' ? 'start' : 'resume',
            'An earlier launch of this page, whose answer had not arrived, made this run; nothing new was sent.');
          return;
        }
        if (known?.state === 'pending') { answered = false; setRefusal({ action, text: 'An earlier launch of this page is still on its way; its run comes in a moment.', detail: null, key }); return; }
      }
      launch = features.requests ? { id: newRequestId(), action, run_dir: runDir, at: Date.now() } : null;
      keepLaunch(launch);
      const started = await launchWithConsent(flags => send(launch ? { ...flags, request_id: launch.id } : flags), consent);
      if (!started) { latest.current.onMessage({ level: 'info', text: declined }); return; }
      setRefusal(null);
      handed = true;
      latest.current.onLaunched(started, as, note?.(started));
    } catch (e: any) {
      // A refusal answers the request in the backend's words: nothing was made (a 4xx). No answer at all - the page is going
      // away (a reload aborts the request), or the backend stopped - or a failure inside the backend (a 5xx) can come AFTER
      // the run was made: the id stays kept, and the page asks what became of it instead of sending it again.
      answered = e instanceof ApiError && e.status < 500;
      setRefusal({ action, text: plainError(e), detail: e?.detail, key });
      if (e?.detail?.code === 'already_running') latest.current.control.refresh();     // continued from elsewhere: show what is true
      if (!answered && launch && sentLaunch()?.id === launch.id) { asking = true; askAbout(launch, 'a moment ago, whose answer did not arrive,'); }
    } finally {
      if (answered) keepLaunch(null);
      going.current = false;
      if (!handed && !asking) latest.current.control.setPending(null);       // while asking, the header keeps "Starting..."
    }
  }, [features.requests, askAbout]);

  /** After a reload during a launch: the page asks what became of it instead of sending it again. Asked once per launch
   *  kept (React's StrictMode mounts the page twice in development: `asked` and `mounted` hold). */
  const asked = useRef<string | null>(null);
  useEffect(() => {
    const sent = features.requests ? sentLaunch() : null;
    if (!sent || asked.current === sent.id) return;
    asked.current = sent.id;
    askAbout(sent, 'before the page was reloaded');
  }, [features.requests, askAbout]);

  return { go, refusal, setRefusal, busy: going };
}

// ---- the page's launches (plan-refactoring C5, out of App.tsx's Page) ---------------------------------------------------------
/** A draft whose Mode is still `resume` (record 7.267; plan "The draft": "An old saved draft with mode: resume"): no Mode is
 *  chosen, and nothing starts until one is. The value stays `resume` in the configuration, which every backend route still
 *  reads (the command line still starts one); the page shows it as no Mode chosen. */
const NO_MODE = 'Choose a Mode in the RL model window first: this configuration still says resume, which is no longer a choice (Continue... in the Runs window continues a run).';
/** Calibration evaluates only random designs. Task creation owns the fixed starting-design baseline. */
export const CALIBRATION_DESIGNS = 64;

/** The page's launcher: Start, Calibration, Continue... of the run shown and Resume of the header's run, the continuation checks
 *  they depend on, why each cannot go now, the refusals kept beside them, the header's "Next" line (`setNextModel`: Run
 *  configuration's part of it) and Fine-tune from a run's newest save point. `launchedRun`: the page's "the run has started".
 *  `taskShown`: the name the header's title gives the registered task (the circuit panel's `onTaskName`). */
export function useLaunchActions({ control, meta, config, setConfig, configKey, validation, runDir, status, circuit, isReal, launchedRun, setMessage, taskShown = null }: {
  control: RunControl; meta: Json; config: Json; setConfig: (next: Json | ((c: Json) => Json), record?: boolean) => void; configKey: string;
  validation: Json; runDir: string | null; status: Json; circuit: Json; isReal: boolean; launchedRun: (started: Json, as: 'start' | 'resume', note?: string) => void;
  setMessage: (message: Json) => void; taskShown?: string | null }) {
  const features = useMemo(() => featuresOf(meta), [meta]);
  const launcher = useLauncher({ control, features, onLaunched: launchedRun, onMessage: setMessage });
  // The backend's continuation check (when it has one): of the run shown, for Continue..., and of the header's paused run,
  // for Resume - the reason either cannot go on is said before the press.
  const shownCheck = useContinuation(features, runDir, status);
  const heldCheck = useContinuation(features, control.dir, control.phase === 'paused' ? control.status : null);
  const startBlocked = startReadiness(control.phase, validation) ?? (config.run.mode === 'resume' ? NO_MODE : null);
  // What Start would start (record 7.269; plan "The draft": "What Start will start is one line beside it ... It is also Start's
  // tooltip, with the reason when Start is disabled"): the task, Run configuration's model and network, the budget. A saved
  // task as the title beside it names it (branch record SIF-71: a renamed task by its new name; it was the key without
  // "real:" for every task, the old name of a renamed one); the key without "real:" until the circuit panel has said. A
  // Virtuoso cell is library/cell (the title names it by the project's task name instead).
  const [nextModel, setNextModel] = useState<NextModel | null>(null);
  const nextTask: string | null = config.circuit?.source === 'registered_task'
    ? (config.circuit.task_id ? (taskShown ?? String(config.circuit.task_id).replace(/^real:/, '')) : null)
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
        authorizeText: (!isReal ? `Start ${budget} synthetic MOCK evaluations?` : circuit?.simulator === 'ngspice' ? `This starts ngspice simulations of the task (no license; every one is counted as a real evaluation).\nRun a budget of ${plural(budget, 'candidate evaluation')}?`
          : `This starts REAL Virtuoso/Spectre simulations.\nAuthorize a budget of ${plural(budget, 'candidate evaluation')}?`) + calibrationText },
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
  return { launcher, shownCheck, startBlocked, setNextModel, nextLine, resumeBlocked, continueBlocked, headerRefusal, shownRefusal, start,
    continueShown, resumeHeld, fineTuneFrom };
}
