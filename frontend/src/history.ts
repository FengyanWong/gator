// The configuration with its Undo history, kept in this browser (plan-refactoring C3, out of store.ts).
import { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import type { Json } from './api';
import type { WorkbenchConfig } from './contracts';
import { CONFIG_KEY as STORAGE_KEY } from './contract';
import { migrateConfig } from './migrations';
import { typingField } from './windows';
import { keep, readKept } from './kept';

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
/** Changes typed into one field less than this apart are one Undo step (windows.ts typingField says which field). */
const MERGE_MS = 1500;

/** The last Undo or Redo and the two configurations it moved between, until the next recorded change (branch record SIF-97):
 *  the editors name what it changed, from whichever panel or window it was pressed in. */
export type HistoryStep = { kind: 'Undo' | 'Redo'; from: WorkbenchConfig; to: WorkbenchConfig };
type History = { config: Json; past: Json[]; future: Json[]; field: Element | null; at: number; step: HistoryStep | null };
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
      future: [], field: action.field, at: action.at, step: null };
  }
  const from = action.type === 'undo' ? state.past : state.future;
  if (!from.length) return { ...state, field: null, at: 0 };
  return { config: from[from.length - 1], field: null, at: 0,
    step: { kind: action.type === 'undo' ? 'Undo' : 'Redo', from: state.config, to: from[from.length - 1] },
    past: action.type === 'undo' ? state.past.slice(0, -1) : [...state.past, state.config],
    future: action.type === 'redo' ? state.future.slice(0, -1) : [...state.future, state.config] };
}

/** Configuration state with undo/redo and local persistence (kept in the browser by itself, 0.8 s after each change - the
 *  editors' "Save" button that did the same at once went on 2026-09-22; "Export JSON" writes a file, and a started run
 *  stores its own effective_config.json). A change still waiting for those 0.8 s is written when the page goes away.
 *  `fresh`: this browser had no saved configuration when the page opened (blocked site storage counts as fresh). */
export function useConfig() {
  const [fresh] = useState(() => readKept(s => s.getItem(STORAGE_KEY) === null, () => true));
  const [history, dispatch] = useReducer(configHistory, undefined, (): History => {
    const config: Json = readKept(s => migrateConfig(JSON.parse(s.getItem(STORAGE_KEY) || 'null')) ?? emptyConfig(), () => emptyConfig());
    return { config, past: [], future: [], field: null, at: 0, step: null };
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
  if (stored.current === null) stored.current = readKept(s => s.getItem(STORAGE_KEY) ?? '', () => '');
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
    const flush = () => keep(s => { if (unsaved.current && (s.getItem(STORAGE_KEY) ?? '') === stored.current) save(); });   // no storage: nothing to flush
    window.addEventListener('pagehide', flush);
    return () => window.removeEventListener('pagehide', flush);
  }, []);

  return { config, setConfig, undo, redo, canUndo: history.past.length > 0, canRedo: history.future.length > 0, lastStep: history.step, fresh, saveError,
    retrySave: save };
}
