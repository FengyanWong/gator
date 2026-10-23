// The editors' rules (plan-refactoring C6, out of Editors.tsx): the tables' names and headers, the scale a Specs row is offered,
// the Specs' limit list, typed numbers, the tooltip of a cell that differs from the saved task, the fields that follow a
// change of a row, and the row Add makes. No React.
import type { Json } from '../api';
import { kindUnit, PREFIX_POWERS as SUFFIX, sameQuantity } from '../units';

export type Section = 'parameters' | 'targets' | 'measurements';

/** The three tables by their tabs' names; key order = tab order. Here since branch record SIF-51, out of Editors.tsx, so the
 *  import and Matched devices confirmations (DiffView) say Probes and Specs where they said "measurements" and "targets". */
export const SECTION_TITLES: Record<Section, string> = { parameters: 'Parameters', measurements: 'Probes', targets: 'Specs' };

/** The editor tables' headers in plain words (record 7.188); the field names - what the task files, Export JSON and the agent
 *  use - stay in each header's tooltip, in the formula bar's format note and on the help line a header press opens. The few
 *  columns that had a word of their own keep it (Expression, Judged at, Missing value = failed, Margin sides, Scale): Editors.tsx
 *  set those apart until branch record SIF-51, when the confirmations of an import and of Matched devices began to name the
 *  fields by these words too ("binding_group" read where the header says "Tied to").
 *  `signal` holds a Maestro output's expression (ymax(VT("/OUT")), getData(... ?result "stb")): "signal" read like a net name
 *  (review of 2026-10-03). For a profile metric it is a label of what is measured. */
export const LABELS: Record<string, Record<string, string>> = {
  parameters: { variable_id: 'ID', instance_path: 'Instance', parameter_name: 'Parameter', initial_value: 'Initial value', unit: 'Unit', optimized: 'Optimized',
    value_type: 'Value type', lower: 'Lower', upper: 'Upper', step: 'Step', scale: 'Search scale', binding_group: 'Tied to', ratio: 'Ratio', notes: 'Notes' },
  measurements: { measurement_id: 'Probe ID', analysis: 'Analysis', result_source: 'Result source', source_name: 'Output name', signal: 'Expression',
    unit: 'Unit', notes: 'Notes' },
  targets: { metric_id: 'Spec ID', equation: 'Equation', unit: 'Unit', constraint: 'Limit', lower: 'Lower', upper: 'Upper', hard: 'Hard',
    direction_after_feasible: 'Objective', nominal_only: 'Judged at', missing_is_failure: 'Missing value = failed', margin_sides: 'Margin sides',
    soft_weight: 'Soft weight', normalization_scale: 'Scale', active: 'Active', basis: 'Basis' },
};
/** A field by its header's word, or by its name where no header has one. */
export const fieldLabel = (section: string, field: string): string => LABELS[section]?.[field] ?? field;
/** The column a field is chosen in: the Specs' objective is in the Limit list (LimitSelect). */
export const columnOf = (section: string, field: string): string => section === 'targets' && field === 'direction_after_feasible' ? 'constraint' : field;
/** Whether a table draws a column (More columns shows the advanced ones): never a hidden one (schema.HIDDEN_COLUMNS:
 *  initial_value, result_source, the Unit of Parameters and Specs), nor the Specs' objective (in the Limit list), and "Judged
 *  at" only while the run plans training corners - without corners every spec is judged at nominal, so the choice would do
 *  nothing. They keep their values. Here, out of Editors.tsx, since the review of branch record SIF-95: an issue's Where in the
 *  header's list says by it which cell it chooses. */
export const drawsColumn = (section: string, column: Json, config: Json): boolean => !column.hidden && (section !== 'targets'
  || (column.name !== 'direction_after_feasible' && (column.name !== 'nominal_only' || (config?.run?.conditions?.policy ?? 'off') !== 'off')));
/** The unit of a row of `config` by its table and ID (`keys`: each table's ID field, schema.section_keys), for a table that
 *  writes the row's numbers as its cells do (DiffView, branch record SIF-51); null for a row that is not there. */
