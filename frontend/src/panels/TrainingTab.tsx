import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, ApiError, Json, OLDER_BACKEND, plainError, readWithDeadline } from '../api';
import { createdAt as created, runName, runTaskOrBlank as taskOf, timeOfDay as clock, TRAINING_STATE_CLASS as STATE_CLASS } from '../format';
import { si, unitLabel } from '../units';
import { Icon } from './Icons';
import { KeyTile } from './fields';
import { shownLive } from '../runState';
import { TRAINING_CAPS_KEY, TRAINING_COMPARE_KEY } from '../contract';
import { TrainingChart } from './TrainingChart';
import { runMode } from './rlModelText';
import { build, buildCompare, catalog, ChartSpec, COMPARE_MAX, Context, ENDS, keyNumbers, LearnerX, RECENT, setCaps, TrainingStore, View } from './trainingData';
import type { Built } from './trainingData';
import type { Answer } from './trainingData';
import { keep, readKept } from '../kept';

/** The Training tab (record 7.193, user request): live charts of the shown run's RECORDED training numbers - step reward,
 *  the share of designs meeting every hard spec, the specs against their limits, the best design, and the SAC learner's
 *  losses, temperature and entropy - beside Output files. Logs and errors stay in the Logs tab.
 *
 *  Where the numbers come from: GET /api/runs/training (backend training_series.py) reads the run's own tables and the
 *  journal of results not yet published as a part; nothing in the training loop was added for it, nothing is simulated.
 *  The page asks for what is new since its last answer (a cursor of flush records), every 2 s while the run's worker
 *  lives, once when it ends, and never while this tab is hidden: opened again, one answer brings it up to date. Charts
 *  are redrawn at most once a second, and only when something changed.
 *
 *  Several runs on one chart (record 7.200, the user's choice of "what next"): up to three other runs beside the shown one,
 *  each its own colour, read the same way (history once, then every 2 s while its worker lives - the answer says so).
 *
 *  More than two charts (record 7.205, user: "add multiple charts same page support. more than the current 2"): up to
 *  eight, each choosing what it shows in its own title; + adds one, × takes one off.
 *
 *  Learner by evaluation (record 7.213, the user's choice of "what next"): the learner's charts drawn over the evaluations
 *  collected instead of the update count, so runs that learn 1 and 8 times per evaluation line up; units in the chart
 *  titles are written as everywhere on the page (units.ts, record 7.208: English letters).
 *
 *  Key numbers (record 7.215, the user's choice of "what next"): a table of each run's first passing design, its passing
 *  share of the last 100 evaluations, its best design's worst miss and how far its entropy estimate and temperature fell -
 *  read from the recorded rows like the charts, so the runs on the charts can be compared at a glance.
 *
 *  Kept in this browser: the charts chosen, the smoothing, the learner's x, whether the key numbers are open and the
 *  compared runs (like the folded modules); not the zoom. */
const SETTINGS_KEY = 'gator-workbench-training-v1';
const SMOOTHING = [0, 10, 20, 50, 100, 200];
const MAX_CHARTS = 8;
type Settings = { charts: string[]; smoothing: number; learnerX: LearnerX; keys: boolean };
const DEFAULTS: Settings = { charts: ['reward', 'pass'], smoothing: 20, learnerX: 'update', keys: true };
function storedSettings(): Settings {
  return readKept(storage => {
    const s = JSON.parse(storage.getItem(SETTINGS_KEY) ?? 'null');
    // any number of charts since 7.205; before it two, the second possibly null
    const charts = Array.isArray(s?.charts) ? s.charts.filter((c: unknown) => typeof c === 'string').slice(0, MAX_CHARTS) : [];
    return { charts: charts.length ? charts : DEFAULTS.charts, smoothing: SMOOTHING.includes(s?.smoothing) ? s.smoothing : DEFAULTS.smoothing,
      learnerX: s?.learnerX === 'evaluation' ? 'evaluation' : DEFAULTS.learnerX, keys: s?.keys !== false };
  }, () => DEFAULTS);
}
/** How many charts stand side by side: up to three in a row, four as two by two, then rows of three or four. */
const columnsFor = (n: number) => (n <= 3 ? n : n === 4 ? 2 : n <= 6 ? 3 : 4);
const chartName = (id: string) => (id.startsWith('spec:') ? id.slice(5) : id.replace(/_/g, ' '));
keep(s => {      // a browser check of the memory bound sets lower caps for its own page (trainingData.ts setCaps)
  const caps = JSON.parse(s.getItem(TRAINING_CAPS_KEY) ?? 'null');
  if (caps) setCaps(caps);
});                 // blocked storage: the default caps

