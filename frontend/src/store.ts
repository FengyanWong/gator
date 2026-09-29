import { useCallback, useEffect, useRef, useState } from 'react';
import type { Json } from './api';

const STORAGE_KEY = 'gator-workbench-config-v1';
const HISTORY_LIMIT = 100;

const emptyConfig = (): Json => ({
  schema_version: 'gator-workbench-config-v1',
  project: { name: 'gator-project', task_name: 'task', notes: '' },
  circuit: { source: 'registered_task', task_id: 'synthetic:gpdk045_ota5', circuit_class: 'unspecified', pdk_id: 'unspecified' },
  parameters: [], targets: [], measurements: [],
  run: { mode: 'scratch', max_evaluations: 60, concurrency: 1, threads_per_job: 1, seed: 0, reward: { violation_shape: 'compressed', worst_spec_share: 0.5 } },
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

/** Configuration state with undo/redo and local persistence (kept in the browser by itself, 0.8 s after each change - the
 *  editors' "Save" button that did the same at once went on 2026-09-22; "Export JSON" writes a file, and a started run
 *  stores its own effective_config.json). */
export function useConfig() {
  const [config, setConfigState] = useState<Json>(() => {
    try { return migrateConfig(JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null')) ?? emptyConfig(); } catch { return emptyConfig(); }
  });
  const past = useRef<Json[]>([]);
  const future = useRef<Json[]>([]);
  const [, bump] = useState(0);

  const setConfig = useCallback((next: Json | ((c: Json) => Json), record = true) => {
    setConfigState((current: Json) => {
      const value = typeof next === 'function' ? next(current) : next;
      if (record && JSON.stringify(value) !== JSON.stringify(current)) {
        past.current = [...past.current.slice(-HISTORY_LIMIT), current];
        future.current = [];
      }
      return value;
    });
    bump(n => n + 1);
  }, []);

  // Undo and redo are one move between the two histories, in opposite directions.
  const move = (from: { current: Json[] }, to: { current: Json[] }) => {
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

  useEffect(() => { const id = setTimeout(() => localStorage.setItem(STORAGE_KEY, JSON.stringify(config)), 800); return () => clearTimeout(id); }, [config]);

  return { config, setConfig, undo, redo, canUndo: past.current.length > 0, canRedo: future.current.length > 0 };
}

export function usePolling<T>(fn: () => Promise<T>, ms: number, enabled: boolean, deps: unknown[]) {
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

export function useRequest<T>(fn: () => Promise<T>, deps: unknown[], { enabled = true, delay = 0, keepPrevious = false, pollEvery = 0 }:
  { enabled?: boolean; delay?: number; keepPrevious?: boolean; pollEvery?: number | ((value: T | null) => number) } = {}) {
  const [result, setResult] = useState<{ deps: unknown[]; value: T | null; error: string | null }>({ deps: [], value: null, error: null });
  const [loading, setLoading] = useState(false);
  const [revision, refresh] = useState(0);
  const immediate = useRef(false);
  const inFlight = useRef<{ deps: unknown[]; promise: Promise<T> } | null>(null);
  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    if ((!keepPrevious && !pollEvery) || !enabled) setResult({ deps, value: null, error: null });
    setLoading(enabled);
    if (!enabled) return;
    const read = async () => {
      let value: T | null = null;
      try {
        // A refresh or interval change can reuse an outstanding read of the same selection.
        if (!inFlight.current || !sameDependencies(inFlight.current.deps, deps)) {
          const promise = Promise.resolve().then(fn).finally(() => {
            if (inFlight.current?.promise === promise) inFlight.current = null;
          });
          inFlight.current = { deps, promise };
        }
        value = await inFlight.current.promise;
        if (live) setResult({ deps, value, error: null });
      }
      catch (e: any) { if (live) setResult({ deps, value: null, error: String(e.message ?? e) }); }
      finally {
        if (live) {
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
  }, [enabled, delay, keepPrevious, pollEvery, revision, ...deps]);
  // Hide the old selection during render, before effect cleanup/reset has run. A changed polling interval
  // retains the same run's result; a changed run/table never inherits it. Validation opts into keepPrevious.
  const current = sameDependencies(deps, result.deps);
  return { value: enabled && (current || keepPrevious) ? result.value : null,
    error: enabled && current ? result.error : null, loading: enabled && (loading || !current),
    refresh: useCallback(() => { immediate.current = true; refresh(n => n + 1); }, []) };
}
