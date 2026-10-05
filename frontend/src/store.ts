import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { readWithDeadline, type Json } from './api';

export const STORAGE_KEY = 'gator-workbench-config-v1';
/** Which saved revision of which task the editors' rows came from (record 7.203): noted when a task's rows are loaded
 *  (choosing it, Reload saved values) and after each Save task - for this tab, and for the next load of the page. Save
 *  task and the check send it, so rows older than the saved task are not saved over it unasked. */
const ROWS_FROM_KEY = 'gator-workbench-rows-from-v1';
let rowsFromHere: Json = (() => { try { return JSON.parse(localStorage.getItem(ROWS_FROM_KEY) ?? 'null'); } catch { return null; } })();
export const rowsFrom = (task: string | null | undefined): number | null =>
  !!task && rowsFromHere?.task === task && Number.isInteger(rowsFromHere?.revision) ? rowsFromHere.revision : null;
export const noteRowsFrom = (task: string, revision: unknown) => {
  if (!Number.isInteger(revision)) return;
  rowsFromHere = { task, revision };
  try { localStorage.setItem(ROWS_FROM_KEY, JSON.stringify(rowsFromHere)); } catch { /* no storage: this tab still knows */ }
};
const HISTORY_LIMIT = 100;

/** The reward a new configuration starts with, and the one the run panel describes in a sentence (record 7.183, compared
 *  in training on 2026-10-05): minus half the average miss and half the worst miss; a passing design earns up to +1 for the
 *  room on its tightest row and up to +1 for the objective row. The schema's own defaults stay the old arithmetic (capped,
 *  share 0, no bonus), which is what a configuration saved without these fields meant. */
export const SIMPLE_REWARD: Json = { violation_shape: 'compressed', worst_spec_share: 0.5, objective_weight: 1, objective_shape: 'compressed', margin_weight: 1 };

const emptyConfig = (): Json => ({
  schema_version: 'gator-workbench-config-v1',
  project: { name: 'gator-project', task_name: 'task', notes: '' },
  // No task until one is chosen: the MOCK task that used to open here was deleted on 2026-09-30 (record 7.128).
  circuit: { source: 'registered_task', task_id: null, circuit_class: 'unspecified', pdk_id: 'unspecified' },
  parameters: [], targets: [], measurements: [],
  run: { mode: 'scratch', max_evaluations: 60, concurrency: 1, seed: 0, reward: { ...SIMPLE_REWARD } },
  output: { experiment_name: 'experiment' },
  research: {},
});

/** A Specs row saved before specs had equations named ONE probe in `measurement_id`: that probe is its equation (the
 *  simplest one). The key keeps its place, so the row still equals the same row served by the backend now (rows are
 *  compared as JSON text), and an `equation` given as well wins - the backend reads old rows the same way. */
export function migrateConfig(config: Json): Json {
  if (!config || typeof config !== 'object') return config;
  let out = config;
  if (Array.isArray(config.targets)) {
    const targets = config.targets.map((row: Json) => row && typeof row === 'object' && 'measurement_id' in row
      ? Object.fromEntries(Object.entries(row).filter(([key]) => !(key === 'measurement_id' && 'equation' in row))
          .map(([key, value]) => [key === 'measurement_id' ? 'equation' : key, value]))
      : row);
    out = { ...out, targets };
  }
  if (Array.isArray(config.parameters)) out = { ...out, parameters: config.parameters.map(migrateParameter) };
  out = withoutExpressionProbes(out);
  if (Array.isArray(out.targets)) out = { ...out, targets: out.targets.map(migrateTarget) };
  if (Array.isArray(out.measurements)) out = { ...out, measurements: out.measurements.map((row: Json) => without(row, RETIRED_MEASUREMENT_KEYS)) };
  // "Threads per job" retired on 2026-09-29: no simulator ever used it. The backend drops it too and hashes it at 1.
  if (config.run && typeof config.run === 'object' && 'threads_per_job' in config.run) out = { ...out, run: without(config.run, ['threads_per_job']) };
  // "Experiment group" and "Test tasks" retired on 2026-10-03 (record 7.163): nothing read them. The backend drops them too.
  if (config.research && typeof config.research === 'object' && ('experiment_group' in config.research || 'test_tasks' in config.research))
    out = { ...out, research: without(config.research, ['experiment_group', 'test_tasks']) };
  return out;
}