function storedCompare(): string[] {
  return readKept(s => { const list = JSON.parse(s.getItem(TRAINING_COMPARE_KEY) ?? '[]'); return Array.isArray(list) ? list.filter(d => typeof d === 'string').slice(0, COMPARE_MAX - 1) : []; },
    () => []);
}
const readError = (e: any) => (e instanceof ApiError && (e.status === 405 || (e.status === 404 && e.detail === 'Not Found')) ? OLDER_BACKEND : plainError(e));
/** A run in the Compare list, as the run window names it: when, task, mode and seed, state, evaluations. Worked out once
 *  per row: a row stays the same object until the run list changes (App.tsx keeps an unchanged list, record 7.275). */
const CHOICES = new WeakMap<object, string>();
const runChoice = (r: Json) => {
  let text = CHOICES.get(r);
  if (text === undefined) {
    // As the run shown is named left of Runs... (branch records SIF-6, SIF-11): dots, the Mode in words, "seed 2".
    text = `${created(r.created_utc)} · ${taskOf(r)} · ${runMode(r)}, seed ${r.seed} · ${r.state ?? 'not started'}${r.evaluations != null ? ` · ${r.evaluations} evaluations` : ''}${r.mock ? ' · MOCK' : ''}`;
    CHOICES.set(r, text);
  }
  return text;
};

const POLL_MS = 2000, RETRY_MS = 5000, FRAME_MS = 1000;
const NONE: View = { mode: 'all' };
// a unit that is a quantity gets its SI prefix (si in api.ts); a count, a share or a normalized number is a plain number
const PLAIN = new Set(['', 'share', 'normalized', 'nats']);
const formatFor = (unit: string) => (v: number) => (PLAIN.has(unit) ? String(+v.toPrecision(4)) : si(v, unit));
const plain = (v: number) => String(+v.toPrecision(3));

/** Whether the browser tab itself is in the background: then nothing is read and nothing drawn either. */
function usePageHidden() {
  const [hidden, setHidden] = useState(() => document.visibilityState === 'hidden');
  useEffect(() => {
    const change = () => setHidden(document.visibilityState === 'hidden');
    document.addEventListener('visibilitychange', change);
    return () => document.removeEventListener('visibilitychange', change);
  }, []);
  return hidden;
}

/** What a read loop of the Training tab does besides reading (plan-refactoring C10: the shown run's loop and the compared
 *  runs' loop were one loop with these differences). `before`: at the start of each read. `done`: an answer applied - whether
 *  to read again in POLL_MS. `failed`: a read failed (not cancelled) - how long until it is tried again, or null for never. */
type ReadLoop = { before?: () => void; done: (dir: string, answer: Answer) => boolean; failed: (dir: string, e: any) => number | null };
/** Reads each run's recorded numbers that are new since its last answer - the history in pages, then again while `done`
 *  says so - for as long as the effect stands (`deps`). `runs()` is asked when it starts: the runs to read, or null for none. */
function useTrainingReads(runs: () => { dir: string; store: TrainingStore }[] | null, loop: ReadLoop, requestFrame: () => void, deps: unknown[]) {
  useEffect(() => {
    const list = runs();
    if (!list) return;
    let alive = true;
    const timers: number[] = [], controller = new AbortController();
    for (const { dir, store: run } of list) {
      const read = async () => {
        loop.before?.();
        try {
          const answer: Answer = await readWithDeadline(signal => api.training(dir, run.flushes, signal, run.tailCursor), controller.signal, 60000);
          if (!alive) return;
          if (run.apply(answer)) requestFrame();
          const again = loop.done(dir, answer);
          if (answer.flushes.served < answer.flushes.total || answer.tail_page?.more) { void read(); return; }
          if (again) timers.push(window.setTimeout(read, POLL_MS));
        } catch (e: any) {
          if (!alive || controller.signal.aborted) return;
          const after = loop.failed(dir, e);
          if (after !== null) timers.push(window.setTimeout(read, after));
        }
      };
      void read();
    }
    return () => { alive = false; controller.abort(); timers.forEach(t => window.clearTimeout(t)); };
  }, deps);
}