export const unitIn = (config: Json, keys: Record<string, string>) => (section: string, key: string): string | null =>
  (config?.[section] ?? []).find((r: Json) => keys[section] && r[keys[section]] === key)?.unit ?? null;

/** The scale offered while nobody has typed one, or null when the row gives nothing to size it by yet: then the scale stays
 * empty and the backend sizes it from the limits (the size of the threshold, else 1), instead of freezing a bare 1 W or
 * 1 Hz into a row whose limits are typed afterwards (record 7.112).
 * One rule since record 7.183: the size of the limit - which is what an empty scale means too - and 6 dB (a factor of two)
 * for a dB row, where "a fraction of a 40 dB limit" makes each dB count for little. On the 227 recorded designs the tighter
 * suggestions of before acted as hidden weights: 10 degrees on a phase row reordered the designs, and half the width of an
 * interval put most of a ring oscillator's designs above a miss of 0.9. */
export function suggestedScale(row: Json): number | null {
  if (row.unit === 'dB') return 6;
  return Math.max(...[row.lower, row.upper].filter(v => typeof v === 'number').map(Math.abs), 0) || null;
}
/** What the page suggested until record 7.183 (3 dB, 10 degrees, half an interval): a row that still holds it was never typed
 * into, so it follows the next edit to today's suggestion instead of keeping the old number for good. */
function formerSuggestion(row: Json): number | null {
  if (row.unit === 'dB') return 3;
  if (row.unit === 'deg') return 10;
  if (row.constraint === 'interval' && row.lower != null && row.upper != null && row.upper > row.lower) return (row.upper - row.lower) / 2;
  return null;
}
const SCALE_FIELDS = ['unit', 'lower', 'upper', 'constraint'];
/** The scale after an edit of a field it depends on: an empty scale, or one still equal to the row's suggestion before the
 * edit, follows the edit; a scale the user typed stays. */
function followScale(before: Json, after: Json): number | null {
  const untouched = before.normalization_scale == null || before.normalization_scale === suggestedScale(before)
    || before.normalization_scale === formerSuggestion(before);
  return untouched ? suggestedScale(after) : after.normalization_scale;
}

/** Specs: the limit and the objective in ONE list. An objective means "once every hard spec passes, the lower (higher) the
 *  better" and works on the limit on its side (minimize an upper limit, maximize a lower one), so a pair that could never
 *  work (>= then lower is better) is not offered. Saved as before: `constraint` + `direction_after_feasible`. */
export const LIMIT_CHOICES: [string, string][] = [['>=', 'none'], ['>=', 'maximize'], ['<=', 'none'], ['<=', 'minimize'],
  ['interval', 'none'], ['interval', 'minimize'], ['interval', 'maximize']];
// "target ± tolerance" went with its two columns (review of 2026-10-03): it was exactly an interval [target - tolerance,
// target + tolerance], and a tolerance on any other row only loosened its limit. Older rows are rewritten so when they load.
const LIMIT_TEXT: Record<string, string> = { '>=': '≥ lower', '<=': '≤ upper', interval: 'interval' };
// A row without a constraint read "undefined", and an objective this list does not know read like a plain limit (review of
// 2026-10-01): both are shown as they are.
export const limitLabel = (constraint: string, objective: string) => (constraint ? LIMIT_TEXT[constraint] ?? String(constraint) : '(not set)')
  + (objective === 'minimize' ? ', then lower is better' : objective === 'maximize' ? ', then higher is better'
    : objective && objective !== 'none' ? `, then ${objective}` : '');

/** A cell's tooltip with the saved task's value first, when the value here differs from it (record 7.222). */
export const withSaved = (saved: string | null | undefined, title: Json): Json =>
  saved != null ? `Saved in the task: ${saved}.${title ? `\n${title}` : ''}` : title;

/** The numbers that carry their row's unit (record 7.208): written as every quantity is (units.ts - 450 nm, 400 uA), typed in
 *  any form. Record 7.181 wrote only very small and very large numbers of an unprefixed unit this way, without the unit. */
