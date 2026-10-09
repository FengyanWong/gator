// A task's rows, compared with the editors' rows (plan-refactoring C9, out of Left.tsx): the three tables as a reload leaves them.
import type { Json } from '../api';
import { migrateConfig } from '../store';

export const sameJson = (a: Json, b: Json) => JSON.stringify(a ?? []) === JSON.stringify(b ?? []);

/** The three editors, by their configuration keys: Parameters, Specs, Probes. */
const ROW_SECTIONS = ['parameters', 'targets', 'measurements'];
/** The three tables as a reload leaves them (store.ts migrateConfig), for comparing: a task saved before a column retired
 *  still carries it (`tolerance: 0` on every spec of mscr_ota7t/ring3/vco_lin) and the page drops it when it reloads, so
 *  the rows compared as they came never matched again - switching task asked to discard edits nobody made (record 7.223).
 *  Both sides, as rows on the page can carry a retired field too (an answer that still names one). */
export const tablesOf = (config: Json): Json => migrateConfig(Object.fromEntries(ROW_SECTIONS.map(s => [s, config?.[s] ?? []])));
export const sameRows = (config: Json, starter: Json) => { const a = tablesOf(config), b = tablesOf(starter); return ROW_SECTIONS.every(s => sameJson(a[s], b[s])); };
export const noRows = (config: Json) => ROW_SECTIONS.every(s => !(config[s] ?? []).length);
