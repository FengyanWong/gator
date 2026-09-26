import { useCallback, useEffect, useRef, useState } from 'react';
import type { Json } from './api';

const STORAGE_KEY = 'gator-workbench-config-v1';
const HISTORY_LIMIT = 100;

const emptyConfig = (): Json => ({
  schema_version: 'gator-workbench-config-v1',
  project: { name: 'gator-project', task_name: 'task', notes: '' },
  circuit: { source: 'registered_task', task_id: 'synthetic:gpdk045_ota5', circuit_class: 'unspecified', pdk_id: 'unspecified' },
  parameters: [], targets: [], measurements: [],
  run: { mode: 'scratch', max_evaluations: 60, concurrency: 1, threads_per_job: 1, seed: 0 },
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

/** Columns retired on 2026-09-26 (record 7.92). The backend drops them the same way when it reads a row, so a row here
 *  equals the row it serves back; what they meant is kept in the columns that remain (an expression relation as the
 *  ratio, a discrete candidate grid as lower/upper/step), and a value that cannot be kept goes into the notes. */
const RETIRED_PARAMETER_KEYS = ['name', 'target_kind', 'candidates', 'relation', 'expression'];
const RETIRED_MEASUREMENT_KEYS = ['function', 'window', 'at_frequency_hz', 'integration_band_hz', 'branch_direction', 'loop_definition', 'crossover', 'on_failure', 'validity'];

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

  const undo = useCallback(() => {
    setConfigState((current: Json) => {
      const previous = past.current.pop();
      if (previous === undefined) return current;
      future.current.push(current);
      return previous;
    });
    bump(n => n + 1);
  }, []);

  const redo = useCallback(() => {
    setConfigState((current: Json) => {
      const next = future.current.pop();
      if (next === undefined) return current;
      past.current.push(current);
      return next;
    });
    bump(n => n + 1);
  }, []);

  useEffect(() => { const id = setTimeout(() => localStorage.setItem(STORAGE_KEY, JSON.stringify(config)), 800); return () => clearTimeout(id); }, [config]);

  return { config, setConfig, undo, redo, canUndo: past.current.length > 0, canRedo: future.current.length > 0 };
}

export function usePolling<T>(fn: () => Promise<T>, ms: number, enabled: boolean, deps: unknown[]) {
  const [value, setValue] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!enabled) { setValue(null); return; }
    let alive = true;
    const tick = () => fn().then(v => { if (alive) { setValue(v); setError(null); } }).catch(e => alive && setError(String(e.message || e)));
    tick();
    const id = setInterval(tick, ms);
    return () => { alive = false; clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ms, ...deps]);
  return { value, error };
}