/** Columns retired on 2026-09-26 (record 7.92), and the Probes' conditions and aggregation on 2026-09-29 (record 7.105).
 *  The backend drops them the same way when it reads a row, so a row here
 *  equals the row it serves back; what they meant is kept in the columns that remain (an expression relation as the
 *  ratio, a discrete candidate grid as lower/upper/step), and a value that cannot be kept goes into the notes. */
const RETIRED_PARAMETER_KEYS = ['name', 'target_kind', 'candidates', 'relation', 'expression'];
const RETIRED_MEASUREMENT_KEYS = ['function', 'window', 'at_frequency_hz', 'integration_band_hz', 'branch_direction', 'loop_definition', 'crossover', 'on_failure', 'validity',
  'conditions', 'aggregation', 'expression'];

/** Retired on 2026-10-03, as the backend does (schema.WorkbenchConfig._expression_probes, PerformanceTarget._retired_fields):
 *  a probe computed from other probes goes into the equations of the specs that use it, in parentheses; a spec's
 *  "target ± tolerance" becomes the interval it was, and a tolerance on another spec the limits it loosened (an empty scale
 *  gets the size it had). What never ran (a cycle of probes, a target without a positive tolerance) stays as it is, for
 *  the backend to refuse in plain words. */
const namePattern = (name: string) => new RegExp(`(?<![A-Za-z0-9_.])${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![A-Za-z0-9_])`, 'g');
function withoutExpressionProbes(config: Json): Json {
  const probes: Json[] = Array.isArray(config.measurements) ? config.measurements : [];
  const computed = new Map<string, string>(probes.filter(m => m?.result_source === 'expression').map(m => [String(m.measurement_id), String(m.expression ?? '')]));
  if (!computed.size) return config;
  const written = (text: string, seen: string[] = []): string | null => {
    let out: string | null = text;
    for (const [name, expression] of computed) {
      if (out === null || !namePattern(name).test(out)) continue;
      if (seen.includes(name)) return null;
      const inner = written(expression, [...seen, name]);
      out = inner === null ? null : out.replace(namePattern(name), `(${inner})`);
    }
    return out;
  };
  const targets = (config.targets ?? []).map((t: Json) => typeof t?.equation === 'string' ? { t, equation: written(t.equation) } : { t, equation: t?.equation });
  if (targets.some((x: Json) => x.equation === null)) return config;                 // a cycle: the backend says so
  return { ...config, targets: targets.map((x: Json) => typeof x.t?.equation === 'string' ? { ...x.t, equation: x.equation } : x.t),
    measurements: probes.filter(m => m?.result_source !== 'expression') };
}
function migrateTarget(row: Json): Json {
  if (!row || typeof row !== 'object' || !('target' in row || 'tolerance' in row || row.constraint === 'target')) return row;
  const number = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
  const tolerance = row.tolerance ?? 0, size = Math.max(...[row.lower, row.upper, row.target].filter(number).map(Math.abs), 0) || 1;
  if (!number(tolerance) || tolerance < 0) return row;
  let out = without(row, ['target', 'tolerance']);
  if (row.constraint === 'target') {
    if (!number(row.target) || tolerance <= 0 || row.lower != null || row.upper != null) return row;
    out = { ...out, constraint: 'interval', lower: row.target - tolerance, upper: row.target + tolerance };
  } else if (tolerance) {
    out = { ...out, ...(number(row.lower) ? { lower: row.lower - tolerance } : {}), ...(number(row.upper) ? { upper: row.upper + tolerance } : {}) };
  } else return out;
  return out.normalization_scale == null ? { ...out, normalization_scale: size } : out;
}

function without(row: Json, keys: string[]): Json {
  if (!row || typeof row !== 'object' || !keys.some(key => key in row)) return row;
  return Object.fromEntries(Object.entries(row).filter(([key]) => !keys.includes(key)));
}

