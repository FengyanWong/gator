// Import preparation is pure; reading a file, fetching its diff and applying it belong to the view.
import type { EditorSection, WorkbenchConfig } from '../contracts';
import { migrateConfig } from '../migrations.ts';
import { LABELS, SECTION_TITLES } from './editorRules.ts';

export const ROW_TABS = Object.keys(SECTION_TITLES) as EditorSection[];
export const IMPORTED_SECTIONS: Record<string, string> = { project: 'project labels', circuit: 'circuit source', run: 'run settings',
  output: 'output settings', research: 'research labels' };

/** Check the import envelope before normalizing rows; do not treat an arbitrary schema_version as a configuration. */
export function prepareImport(incoming: unknown, config: WorkbenchConfig, tab: EditorSection, keyField: string) {
  const object = incoming !== null && typeof incoming === 'object' ? incoming as Record<string, unknown> : {};
  const whole = object.schema_version === 'gator-workbench-config-v1';
  const rowsIn = Array.isArray(object[tab]) ? object[tab] : Array.isArray(incoming) ? incoming : null;
  if (whole && !(['project', 'circuit', 'run', 'output'].every(section => object[section] && typeof object[section] === 'object')
      && ROW_TABS.every(section => object[section] == null || Array.isArray(object[section]))))
    throw new Error('the file says it is a workbench configuration, but its sections (project, circuit, run, output and the three tables) are not all there');
  if (!whole && !rowsIn)
    throw new Error(`the file is neither a workbench configuration (from Export JSON) nor ${SECTION_TITLES[tab]} rows (a list, or an object with "${tab}")`);
  if (!whole && (rowsIn as unknown[]).some(row => !row || typeof row !== 'object' || !(row as Record<string, unknown>)[keyField]))
    throw new Error(`every ${SECTION_TITLES[tab]} row needs its ${LABELS[tab][keyField]} ("${keyField}" in the file)`);
  const next: WorkbenchConfig = migrateConfig(whole ? incoming : { ...config, [tab]: rowsIn });
  const others = Object.keys(IMPORTED_SECTIONS)
    .filter(section => JSON.stringify(config[section] ?? null) !== JSON.stringify(next[section] ?? null));
  return { next, others, rows: whole ? null : { section: tab, value: next[tab] } };
}