export function TrainingTab({ hidden, runDir, status, runs }: { hidden: boolean; runDir: string | null; status: Json; runs: Json[] }) {
  const pageHidden = usePageHidden();
  const active = !hidden && !pageHidden && !!runDir;
  const live = shownLive(status, runDir);
  // the charts on the page: a stable key each (so taking one off keeps the others' charts as they are) and what it shows
  const nextKey = useRef(0);
  const [slots, setSlots] = useState<{ key: number; id: string }[]>(() => storedSettings().charts.map(id => ({ key: nextKey.current++, id })));
  const [smoothing, setSmoothing] = useState<number>(() => storedSettings().smoothing);
  const [learnerX, setLearnerX] = useState<LearnerX>(() => storedSettings().learnerX);
  const [keysOpen, setKeysOpen] = useState<boolean>(() => storedSettings().keys);
  useEffect(() => {
    keep(s => s.setItem(SETTINGS_KEY, JSON.stringify({ charts: slots.map(slot => slot.id), smoothing, learnerX, keys: keysOpen })));   // a private window: not remembered
  }, [slots, smoothing, learnerX, keysOpen]);
  const store = useRef<TrainingStore | null>(null);
  const [frame, setFrame] = useState(0);                         // one more each time the charts take the store's rows
  const [reading, setReading] = useState<{ error: string | null; at: number | null; busy: boolean }>({ error: null, at: null, busy: false });
  const [views, setViews] = useState<Record<number, View>>({});           // by chart key; none = the whole run
  const [widths, setWidths] = useState<Record<number, number>>({});
  const [retry, setRetry] = useState(0);

  // Another run: its own store, whole charts, the zoom let go. The previous run's rows are dropped with its store.
  if (runDir && store.current?.runDir !== runDir) store.current = new TrainingStore(runDir);
  if (!runDir && store.current) store.current = null;
  useEffect(() => { setViews({}); setReading({ error: null, at: null, busy: false }); }, [runDir]);

  // ---- drawing: at most once a second, only when something changed, never while hidden (then caught up when shown)
  const activeRef = useRef(active);
  activeRef.current = active;
  const dirty = useRef(false), lastFrame = useRef(0), frameTimer = useRef<number | null>(null);
  const requestFrame = useCallback(() => {
    dirty.current = true;
    if (frameTimer.current != null || !activeRef.current) return;
    frameTimer.current = window.setTimeout(() => {
      frameTimer.current = null;
      if (!activeRef.current || !dirty.current) return;
      dirty.current = false; lastFrame.current = Date.now(); setFrame(f => f + 1);
    }, Math.max(0, lastFrame.current + FRAME_MS - Date.now()));
  }, []);
  useEffect(() => { if (active && dirty.current) requestFrame(); }, [active, requestFrame]);
  useEffect(() => () => { if (frameTimer.current != null) window.clearTimeout(frameTimer.current); }, []);

  // ---- reading: what is new since the last answer; again every 2 s while the run is live; nothing while hidden
  const liveRef = useRef(live);
  liveRef.current = live;
  useTrainingReads(() => { const own = store.current; return active && own ? [{ dir: own.runDir, store: own }] : null; }, {
    before: () => setReading(r => (r.busy ? r : { ...r, busy: true })),
    done: () => { setReading({ error: null, at: Date.now(), busy: false }); return liveRef.current; },
    // a backend started before this tab existed has no such route (FastAPI's own 404 "Not Found"): said as such
    failed: (_dir, e) => { setReading({ error: readError(e), at: Date.now(), busy: false }); return liveRef.current ? RETRY_MS : null; },
  }, requestFrame, [active, runDir, live, retry, requestFrame]);

  // ---- other runs on the same charts (record 7.200): each its own store, read like the shown one, apart from it
  const [compare, setCompare] = useState<string[]>(storedCompare);
  const keepCompare = (next: string[]) => { setCompare(next); keep(s => s.setItem(TRAINING_COMPARE_KEY, JSON.stringify(next))); };   // not remembered without storage
  const others = compare.filter(dir => dir !== runDir).slice(0, COMPARE_MAX - 1);
  const othersKey = others.join('\n');
  const compared = useRef(new Map<string, TrainingStore>());
  for (const dir of others) if (!compared.current.has(dir)) compared.current.set(dir, new TrainingStore(dir));
  for (const dir of [...compared.current.keys()]) if (!others.includes(dir)) compared.current.delete(dir);
  const [comparedState, setComparedState] = useState<Record<string, { error: string | null; live: boolean }>>({});
  useTrainingReads(() => (active && others.length ? others.flatMap(dir => { const run = compared.current.get(dir); return run ? [{ dir, store: run }] : []; }) : null), {
    done: (dir, answer) => {
      const working = !!answer.worker_alive;
      setComparedState(state => ({ ...state, [dir]: { error: null, live: working } }));
      return working;
    },
    failed: (dir, e) => { setComparedState(state => ({ ...state, [dir]: { error: readError(e), live: false } })); return null; },
  }, requestFrame, [active, othersKey, retry, requestFrame]);
  const rowOf = useMemo(() => new Map(runs.map(r => [r.run_dir, r] as [string, Json])), [runs]);
  /** A run's name on a compared chart, as the run window and the Compare list show it: its experiment (the task when the
   *  experiment kept the default name), its seed and when it was made; the start of its folder's id only when two compared
   *  runs would read the same. Record 7.213: four Spectre runs of one task and seed read alike by folder id alone. */
  const labels = useMemo(() => {
    const base = (dir: string) => {
      const row = rowOf.get(dir), experiment = String(row?.experiment ?? '').split('__')[0];
      return row ? `${experiment && !['experiment', 'None'].includes(experiment) ? experiment : taskOf(row)} \u00b7 seed ${row.seed ?? '?'} \u00b7 ${created(row.created_utc)}` : runName(dir);
    };
    const dirs = runDir ? [runDir, ...others] : others, named = dirs.map(base);
    return new Map(dirs.map((dir, i) => [dir, named.indexOf(named[i]) === named.lastIndexOf(named[i]) ? named[i]
      : `${named[i]} \u00b7 ${(runName(dir).split('__').pop() ?? '').slice(0, 6)}`]));
  }, [rowOf, runDir, othersKey]);
  const runLabel = (dir: string) => labels.get(dir) ?? runName(dir);

  const own = store.current;
  // a baseline run that calibrates (record 7.197): its random designs are not training, and nothing learns
  const calibration = !!status?.calibration;
  const context: Context = useMemo(() => ({ calibration }), [calibration]);
  const charts = useMemo(() => (own ? catalog(own, context) : []), [own, frame, context]);
  // the key numbers of every run on the charts, the shown one first (record 7.215); again with each frame
  const keyRows = useMemo(() => (own && runDir ? [{ dir: runDir, store: own, context }, ...others.map(dir => ({ dir, store: compared.current.get(dir), context: {} }))]
    .map(({ dir, store: run, context: known }) => ({ dir, numbers: run && run.answers > 0 ? keyNumbers(run, known) : null })) : []), [own, runDir, frame, othersKey, context]);
  const specOf = (id: string | null) => (id ? charts.find(c => c.id === id) ?? null : null);
  const viewOf = (key: number) => views[key] ?? NONE;
  // Each chart's data, rebuilt only when what it shows changed: new numbers (frame), its choice, its zoom or its width - so a
  // chart whose own things stayed put keeps its data object and is not drawn again. A chart chosen for another run that
  // this one does not have (a spec of another circuit) says so in its place; the choice is kept for the runs that have it.
  const builtCache = useRef(new Map<number, { sig: string; built: Built | null }>());
  const runsSig = useMemo(() => runs.map(r => `${r.run_dir}|${r.task_name}|${r.seed}|${r.experiment}|${r.created_utc}`).join('\n'), [runs]);   // what the labels are made of
  const built = slots.map(slot => {
    const spec = specOf(slot.id), view = viewOf(slot.key), width = widths[slot.key] ?? 600;
    const sig = [frame, runDir, slot.id, !!spec?.available, smoothing, learnerX, JSON.stringify(view), width, calibration, othersKey, runsSig].join('\u0001');
    const hit = builtCache.current.get(slot.key);
    if (hit && hit.sig === sig) return hit.built;
    let made: Built | null = null;
    if (own && runDir && spec?.available) {
      made = !others.length ? build(own, spec.id, smoothing, view, width, context, learnerX)
        : buildCompare([{ store: own, label: runLabel(runDir), context }, ...others.map(dir => ({ store: compared.current.get(dir)!, label: runLabel(dir) }))],
          spec.id, smoothing, view, width, learnerX);
    }
    builtCache.current.set(slot.key, { sig, built: made });
    return made;
  });
  for (const key of [...builtCache.current.keys()]) if (!slots.some(slot => slot.key === key)) builtCache.current.delete(key);

  const setView = (key: number, view: View) => setViews(v => ({ ...v, [key]: view }));
  const choose = (key: number, id: string) => { setSlots(list => list.map(slot => (slot.key === key ? { ...slot, id } : slot))); setView(key, NONE); };
  /** One more chart: the first chart of this run not on the page yet that it can draw. */
  const addChart = () => setSlots(list => {
    if (list.length >= MAX_CHARTS) return list;
    const next = charts.find(c => c.available && !list.some(slot => slot.id === c.id))?.id ?? 'reward';
    return [...list, { key: nextKey.current++, id: next }];
  });
  const removeChart = (key: number) => setSlots(list => (list.length <= 1 ? list : list.filter(slot => slot.key !== key)));
  const shown = slots.filter((_, i) => built[i]);
  const following = shown.every(slot => viewOf(slot.key).mode !== 'fixed');
  const follow = () => setViews(v => Object.fromEntries(slots.map((slot, i) => {
    const view = v[slot.key] ?? NONE;
    if (following) { const range = built[i]?.range; return [slot.key, range ? { mode: 'fixed', min: range[0], max: range[1] } : view]; }   // freeze where it is
    return [slot.key, view.mode === 'fixed' ? { mode: 'follow', width: view.max - view.min } : view];                                     // slide to the newest, same width
  })));
  const reset = () => setViews({});
  /** The learner's x changed: its charts' zoom was in the other unit, so they show the whole run again. */
  const chooseLearnerX = (next: LearnerX) => {
    setLearnerX(next);
    setViews(v => Object.fromEntries(Object.entries(v).filter(([key]) => specOf(slots.find(slot => slot.key === Number(key))?.id ?? null)?.axis !== 'update')));
  };
  const learnerShown = slots.some(slot => specOf(slot.id)?.axis === 'update');

  /** The facts of a recorded row, for the line above a chart. */
  const describe = (axis: 'evaluation' | 'update') => (row: number) => {
    if (!own) return '';
    if (axis === 'update') {
      const t = own.updates, phase = own.words.updatePhase.list[t.cols.phase[row]];
      return `${learnerX === 'evaluation' ? `update ${t.cols.cum[row]}` : `after ${t.cols.collected[row]} evaluations`}${phase ? ` · ${phase} learning` : ''}`;
    }
    const t = own.evaluations, w = own.words, c = t.cols;
    const status = w.status.list[c.status[row]];
    return [w.phase.list[c.phase[row]], `episode ${w.episode.list[c.episode[row]] ?? '?'} step ${c.episodeStep[row]}`,
      Number.isFinite(c.index[row]) && c.index[row] !== c.k[row] ? `completion index ${c.index[row]}` : '',
      status && status !== 'ok' ? `status ${status}` : ''].filter(Boolean).join(' · ');
  };

  if (!runDir || !own) return <div className="training" style={hidden ? { display: 'none' } : undefined}><p className="hint">No run selected.</p></div>;
  const { evaluations, updates } = own.counts();
  const last = own.lastTime();
  const state: string | undefined = status?.state;
  const empty = own.answers > 0 && evaluations === 0 && updates === 0 && !others.length;
  const candidates = runs.filter(r => r.run_dir !== runDir && !others.includes(r.run_dir));
  const unavailable = charts.filter(c => !c.available);
  const counts = own.answers === 0 ? (reading.error ? '' : 'Reading the recorded numbers...')
    : `${evaluations} evaluation${evaluations === 1 ? '' : 's'} · ${updates} learner update${updates === 1 ? '' : 's'}${last ? ` · last metric ${clock(last)}` : ''}`
      + (live ? ' · live' : reading.at ? ` · read ${clock(reading.at / 1000)}` : '');
  return (<div className="training" style={hidden ? { display: 'none' } : undefined}>
    <div className="row training-head">
      {/* what is shown on the left (it shortens with an ellipsis), the controls on the right (they never wrap away) */}
      <span className="training-what">
        <span className="training-run" title={runDir}>{runName(runDir)}</span>
        {state && <span className={`badge ${STATE_CLASS[state] ?? 'state-unknown'}`}>{state}{status?.stop_reason ? ` (${status.stop_reason})` : ''}</span>}
        <span className="hint training-counts" title={counts}>{counts}</span>
      </span>
      <span className="training-controls">
      <button disabled={slots.length >= MAX_CHARTS} onClick={addChart}
        title={`Add chart: one more chart on the page (up to ${MAX_CHARTS}). Each chart chooses what it shows in its title; × there takes it off.`}>
        <Icon name="add" label="Add chart" /></button>
      <label className="inline">Smoothing <select value={smoothing} onChange={e => setSmoothing(Number(e.target.value))}>
        {SMOOTHING.map(n => <option key={n} value={n}>{n ? `mean of last ${n}` : 'off'}</option>)}</select></label>
      <label className="inline" title={'Learner by: the x axis of the learner\'s charts (losses, temperature, entropy). "update": the learner\'s update count. '
        + '"evaluation": the number of evaluations collected when each update ran - the x of the other charts - so runs that learn 1 and 8 times per '
        + 'evaluation line up; the updates after one evaluation share its x, and smoothing averages the updates of the last evaluations.'
        + (learnerShown ? '' : ' No learner chart is on the page now.')}>Learner by <select aria-label="Learner charts by" value={learnerX}
          onChange={e => chooseLearnerX(e.target.value === 'evaluation' ? 'evaluation' : 'update')}>
          <option value="update">update</option><option value="evaluation">evaluation</option></select></label>
      <select aria-label="Compare with another run" className="training-compare" value="" disabled={others.length >= COMPARE_MAX - 1 || !candidates.length}
        onChange={e => { if (e.target.value) keepCompare([...others, e.target.value]); }}
        title={`Compare: draw up to ${COMPARE_MAX - 1} other runs on the same charts, each in its own colour (the list of the run window, Runs...).`}>
        <option value="">Compare...</option>{candidates.map(r => <option key={r.run_dir} value={r.run_dir}>{runChoice(r)}</option>)}</select>
      <button aria-pressed={following} disabled={!shown.length} onClick={follow}
        title={following ? 'Follow latest: on - the charts keep the newest results in view. Press to hold them where they are.' : 'Follow latest: off - you zoomed in, so new results do not move the charts. Press to slide back to the newest results, keeping the zoom width.'}>
        <Icon name="follow" label="Follow latest" /></button>
      <button disabled={!shown.some(slot => viewOf(slot.key).mode !== 'all')} onClick={reset} title="Reset zoom: show the whole run again (a double click on a chart does the same). Drag across a chart to zoom in.">
        <Icon name="zoom-reset" label="Reset zoom" /></button>
      </span>
    </div>
    {others.length > 0 && <div className="training-compared">
      {/* the runs on the charts, each in its colour; × takes one off (record 7.200) */}
      <span className="training-chip key-run0" title={runDir}><span className="swatch" />{runLabel(runDir)} (shown)</span>
      {others.map((dir, i) => <span key={dir} className={`training-chip key-run${i + 1}`} title={dir}><span className="swatch" />{runLabel(dir)}
        {comparedState[dir]?.live ? ' \u00b7 live' : ''}{comparedState[dir]?.error ? <span className="error"> - {comparedState[dir].error}</span> : null}
        <button type="button" className="training-chip-remove" onClick={() => keepCompare(others.filter(d => d !== dir))}
          title={`Remove: take ${runLabel(dir)} off the charts`}><Icon name="close" label={`Remove ${runLabel(dir)}`} /></button></span>)}
    </div>}
    {own.answers > 0 && !empty && <details className="training-keys" open={keysOpen} onToggle={e => setKeysOpen(e.currentTarget.open)}>
      <summary title="Key numbers: what each run on the charts reached, read from its recorded rows (episode starts left out, as on the charts).">Key numbers</summary>
      {/* One run: its numbers as tiles (record 7.360, user: "make it more compact but keeping the style"); several: one row each. */}
      {keyRows.length === 1 && keyRows[0].numbers ? ((k: NonNullable<(typeof keyRows)[number]['numbers']>) => <div className="key-tiles training-key-tiles">
        <KeyTile label="Evaluations" value={k.evaluations} title="Evaluations recorded so far." />
        <KeyTile label="First passing design" value={k.firstPass ?? 'none yet'} before={k.firstPass != null ? 'evaluation' : undefined}
          title="The evaluation number of the first design that met every hard spec." />
        <KeyTile label={`Passing, last ${RECENT}`} value={!k.recent ? '-' : k.recent.judged ? `${k.recent.passed} of ${k.recent.judged}` : 'no verdict'}
          after={k.recent?.judged ? `${Math.round((100 * k.recent.passed) / k.recent.judged)} %` : undefined}
          title={`Of the designs of the last ${RECENT} evaluations with a verdict (a timeout or a lost link is none), how many met every hard spec.${k.recent ? ` Evaluations ${k.recent.from} to ${k.recent.to}.` : ''}`} />
        <KeyTile label="Best design's worst miss" value={k.bestMiss != null ? plain(k.bestMiss) : '-'}
          title="The worst-spec miss of the design the run keeps as its best, at the newest evaluation: 0 = it has a design that meets every hard spec." />
        <KeyTile label={'Entropy estimate, first \u2192 last'} value={k.entropy ? `${plain(k.entropy[0])} \u2192 ${plain(k.entropy[1])}` : '-'}
          title={`The policy's entropy estimate (-mean_log_prob): the mean of the learner updates of the first ${ENDS} evaluations it learned at, then of the last ${ENDS}. Fallen far = the policy has settled; level = it still explores.`} />
        <KeyTile label={'Temperature \u03b1, first \u2192 last'} value={k.alpha ? `${plain(k.alpha[0])} \u2192 ${plain(k.alpha[1])}` : '-'}
          title={`The temperature \u03b1 the same way: the mean of the first ${ENDS} evaluations it learned at, then of the last ${ENDS}.`} />
      </div>)(keyRows[0].numbers!) : <table className="grid training-keys-table"><thead><tr><th>Run</th><th title="Evaluations recorded so far.">Evaluations</th>
        <th title="The evaluation number of the first design that met every hard spec.">First passing design</th>
        <th title={`Of the designs of the last ${RECENT} evaluations with a verdict (a timeout or a lost link is none), how many met every hard spec.`}>Passing, last {RECENT}</th>
        <th title="The worst-spec miss of the design the run keeps as its best, at the newest evaluation: 0 = it has a design that meets every hard spec.">Best design's worst miss</th>
        <th title={`The policy's entropy estimate (-mean_log_prob): the mean of the learner updates of the first ${ENDS} evaluations it learned at, then of the last ${ENDS}. Fallen far = the policy has settled; level = it still explores.`}>Entropy estimate</th>
        <th title={`The temperature α the same way: the mean of the first ${ENDS} evaluations it learned at, then of the last ${ENDS}.`}>Temperature α</th></tr></thead>
        <tbody>{keyRows.map(({ dir, numbers: k }, i) => <tr key={dir}>
          <td title={dir}>{others.length ? <span className={`training-chip key-run${i}`}><span className="swatch" />{runLabel(dir)}</span> : runLabel(dir)}</td>
          {!k ? <td colSpan={6} className="hint">Reading...</td> : <>
            <td>{k.evaluations}</td>
            <td>{k.firstPass != null ? `evaluation ${k.firstPass}` : 'none yet'}</td>
            <td title={k.recent ? `evaluations ${k.recent.from} to ${k.recent.to}` : undefined}>{!k.recent ? '-' : k.recent.judged ? `${k.recent.passed} of ${k.recent.judged} (${Math.round((100 * k.recent.passed) / k.recent.judged)} %)` : 'no verdict'}</td>
            <td>{k.bestMiss != null ? plain(k.bestMiss) : '-'}</td>
            <td>{k.entropy ? `${plain(k.entropy[0])} \u2192 ${plain(k.entropy[1])}` : '-'}</td>
            <td>{k.alpha ? `${plain(k.alpha[0])} \u2192 ${plain(k.alpha[1])}` : '-'}</td></>}
        </tr>)}</tbody></table>}
    </details>}
    {state === 'failed' && status?.error && <p className="error training-note">The run failed: {status.error}</p>}
    {reading.error && <p className="error training-note">The training numbers could not be read: {reading.error} <button onClick={() => setRetry(n => n + 1)}>Retry read</button></p>}
    {!own.tailComplete && <p className="hint training-note">The run's journal was being rewritten at a save point; its newest results come with the next read.</p>}
    {unavailable.length > 0 && <details className="training-note"><summary>Not in this run: {unavailable.map(c => c.title).join(', ')}</summary>
      <ul>{unavailable.map(c => <li key={c.id}><b>{c.title}</b>: {c.reason}</li>)}</ul></details>}
    {(own.thinnedEvaluations > 0 || own.thinnedUpdates > 0) && <p className="hint training-note">The oldest part of this long run is shown thinned to its extremes (shaded): every point drawn is a recorded one, some in between are left out on screen only. The run's tables keep every row.</p>}
    {empty ? <p className="hint">{live ? 'Waiting for metrics: the charts start with the run\'s first recorded result.' : 'This run recorded no evaluations and no learner updates.'}</p>
      : own.answers === 0 ? <p className="hint">{reading.error ? '' : 'Reading the run\'s recorded training numbers...'}</p>
      : <div className="training-charts" style={{ gridTemplateColumns: `repeat(${columnsFor(slots.length)}, minmax(0, 1fr))` }}>
        {slots.map((slot, i) => {
          const spec = specOf(slot.id), made = built[i];
          return <figure key={slot.key} className="training-chart">
            {/* what this chart shows is chosen in its title; × takes the chart off the page (one always stays) */}
            <figcaption>
              <select aria-label={`Chart ${i + 1}`} className="training-chart-choice" value={slot.id} onChange={e => choose(slot.key, e.target.value)}
                title={spec ? `${spec.about} Recorded as ${spec.source}.` : 'This run has no such chart.'}>
                {!spec && <option value={slot.id} disabled>{chartName(slot.id)} - not in this run</option>}{options(charts)}</select>
              <span className="spacer" />
              <button type="button" className="training-chart-remove" disabled={slots.length <= 1} onClick={() => removeChart(slot.key)}
                title="Remove chart: take this chart off the page"><Icon name="close" label={`Remove chart ${i + 1}`} /></button>
            </figcaption>
            {!spec ? <p className="hint training-empty">{own.answers > 0 ? `This run has no ${chartName(slot.id)} chart (a spec of another task?). Choose another in the title.` : 'Reading...'}</p>
              : !spec.available ? <p className="hint training-empty">{spec.reason}</p>
              : <>{made?.missing?.length ? <p className="hint training-missing">Not on this chart: {made.missing.map(m => `${m.label} (${m.reason})`).join('; ')}</p> : null}
                <TrainingChart built={made} hidden={!active} xLabel={spec.axis === 'update' && learnerX === 'update' ? 'Learner update' : 'Evaluation'}
                  format={formatFor(spec.unit)} describe={describe(spec.axis)}
                  onWidth={width => setWidths(w => (Math.abs((w[slot.key] ?? 600) - width) < 8 ? w : { ...w, [slot.key]: width }))}
                  onZoom={(min, max) => setView(slot.key, { mode: 'fixed', min, max })} onReset={() => setView(slot.key, NONE)} /></>}
          </figure>;
        })}
      </div>}
  </div>);
}

/** The chart choices, grouped; one the run cannot draw stays choosable and says why in its place. */
function options(charts: ChartSpec[]) {
  const groups: ChartSpec['group'][] = ['Results', 'Specs', 'Learner (SAC)', 'Not recorded'];
  return groups.map(group => {
    const list = charts.filter(c => c.group === group);
    return list.length ? <optgroup key={group} label={group}>{list.map(c => <option key={c.id} value={c.id} title={c.available ? c.about : c.reason ?? ''}>
      {c.title}{c.unit && !['', 'share'].includes(c.unit) ? ` (${unitLabel(c.unit)})` : ''}{c.available ? '' : ' - not recorded'}</option>)}</optgroup> : null;
  });
}