/** (lower, upper, step) when the values are a uniform grid, else null - the backend's rule (schema.uniform_grid). */
function uniformGrid(values: unknown): [number, number, number] | null {
  if (!Array.isArray(values) || values.some(v => typeof v !== 'number' || !Number.isFinite(v))) return null;
  const sorted = [...new Set(values as number[])].sort((a, b) => a - b);
  if (sorted.length < 2 || sorted.length !== values.length) return null;
  const step = sorted[1] - sorted[0];
  if (step <= 0 || sorted.some((v, i) => i > 0 && Math.abs(v - sorted[i - 1] - step) > 1e-9 * Math.abs(step) + 1e-18)) return null;
  return [sorted[0], sorted[sorted.length - 1], step];
}

/** The ratio r when the text is r*leader, leader*r or leader/r with a plain number r > 0, else null. */
function plainRatio(expression: unknown): number | null {
  if (typeof expression !== 'string') return null;
  const number = '([0-9]*\\.?[0-9]+(?:[eE][-+]?[0-9]+)?)';
  const forms: [RegExp, (n: number) => number][] = [
    [new RegExp(`^\\s*${number}\\s*\\*\\s*leader\\s*$`), n => n], [new RegExp(`^\\s*leader\\s*\\*\\s*${number}\\s*$`), n => n],
    [new RegExp(`^\\s*leader\\s*/\\s*${number}\\s*$`), n => 1 / n], [/^\s*leader\s*$/, () => 1]];
  for (const [form, ratio] of forms) {
    const match = form.exec(expression);
    if (match) { const r = ratio(Number(match[1] ?? 1)); return Number.isFinite(r) && r > 0 ? r : null; }
  }
  return null;
}

function migrateParameter(row: Json): Json {
  if (!row || typeof row !== 'object' || !(RETIRED_PARAMETER_KEYS.some(key => key in row) || row.value_type === 'discrete')) return row;
  const notes: string[] = [];
  let out: Json = { ...row };
  if (row.relation === 'expression') {
    const ratio = plainRatio(row.expression);
    if (ratio !== null) out.ratio = ratio;
    else notes.push(`Was relation expression ${JSON.stringify(row.expression ?? '')}: give the ratio (kept ${row.ratio ?? 1}).`);
  }
  if (row.value_type === 'discrete') {
    const grid = uniformGrid(row.candidates);
    if (grid) [out.lower, out.upper, out.step] = grid;
    else notes.push(`Was value_type discrete with candidates ${JSON.stringify(row.candidates ?? null)}: give lower, upper and step.`);
    out.value_type = 'continuous';
  }
  if (row.target_kind && row.target_kind !== 'instance_parameter') notes.push(`Was target_kind ${row.target_kind}: the optimizer writes instance parameters only.`);
  out = without(out, RETIRED_PARAMETER_KEYS);
  if (notes.length) out.notes = [row.notes, ...notes].filter(Boolean).join(' ');
  return out;
}

/** The text field this change was typed into, or null (a select, a tick box, a button, an answer that arrived meanwhile).
 *  Changes typed into ONE field less than MERGE_MS apart are one Undo step (user choice 2026-09-30: typing 1.5e-6 used to
 *  take six Undo presses, and the 100 kept steps ran out while typing). The field is the one whose input event is being
 *  handled, not the focused one: an agent proposal applied, rows read from Virtuoso or a change in a pop-up window while a
 *  cell had focus joined its typing step, and Undo took them away with the typed text (review of 2026-10-01). Tag names,
 *  not instanceof: a pop-up window's fields belong to that window. */
const MERGE_MS = 1500;
const inputWindows = new Set<Window>();
/** A portal's native input event belongs to its own window, even though React updates the workbench's store. */
export function registerInputWindow(view: Window) {
  inputWindows.add(view);
  return () => { inputWindows.delete(view); };
}
function typingField(): Element | null {
  const event = window.event ?? [...inputWindows].map(view => view.event).find(Boolean);
  const e = event && ['input', 'change', 'compositionend'].includes(event.type) ? event.target as HTMLInputElement | null : null;
  if (e?.tagName === 'TEXTAREA') return e;
  return e?.tagName === 'INPUT' && !['checkbox', 'radio', 'file', 'button', 'submit'].includes(e.type) ? e : null;
}

type History = { config: Json; past: Json[]; future: Json[]; field: Element | null; at: number };
type HistoryAction = { type: 'set'; next: Json | ((c: Json) => Json); record: boolean; field: Element | null; at: number }
  | { type: 'undo' | 'redo' } | { type: 'blur'; field: Element };

