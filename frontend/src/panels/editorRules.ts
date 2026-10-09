// The editors' rules (plan-refactoring C6, out of Editors.tsx): the scale a Specs row is offered, the Specs' limit list, typed
// numbers, the tooltip of a cell that differs from the saved task, and the fields that follow a change of a row. No React.
import type { Json } from '../api';
import { kindUnit, PREFIX_POWERS as SUFFIX, sameQuantity } from '../units';

export type Section = 'parameters' | 'targets' | 'measurements';

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
const renameInEquation = (equation: string, from: string, to: string) =>
  equation.replace(new RegExp(`(?<![A-Za-z0-9_.])${from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![A-Za-z0-9_])`, 'g'), to);

export const exact = (v: Json) => (v == null ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v));

/** Fields that follow a change with it, in the same Undo step (review of 2026-10-03): a Maestro output's Probe ID follows its
 * output name, and the spec equations that use the ID follow it; a spec whose equation becomes one Probe takes that Probe's
 * unit while it has no limits yet (its unit must match the Probe's anyway; a prefix can be typed after); the scale follows
 * only a field that really changes - picking an objective re-sends the unchanged limit, and an empty (backend-sized) scale
 * must not be frozen into the row by that. One path for a typed cell, a pasted block and a fill since record 7.184 (a pasted
 * output name had left its Probe ID behind); a limit written without its objective keeps the objective where they still pair. */
export function withFollowers(tab: Section, c: Json, changes: Map<number, Json>): Json {
  const renames: [string, string][] = [], moves: [string, string][] = [];
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
      if (r.measurement_id && r.measurement_id !== row.measurement_id) renames.push([String(r.measurement_id), row.measurement_id]);
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
    ? { ...t, equation: renames.reduce((e, [from, to]) => renameInEquation(e, from, to), t.equation) } : t);
  // A Probe now of another quantity: the Specs on it alone take its unit (they have no Unit column since record 7.208).
  if (moves.length) next.targets = (next.targets ?? c.targets ?? []).map((t: Json) => {
    const move = moves.find(([id]) => typeof t.equation === 'string' && t.equation.trim() === id);
    if (!move || sameQuantity(t.unit, move[1])) return t;
    const moved = { ...t, unit: move[1] };
    return { ...moved, normalization_scale: followScale(t, moved) };                  // as a unit typed in the Spec did
  });
  return next;
}
