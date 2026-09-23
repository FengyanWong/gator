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
  if (!config || !Array.isArray(config.targets)) return config;
  const targets = config.targets.map((row: Json) => row && typeof row === 'object' && 'measurement_id' in row
    ? Object.fromEntries(Object.entries(row).filter(([key]) => !(key === 'measurement_id' && 'equation' in row))
        .map(([key, value]) => [key === 'measurement_id' ? 'equation' : key, value]))
    : row);
  return { ...config, targets };
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
