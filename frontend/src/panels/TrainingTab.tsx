import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api, ApiError, Json, OLDER_BACKEND, plainError, readWithDeadline, si } from '../api';
import { useLook } from '../theme';
import { Icon } from './Icons';
import { LIVE_STATES } from './RunControl';
import { TrainingChart } from './TrainingChart';
import { build, buildCompare, catalog, ChartSpec, COMPARE_MAX, CompareRun, Context, setCaps, TrainingStore, View } from './trainingData';
import type { Answer } from './trainingData';

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
 *  Kept in this browser: the two charts chosen, the smoothing and the compared runs (like the folded modules); not the zoom. */
const SETTINGS_KEY = 'gator-workbench-training-v1';
const SMOOTHING = [0, 10, 20, 50, 100, 200];
type Settings = { charts: [string, string | null]; smoothing: number };
const DEFAULTS: Settings = { charts: ['reward', 'pass'], smoothing: 20 };
function storedSettings(): Settings {
  try {
    const s = JSON.parse(localStorage.getItem(SETTINGS_KEY) ?? 'null');
    if (!s || typeof s.charts?.[0] !== 'string') return DEFAULTS;
    return { charts: [s.charts[0], typeof s.charts[1] === 'string' ? s.charts[1] : null], smoothing: SMOOTHING.includes(s.smoothing) ? s.smoothing : DEFAULTS.smoothing };
  } catch { return DEFAULTS; }
}
try {      // a browser check of the memory bound sets lower caps for its own page (trainingData.ts setCaps)
  const caps = JSON.parse(localStorage.getItem('gator-workbench-training-caps-v1') ?? 'null');
  if (caps) setCaps(caps);
} catch { /* blocked storage: the default caps */ }

