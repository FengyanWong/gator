import { useCallback, useEffect, useRef, useState } from 'react';
import { readWithDeadline, type Json } from './api';

const STORAGE_KEY = 'gator-workbench-config-v1';
const HISTORY_LIMIT = 100;

const emptyConfig = (): Json => ({
  schema_version: 'gator-workbench-config-v1',
  project: { name: 'gator-project', task_name: 'task', notes: '' },
  // No task until one is chosen: the MOCK task that used to open here was deleted on 2026-09-30 (record 7.128).
  circuit: { source: 'registered_task', task_id: null, circuit_class: 'unspecified', pdk_id: 'unspecified' },
  parameters: [], targets: [], measurements: [],
  run: { mode: 'scratch', max_evaluations: 60, concurrency: 1, seed: 0, reward: { violation_shape: 'compressed', worst_spec_share: 0.5 } },
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
  if (Array.isArray(config.measurements)) out = { ...out, measurements: config.measurements.map((row: Json) => without(row, RETIRED_MEASUREMENT_KEYS)) };
  // "Threads per job" retired on 2026-09-29: no simulator ever used it. The backend drops it too and hashes it at 1.
  if (config.run && typeof config.run === 'object' && 'threads_per_job' in config.run) out = { ...out, run: without(config.run, ['threads_per_job']) };
  return out;
}

/** Columns retired on 2026-09-26 (record 7.92), and the Probes' conditions and aggregation on 2026-09-29 (record 7.105).
 *  The backend drops them the same way when it reads a row, so a row here
 *  equals the row it serves back; what they meant is kept in the columns that remain (an expression relation as the
 *  ratio, a discrete candidate grid as lower/upper/step), and a value that cannot be kept goes into the notes. */
const RETIRED_PARAMETER_KEYS = ['name', 'target_kind', 'candidates', 'relation', 'expression'];
const RETIRED_MEASUREMENT_KEYS = ['function', 'window', 'at_frequency_hz', 'integration_band_hz', 'branch_direction', 'loop_definition', 'crossover', 'on_failure', 'validity',
  'conditions', 'aggregation'];

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
function typingField(): Element | null {
  const event = window.event;
  const e = event && ['input', 'change', 'compositionend'].includes(event.type) ? event.target as HTMLInputElement | null : null;
  if (e?.tagName === 'TEXTAREA') return e;
  return e?.tagName === 'INPUT' && !['checkbox', 'radio', 'file', 'button', 'submit'].includes(e.type) ? e : null;
}

/** Configuration state with undo/redo and local persistence (kept in the browser by itself, 0.8 s after each change - the
 *  editors' "Save" button that did the same at once went on 2026-09-22; "Export JSON" writes a file, and a started run
 *  stores its own effective_config.json). A change still waiting for those 0.8 s is written when the page goes away.
 *  `fresh`: this browser had no saved configuration when the page opened (blocked site storage counts as fresh). */
export function useConfig() {
  const [fresh] = useState(() => { try { return localStorage.getItem(STORAGE_KEY) === null; } catch { return true; } });
  const [config, setConfigState] = useState<Json>(() => {
    try { return migrateConfig(JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')) ?? emptyConfig(); } catch { return emptyConfig(); }
  });
  const past = useRef<Json[]>([]);
  const future = useRef<Json[]>([]);
  const typed = useRef<{ field: Element | null; at: number }>({ field: null, at: 0 });
  const [, bump] = useState(0);

  const setConfig = useCallback((next: Json | ((c: Json) => Json), record = true) => {
    const field = record ? typingField() : null, now = Date.now();
    setConfigState((current: Json) => {
      const value = typeof next === 'function' ? next(current) : next;
      if (record && JSON.stringify(value) !== JSON.stringify(current)) {
        // More typing in the same field: the step taken at its first key already brings back what was there before.
        const merge = field !== null && field === typed.current.field && now - typed.current.at < MERGE_MS && past.current.length > 0;
        if (!merge) past.current = [...past.current.slice(-HISTORY_LIMIT), current];
        future.current = [];
        typed.current = { field, at: now };
      }
      return value;
    });
    bump(n => n + 1);
  }, []);

  // Undo and redo are one move between the two histories, in opposite directions.
  const move = (from: { current: Json[] }, to: { current: Json[] }) => {
    typed.current = { field: null, at: 0 };
    setConfigState((current: Json) => {
      const taken = from.current.pop();
      if (taken === undefined) return current;
      to.current.push(current);
      return taken;
    });
    bump(n => n + 1);
  };
  const undo = useCallback(() => move(past, future), []);
  const redo = useCallback(() => move(future, past), []);
  // Leaving the field ends its typing: typing there again - even at once - is an Undo step of its own.
  useEffect(() => {
    const left = (e: FocusEvent) => { if (e.target === typed.current.field) typed.current = { field: null, at: 0 }; };
    document.addEventListener('focusout', left, true);
    return () => document.removeEventListener('focusout', left, true);
  }, []);

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

  return { config, setConfig, undo, redo, canUndo: past.current.length > 0, canRedo: future.current.length > 0, fresh, saveError, retrySave: save };
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