// React may replay this reducer in StrictMode. Configuration and history move together,
// without changing refs or the arrays of a previous state.
function configHistory(state: History, action: HistoryAction): History {
  if (action.type === 'blur') return state.field === action.field ? { ...state, field: null, at: 0 } : state;
  if (action.type === 'set') {
    const config = typeof action.next === 'function' ? action.next(state.config) : action.next;
    if (!action.record) return config === state.config ? state : { ...state, config };
    if (JSON.stringify(config) === JSON.stringify(state.config)) return state;
    const merge = action.field !== null && action.field === state.field && action.at - state.at < MERGE_MS && state.past.length > 0;
    return { config, past: merge ? state.past : [...state.past.slice(-(HISTORY_LIMIT - 1)), state.config],
      future: [], field: action.field, at: action.at };
  }
  const from = action.type === 'undo' ? state.past : state.future;
  if (!from.length) return { ...state, field: null, at: 0 };
  return { config: from[from.length - 1], field: null, at: 0,
    past: action.type === 'undo' ? state.past.slice(0, -1) : [...state.past, state.config],
    future: action.type === 'redo' ? state.future.slice(0, -1) : [...state.future, state.config] };
}

/** Configuration state with undo/redo and local persistence (kept in the browser by itself, 0.8 s after each change - the
 *  editors' "Save" button that did the same at once went on 2026-09-22; "Export JSON" writes a file, and a started run
 *  stores its own effective_config.json). A change still waiting for those 0.8 s is written when the page goes away.
 *  `fresh`: this browser had no saved configuration when the page opened (blocked site storage counts as fresh). */