export const QUANTITY: Record<string, string[]> = { parameters: ['lower', 'upper', 'step', 'initial_value'], targets: ['lower', 'upper', 'normalization_scale'] };
/** A typed number: plain, with an exponent (2.5e-6), or with an SI letter (2.5u, 400µ, 10k). */
export function readNumber(text: string): number | undefined {
  const s = text.trim(), letter = /^([-+]?(?:\d+\.?\d*|\.\d+))([fpnuµμmkKMGT])$/.exec(s);
  const n = letter ? Number(`${letter[1]}e${SUFFIX[letter[2]]}`) : s === '' ? NaN : Number(s);
  return Number.isFinite(n) ? n : undefined;
}

// What a follower row (binding_group set) leaves to its leader: the written value is the leader's times the ratio, so its own
// bounds, step, scale, type and "optimized" do nothing (Save task even clears its bounds).
export const FOLLOWER_IGNORES = ['optimized', 'value_type', 'lower', 'upper', 'step', 'scale'];
// A Maestro output's Probe ID is m_ + its name, as Save task names it (virtuoso_setup.probe_id); spec equations are rewritten
// when it follows a renamed output. Equation names are plain identifiers (spec_equations.parse reads them with Python's ast).
const probeIdOf = (outputName: string) => `m_${outputName}`;
// A Probe ID as a whole name in an equation. equationRenamer spells the same pattern out because
// scripts/editor_renames_check.mjs (record 7.377) pins its text: change both together.
const nameIn = (id: string, flags = '') => new RegExp(`(?<![A-Za-z0-9_.])${id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![A-Za-z0-9_])`, flags);
const equationRenamer = (from: string, to: string) => {
  // An edit may touch many Specs. Compile once for this rename, only when a string equation needs it.
  let pattern: RegExp | undefined;
  return (equation: string) => equation.replace(pattern ??= new RegExp(`(?<![A-Za-z0-9_.])${from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![A-Za-z0-9_])`, 'g'), to);
};
/** Whether an equation names the Probe `id` as a whole name, as a rename finds it (branch record SIF-96: Delete selected names
 *  the Specs whose equation a deleted Probe breaks, on a tab not in view). */
export const usesProbe = (equation: string, id: string): boolean => !!id && nameIn(id).test(equation);

export const exact = (v: Json) => (v == null ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v));

/** Fields that follow a change with it, in the same Undo step (review of 2026-10-03): a Maestro output's Probe ID follows its
 * output name, and the spec equations that use the ID follow it; a spec whose equation becomes one Probe takes that Probe's
 * unit while it has no limits yet (its unit must match the Probe's anyway; a prefix can be typed after); the scale follows
 * only a field that really changes - picking an objective re-sends the unchanged limit, and an empty (backend-sized) scale
 * must not be frozen into the row by that. One path for a typed cell, a pasted block and a fill since record 7.184 (a pasted
 * output name had left its Probe ID behind); a limit written without its objective keeps the objective where they still pair. */