const COMPARE_KEY = 'gator-workbench-training-compare-v1';
function storedCompare(): string[] {
  try { const list = JSON.parse(localStorage.getItem(COMPARE_KEY) ?? '[]'); return Array.isArray(list) ? list.filter(d => typeof d === 'string').slice(0, COMPARE_MAX - 1) : []; }
  catch { return []; }
}
const readError = (e: any) => (e instanceof ApiError && (e.status === 405 || (e.status === 404 && e.detail === 'Not Found')) ? OLDER_BACKEND : plainError(e));
const taskOf = (r: Json) => r?.task_name ?? String(r?.task_id ?? '').split(':')[0];
const created = (utc?: string | null) => (utc ? new Date(utc).toLocaleString([], { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) : 'unknown time');
/** A run in the Compare list, as the run window names it: when, task, mode and seed, state, evaluations. */
const runChoice = (r: Json) => `${created(r.created_utc)} | ${taskOf(r)} | ${r.mode} seed${r.seed} | ${r.state ?? 'not started'}${r.evaluations != null ? ` | ${r.evaluations} eval.` : ''}${r.mock ? ' [MOCK]' : ''}`;

const POLL_MS = 2000, RETRY_MS = 5000, FRAME_MS = 1000;
const NONE: View = { mode: 'all' };
const runName = (runDir: string) => runDir.split(/[\\/]/).filter(Boolean).pop() ?? 'run';
const clock = (seconds: number) => new Date(seconds * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
// a unit that is a quantity gets its SI prefix (si in api.ts); a count, a share or a normalized number is a plain number
const PLAIN = new Set(['', 'share', 'normalized', 'nats']);
const formatFor = (unit: string) => (v: number) => (PLAIN.has(unit) ? String(+v.toPrecision(4)) : si(v, unit));
const STATE_CLASS: Record<string, string> = { completed: 'state-ok', failed: 'state-failed', cancelled: 'state-failed', interrupted: 'state-failed',
  running: 'state-busy', starting: 'state-busy', pausing: 'state-busy', stopping: 'state-busy' };

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

export function TrainingTab({ hidden, runDir, status, runs }: { hidden: boolean; runDir: string | null; status: Json; runs: Json[] }) {
  const look = useLook();
  const pageHidden = usePageHidden();
  const active = !hidden && !pageHidden && !!runDir;
  const live = !!status && status.run_dir === runDir && (!!status.worker_alive || LIVE_STATES.includes(status.state));
  const [settings, setSettings] = useState<Settings>(storedSettings);
  const keep = (next: Settings) => { setSettings(next); try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(next)); } catch { /* a private window: not remembered */ } };
  const store = useRef<TrainingStore | null>(null);
  const [frame, setFrame] = useState(0);                         // one more each time the charts take the store's rows
  const [reading, setReading] = useState<{ error: string | null; at: number | null; busy: boolean }>({ error: null, at: null, busy: false });
  const [views, setViews] = useState<[View, View]>([NONE, NONE]);
  const [widths, setWidths] = useState<[number, number]>([600, 600]);
  const [retry, setRetry] = useState(0);

  // Another run: its own store, whole charts, the zoom let go. The previous run's rows are dropped with its store.
  if (runDir && store.current?.runDir !== runDir) store.current = new TrainingStore(runDir);
  if (!runDir && store.current) store.current = null;
  useEffect(() => { setViews([NONE, NONE]); setReading({ error: null, at: null, busy: false }); }, [runDir]);

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
  useEffect(() => {
    const own = store.current;
    if (!active || !own) return;
    let alive = true, timer: number | undefined;
    const controller = new AbortController();
    const read = async () => {
      setReading(r => (r.busy ? r : { ...r, busy: true }));
      try {
        const answer: Answer = await readWithDeadline(signal => api.training(own.runDir, own.flushes, signal, own.tailCursor), controller.signal, 60000);
        if (!alive) return;
        if (own.apply(answer)) requestFrame();
        setReading({ error: null, at: Date.now(), busy: false });
        if (answer.flushes.served < answer.flushes.total || answer.tail_page?.more) { void read(); return; }
        if (liveRef.current) timer = window.setTimeout(read, POLL_MS);
      } catch (e: any) {
        if (!alive || controller.signal.aborted) return;
        // a backend started before this tab existed has no such route (FastAPI's own 404 "Not Found"): said as such
        setReading({ error: readError(e), at: Date.now(), busy: false });
        if (liveRef.current) timer = window.setTimeout(read, RETRY_MS);
      }
    };
    void read();
    return () => { alive = false; controller.abort(); if (timer !== undefined) window.clearTimeout(timer); };
  }, [active, runDir, live, retry, requestFrame]);

  // ---- other runs on the same charts (record 7.200): each its own store, read like the shown one, apart from it
  const [compare, setCompare] = useState<string[]>(storedCompare);
  const keepCompare = (next: string[]) => { setCompare(next); try { localStorage.setItem(COMPARE_KEY, JSON.stringify(next)); } catch { /* not remembered */ } };
  const others = compare.filter(dir => dir !== runDir).slice(0, COMPARE_MAX - 1);
  const othersKey = others.join('\n');
  const compared = useRef(new Map<string, TrainingStore>());
  for (const dir of others) if (!compared.current.has(dir)) compared.current.set(dir, new TrainingStore(dir));
  for (const dir of [...compared.current.keys()]) if (!others.includes(dir)) compared.current.delete(dir);
  const [comparedState, setComparedState] = useState<Record<string, { error: string | null; live: boolean }>>({});
  useEffect(() => {
    if (!active || !others.length) return;
    let alive = true;
    const timers: number[] = [], controller = new AbortController();
    for (const dir of others) {
      const run = compared.current.get(dir);
      if (!run) continue;
      const read = async () => {
        try {
          const answer: Answer = await readWithDeadline(signal => api.training(dir, run.flushes, signal, run.tailCursor), controller.signal, 60000);
          if (!alive) return;
          if (run.apply(answer)) requestFrame();
          const working = !!answer.worker_alive;
          setComparedState(state => ({ ...state, [dir]: { error: null, live: working } }));
          if (answer.flushes.served < answer.flushes.total || answer.tail_page?.more) { void read(); return; }
          if (working) timers.push(window.setTimeout(read, POLL_MS));
        } catch (e: any) {
          if (!alive || controller.signal.aborted) return;
          setComparedState(state => ({ ...state, [dir]: { error: readError(e), live: false } }));
        }
      };
      void read();
    }
    return () => { alive = false; controller.abort(); timers.forEach(t => window.clearTimeout(t)); };
  }, [active, othersKey, retry, requestFrame]);
  const rowOf = useMemo(() => new Map(runs.map(r => [r.run_dir, r] as [string, Json])), [runs]);
  /** A run's name on a compared chart: task, seed and the start of its folder's id (two runs of one task and seed differ there). */
  const runLabel = (dir: string) => {
    const row = rowOf.get(dir), id = (runName(dir).split('__').pop() ?? '').slice(0, 6);
    return row ? `${taskOf(row)} \u00b7 seed ${row.seed ?? '?'} \u00b7 ${id}` : runName(dir);
  };

  const own = store.current;
  // a baseline run that calibrates (record 7.197): its random designs are not training, and nothing learns
  const calibration = !!status?.calibration;
  const context: Context = useMemo(() => ({ calibration }), [calibration]);
  const charts = useMemo(() => (own ? catalog(own, context) : []), [own, frame, context]);
  const specOf = (id: string | null) => (id ? charts.find(c => c.id === id) ?? null : null);
  // A chart chosen for another run that this one does not have (a spec of another circuit): the step reward, or no second
  // chart, for this run - the choice itself is kept for the runs that have it.
  const ids: [string, string | null] = own && own.answers > 0
    ? [specOf(settings.charts[0]) ? settings.charts[0] : 'reward', specOf(settings.charts[1]) ? settings.charts[1] : null] : settings.charts;
  const slots = ids.map(specOf) as [ChartSpec | null, ChartSpec | null];
  const builtFor = (slot: 0 | 1) => {
    const spec = slots[slot];
    if (!own || !runDir || !spec?.available) return null;
    if (!others.length) return build(own, spec.id, settings.smoothing, views[slot], widths[slot], context);
    const runsOn: CompareRun[] = [{ store: own, label: runLabel(runDir), context },
      ...others.map(dir => ({ store: compared.current.get(dir)!, label: runLabel(dir) }))];
    return buildCompare(runsOn, spec.id, settings.smoothing, views[slot], widths[slot]);
  };
  const built0 = useMemo(() => builtFor(0), [own, frame, slots[0]?.id, slots[0]?.available, settings.smoothing, views[0], widths[0], context, othersKey, rowOf]);
  const built1 = useMemo(() => builtFor(1), [own, frame, slots[1]?.id, slots[1]?.available, settings.smoothing, views[1], widths[1], context, othersKey, rowOf]);
  const built = [built0, built1];

  const setView = (slot: 0 | 1, view: View) => setViews(v => (slot === 0 ? [view, v[1]] : [v[0], view]));
  const choose = (slot: 0 | 1, id: string | null) => { keep({ ...settings, charts: slot === 0 ? [id ?? 'reward', ids[1]] : [ids[0], id] }); setView(slot, NONE); };
  const shown = ([0, 1] as const).filter(slot => built[slot]);
  const following = shown.every(slot => views[slot].mode !== 'fixed');
  const follow = () => setViews(v => v.map((view, slot) => {
    if (following) { const range = built[slot]?.range; return range ? { mode: 'fixed', min: range[0], max: range[1] } : view; }     // freeze where it is
    return view.mode === 'fixed' ? { mode: 'follow', width: view.max - view.min } : view;                                            // slide to the newest, same width
  }) as [View, View]);
  const reset = () => setViews([NONE, NONE]);

  /** The facts of a recorded row, for the line above a chart. */
  const describe = (axis: 'evaluation' | 'update') => (row: number) => {
    if (!own) return '';
    if (axis === 'update') {
      const t = own.updates, phase = own.words.updatePhase.list[t.cols.phase[row]];
      return `after ${t.cols.collected[row]} evaluations${phase ? ` · ${phase} learning` : ''}`;
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
      <label className="inline">Charts <select value={ids[0]} onChange={e => choose(0, e.target.value)}>{options(charts)}</select></label>
      <select aria-label="Second chart" value={ids[1] ?? ''} onChange={e => choose(1, e.target.value || null)}><option value="">(one chart)</option>{options(charts)}</select>
      <label className="inline">Smoothing <select value={settings.smoothing} onChange={e => keep({ ...settings, smoothing: Number(e.target.value) })}>
        {SMOOTHING.map(n => <option key={n} value={n}>{n ? `mean of last ${n}` : 'off'}</option>)}</select></label>
      <select aria-label="Compare with another run" className="training-compare" value="" disabled={others.length >= COMPARE_MAX - 1 || !candidates.length}
        onChange={e => { if (e.target.value) keepCompare([...others, e.target.value]); }}
        title={`Compare: draw up to ${COMPARE_MAX - 1} other runs on the same charts, each in its own colour (the list of the run window, Runs...).`}>
        <option value="">Compare...</option>{candidates.map(r => <option key={r.run_dir} value={r.run_dir}>{runChoice(r)}</option>)}</select>
      <button aria-pressed={following} disabled={!shown.length} onClick={follow}
        title={following ? 'Follow latest: on - the charts keep the newest results in view. Press to hold them where they are.' : 'Follow latest: off - you zoomed in, so new results do not move the charts. Press to slide back to the newest results, keeping the zoom width.'}>
        <Icon name="follow" label="Follow latest" /></button>
      <button disabled={!shown.some(slot => views[slot].mode !== 'all')} onClick={reset} title="Reset zoom: show the whole run again (a double click on a chart does the same). Drag across a chart to zoom in.">
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
    {state === 'failed' && status?.error && <p className="error training-note">The run failed: {status.error}</p>}
    {reading.error && <p className="error training-note">The training numbers could not be read: {reading.error} <button onClick={() => setRetry(n => n + 1)}>Retry read</button></p>}
    {!own.tailComplete && <p className="hint training-note">The run's journal was being rewritten at a save point; its newest results come with the next read.</p>}
    {unavailable.length > 0 && <details className="training-note"><summary>Not in this run: {unavailable.map(c => c.title).join(', ')}</summary>
      <ul>{unavailable.map(c => <li key={c.id}><b>{c.title}</b>: {c.reason}</li>)}</ul></details>}
    {(own.thinnedEvaluations > 0 || own.thinnedUpdates > 0) && <p className="hint training-note">The oldest part of this long run is shown thinned to its extremes (shaded): every point drawn is a recorded one, some in between are left out on screen only. The run's tables keep every row.</p>}
    {empty ? <p className="hint">{live ? 'Waiting for metrics: the charts start with the run\'s first recorded result.' : 'This run recorded no evaluations and no learner updates.'}</p>
      : own.answers === 0 ? <p className="hint">{reading.error ? '' : 'Reading the run\'s recorded training numbers...'}</p>
      : <div className={`training-charts${slots[1] ? ' two' : ''}`}>
        {([0, 1] as const).filter(slot => slots[slot] || slot === 0).map(slot => {
          const spec = slots[slot];
          return <figure key={slot} className="training-chart">
            <figcaption title={spec ? `${spec.about} Recorded as ${spec.source}.` : undefined}>
              <b>{spec?.title ?? 'Chart'}</b>{spec?.unit && !['', 'share'].includes(spec.unit) ? <span className="hint"> ({spec.unit})</span> : null}</figcaption>
            {!spec ? <p className="hint">This chart is not offered for this run.</p>
              : !spec.available ? <p className="hint training-empty">{spec.reason}</p>
              : <>{built[slot]?.missing?.length ? <p className="hint training-missing">Not on this chart: {built[slot]!.missing!.map(m => `${m.label} (${m.reason})`).join('; ')}</p> : null}
                <TrainingChart built={built[slot]} hidden={!active} look={look} xLabel={spec.axis === 'update' ? 'Learner update' : 'Evaluation'}
                  format={formatFor(spec.unit)} describe={describe(spec.axis)}
                  onWidth={width => setWidths(w => (Math.abs(w[slot] - width) < 8 ? w : (slot === 0 ? [width, w[1]] : [w[0], width])))}
                  onZoom={(min, max) => setView(slot, { mode: 'fixed', min, max })} onReset={() => setView(slot, NONE)} /></>}
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
      {c.title}{c.unit && !['', 'share'].includes(c.unit) ? ` (${c.unit})` : ''}{c.available ? '' : ' - not recorded'}</option>)}</optgroup> : null;
  });
}