export function useConfig() {
  const [fresh] = useState(() => { try { return localStorage.getItem(STORAGE_KEY) === null; } catch { return true; } });
  const [history, dispatch] = useReducer(configHistory, undefined, (): History => {
    let config: Json;
    try { config = migrateConfig(JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')) ?? emptyConfig(); } catch { config = emptyConfig(); }
    return { config, past: [], future: [], field: null, at: 0 };
  });
  const { config } = history;

  const setConfig = useCallback((next: Json | ((c: Json) => Json), record = true) => {
    dispatch({ type: 'set', next, record, field: record ? typingField() : null, at: Date.now() });
  }, []);

  // Undo and redo are one move between the two histories, in opposite directions.
  const undo = useCallback(() => dispatch({ type: 'undo' }), []);
  const redo = useCallback(() => dispatch({ type: 'redo' }), []);
  // Leaving the field ends its typing: typing there again - even at once - is an Undo step of its own.
  useEffect(() => {
    const field = history.field;
    if (!field) return;
    const left = () => dispatch({ type: 'blur', field });
    // Listen on the field itself so leaving an input in a separate window also ends the Undo step.
    field.addEventListener('blur', left);
    return () => field.removeEventListener('blur', left);
  }, [history.field]);

  const latest = useRef(config), unsaved = useRef(false);
  latest.current = config;
  // What this page stored last (or found when it opened): the flush below only replaces that.
  const stored = useRef<string | null>(null);
  if (stored.current === null) { try { stored.current = localStorage.getItem(STORAGE_KEY) ?? ''; } catch { stored.current = ''; } }
  const [saveError, setSaveError] = useState<string | null>(null);
  const save = useCallback(() => {
    try {
      const text = JSON.stringify(latest.current);
      localStorage.setItem(STORAGE_KEY, text);
      stored.current = text; unsaved.current = false; setSaveError(null);
    } catch {
      unsaved.current = true;
      setSaveError('Changes could not be saved in this browser. Export JSON before closing this page, or retry saving.');
    }
  }, []);
  useEffect(() => { unsaved.current = true; const id = setTimeout(save, 800); return () => clearTimeout(id); }, [config, save]);
  // A reload or a closed tab less than 0.8 s after the last change used to lose that change. Not over a configuration
  // another tab (or a check script) stored meanwhile: then the page leaves it as it is.
  useEffect(() => {
    const flush = () => { try { if (unsaved.current && (localStorage.getItem(STORAGE_KEY) ?? '') === stored.current) save(); } catch { /* no storage */ } };
    window.addEventListener('pagehide', flush);
    return () => window.removeEventListener('pagehide', flush);
  }, []);

  return { config, setConfig, undo, redo, canUndo: history.past.length > 0, canRedo: history.future.length > 0, fresh, saveError, retrySave: save };
}

export function usePolling<T>(fn: (signal: AbortSignal) => Promise<T>, ms: number, enabled: boolean, deps: unknown[]) {
  return useRequest(fn, deps, { enabled, pollEvery: ms });
}

/** Button actions keep their feature's confirmations and messages; only the pending lifecycle is shared. */
export function useAsyncAction(onError: (error: any, name: string) => void, onStart: () => void) {
  const [busy, setBusy] = useState<string | null>(null);
  const generation = useRef(0);
  const run = async (name: string, action: () => Promise<unknown>) => {
    const mine = ++generation.current;
    setBusy(name); onStart();
    try { await action(); } catch (error) { onError(error, name); }
    finally { if (mine === generation.current) setBusy(null); }
  };
  return { busy, run };
}

/** A read follows explicit dependencies. Replies to an earlier selection or an unmounted view are discarded. */
const sameDependencies = (a: unknown[], b: unknown[]) => a.length === b.length && a.every((v, i) => Object.is(v, b[i]));

export function useRequest<T>(fn: (signal: AbortSignal) => Promise<T>, deps: unknown[], { enabled = true, delay = 0, keepPrevious = false, pollEvery = 0, timeoutMs = 30000 }:
  { enabled?: boolean; delay?: number; keepPrevious?: boolean; pollEvery?: number | ((value: T | null) => number); timeoutMs?: number } = {}) {
  const [result, setResult] = useState<{ deps: unknown[]; value: T | null; error: string | null }>({ deps: [], value: null, error: null });
  const [loading, setLoading] = useState(false);
  const [revision, refresh] = useState(0);
  const immediate = useRef(false);
  const inFlight = useRef<{ controller: AbortController; promise: Promise<T> } | null>(null);
  const cancel = useCallback(() => { inFlight.current?.controller.abort(); inFlight.current = null; }, []);
  // Interval changes can reuse a read; changing the selection, disabling or leaving cancels it.
  useEffect(() => cancel, [enabled, timeoutMs, ...deps]);
  const asked = useRef<unknown[] | null>(null);
  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    // Another selection starts empty; a refresh of the SAME one keeps its answer until the new one comes (a Refresh used
    // to blank Data tables, Output files and Corner check and lose the scroll position).
    const another = !asked.current || !sameDependencies(asked.current, deps);
    asked.current = deps;
    if ((!keepPrevious && !pollEvery && another) || !enabled) setResult({ deps, value: null, error: null });
    setLoading(enabled);
    if (!enabled) return;
    const read = async () => {
      let value: T | null = null;
      if (!inFlight.current) {
        const controller = new AbortController();
        inFlight.current = { controller, promise: readWithDeadline(fn, controller.signal, timeoutMs) };
      }
      const request = inFlight.current;
      try {
        value = await request.promise;
        if (live && !request.controller.signal.aborted) setResult({ deps, value, error: null });
      }
      catch (e: any) { if (live && !request.controller.signal.aborted) setResult({ deps, value: null, error: String(e.message ?? e) }); }
      finally {
        if (inFlight.current === request) inFlight.current = null;
        if (live && !request.controller.signal.aborted) {
          setLoading(false);
          const interval = typeof pollEvery === 'function' ? pollEvery(value) : pollEvery;
          if (interval) timer = setTimeout(read, interval);
        }
      }
    };
    const wait = immediate.current ? 0 : delay;
    immediate.current = false;
    // Even a zero delay lets StrictMode's setup/cleanup replay cancel the first scheduled read.
    timer = setTimeout(read, wait);
    return () => { live = false; clearTimeout(timer); };
  }, [enabled, delay, keepPrevious, pollEvery, timeoutMs, revision, ...deps]);
  // Hide the old selection during render, before effect cleanup/reset has run. A changed polling interval
  // retains the same run's result; a changed run/table never inherits it. Validation opts into keepPrevious.
  const current = sameDependencies(deps, result.deps);
  return { value: enabled && (current || keepPrevious) ? result.value : null,
    error: enabled && current ? result.error : null, loading: enabled && (loading || !current),
    refresh: useCallback(() => { cancel(); immediate.current = true; refresh(n => n + 1); }, [cancel]) };
}