export function withFollowers(tab: Section, c: Json, changes: Map<number, Json>): Json {
  const renames: ((equation: string) => string)[] = [], moves: [string, string][] = [];
  const next = { ...c, [tab]: c[tab].map((r: Json, i: number) => {
    const fields = changes.get(i);
    if (!fields) return r;
    const row = { ...r, ...fields };
    // No Unit column for Parameters (record 7.208): a row whose parameter has a known kind (w, l) is in that kind's unit.
    if (tab === 'parameters' && 'parameter_name' in fields) { const kind = kindUnit(row.parameter_name); if (kind && !sameQuantity(row.unit, kind)) row.unit = kind; }
    if (tab === 'measurements' && 'unit' in fields && row.unit && !sameQuantity(r.unit, row.unit)) moves.push([String(row.measurement_id), row.unit]);
    if (tab === 'measurements' && typeof fields.source_name === 'string' && r.result_source === 'ade_output'
        && /^[A-Za-z_][A-Za-z0-9_]*$/.test(fields.source_name)) {
      row.measurement_id = probeIdOf(fields.source_name);
      if (r.measurement_id && r.measurement_id !== row.measurement_id) renames.push(equationRenamer(String(r.measurement_id), row.measurement_id));
    }
    if (tab === 'targets') {
      const probe = typeof fields.equation === 'string' && !('unit' in fields)
        ? (c.measurements ?? []).find((m: Json) => m.measurement_id === fields.equation.trim()) : null;
      if (probe?.unit && (!r.unit || !sameQuantity(r.unit, probe.unit))) row.unit = probe.unit;   // the Probe's quantity (7.208)
      if ('constraint' in fields && !('direction_after_feasible' in fields)
          && !LIMIT_CHOICES.some(([limit, objective]) => limit === row.constraint && objective === (row.direction_after_feasible ?? 'none'))) row.direction_after_feasible = 'none';
      if (!('normalization_scale' in fields) && SCALE_FIELDS.some(name => row[name] !== r[name])) row.normalization_scale = followScale(r, row);
    }
    return row;
  }) };
  if (renames.length) next.targets = (c.targets ?? []).map((t: Json) => typeof t.equation === 'string'
    ? { ...t, equation: renames.reduce((e, rename) => rename(e), t.equation) } : t);
  // A Probe now of another quantity: the Specs on it alone take its unit (they have no Unit column since record 7.208).
  if (moves.length) next.targets = (next.targets ?? c.targets ?? []).map((t: Json) => {
    const move = moves.find(([id]) => typeof t.equation === 'string' && t.equation.trim() === id);
    if (!move || sameQuantity(t.unit, move[1])) return t;
    const moved = { ...t, unit: move[1] };
    return { ...moved, normalization_scale: followScale(t, moved) };                  // as a unit typed in the Spec did
  });
  return next;
}

/** The start of a new row's ID (Add), in the tab's own word (branch record SIF-50). */
const NEW_ID: Record<Section, string> = { parameters: 'parameter', measurements: 'probe', targets: 'spec' };
/** The row Add puts at the end of a table of `config` (`schema`: /api/schema, its columns and each table's ID field). Here, out
 *  of Editors.tsx, since branch record SIF-104: the Virtuoso window's "Add to Parameters" makes this row too, with a size's
 *  instance and parameter, so the two cannot differ. */
export function newRow(tab: Section, config: Json, schema: Json): Json {
  const row: Json = {}, keyField: string = schema.section_keys[tab], rows: Json[] = config[tab] ?? [];
  // A required field without a default comes as `default: null` from the schema: that means "none", not null - a new
  // Specs row used to get constraint = null and normalization_scale = null, and the whole configuration failed validation.
  for (const c of schema.editors[tab] as Json[]) row[c.name] = c.default !== undefined && (c.default !== null || c.nullable) ? c.default
    : c.nullable ? null : c.options ? c.options[0] : c.type === 'number' ? 1 : c.type === 'boolean' ? false : '';
  // A new probe measures the way the task's other probes do - a task measures one way, Save task refuses a mix - where it
  // used to take result_source's default, backend_profile, in a Maestro task too (review of 2026-10-03). The first probe of a
  // task: ngspice and MOCK tasks read their backend's metrics, every other task reads Maestro outputs.
  if (tab === 'measurements') row.result_source = config.measurements?.[0]?.result_source
    ?? (/^(ngspice|synthetic):/.test(String(config.circuit?.task_id ?? '')) ? 'backend_profile' : 'ade_output');
  // A free ID: `rows.length + 1` repeated an existing one after a deletion, and "Delete selected" then removed both rows.
  // Named as the tab is (probe_3, spec_4), not by the section key (measurement_3, target_4; branch record SIF-50).
  const used = new Set(rows.map(r => r[keyField]));
  let n = rows.length + 1;
  while (used.has(`${NEW_ID[tab]}_${n}`)) n += 1;
  row[keyField] = `${NEW_ID[tab]}_${n}`;
  // A new spec starts as the simplest equation over the probes: the first probe, in its unit.
  const first = config.measurements?.[0];
  if (tab === 'targets' && first && !row.equation) Object.assign(row, { equation: first.measurement_id ?? '', unit: row.unit || first.unit || '' });
  if (tab === 'targets' && row.normalization_scale == null) row.normalization_scale = suggestedScale(row);
  return row;
}
