// The editors' cells (plan-refactoring C6, out of Editors.tsx): one cell of a table, a number in its row's unit, the Probes'
// unit list and the Specs' limit list.
import { useRef } from 'react';
import type { Json } from '../api';
import { Typed } from './Typed';
import { NUMBER_FORMS, plainNumberIn, quantity, readQuantity, sameUnit, unitChoices, unitLabel } from '../units';
import { LIMIT_CHOICES, limitLabel, readNumber, withSaved } from './editorRules';

/** A box's natural width in characters (branch record SIF-28): the editors' columns share the card by it, so a number or a
 *  one-letter parameter no longer takes as much room as an expression. Every box still fills its column. */
const NUMBER_SIZE = 11;
const TEXT_SIZE: Record<string, number> = { signal: 40, equation: 40, notes: 28, parameter_name: 8 };

export function LimitSelect({ row, title, onChange }: { row: Json; title: string; onChange: (fields: Json) => void }) {
  const objective = row.direction_after_feasible ?? 'none', current = `${row.constraint}|${objective}`;
  const offered = LIMIT_CHOICES.some(([c, o]) => `${c}|${o}` === current);
  return <select aria-label="Constraint" title={title} value={current} onChange={e => {
      const [constraint, direction_after_feasible] = e.target.value.split('|');
      onChange({ constraint, direction_after_feasible });
    }}>
    {/* a pair this list does not offer (an older row, an import) is shown as it is; validation says what is wrong with it */}
    {!offered && <option value={current}>{limitLabel(row.constraint, objective)}</option>}
    {LIMIT_CHOICES.map(([c, o]) => <option key={`${c}|${o}`} value={`${c}|${o}`}>{limitLabel(c, o)}</option>)}</select>;
}

/** One cell. `fixed`: why the value is shown and not typed - it follows another field (a Maestro output's Probe ID follows
 *  its output name). `off`: why the field does nothing on this row (a follower's bounds, step, scale, type and "optimized":
 *  its leader decides them) - shown greyed, with that reason as its tooltip (review of 2026-10-03). `saved`: the value the
 *  saved task holds, when this one differs (record 7.222) - first in the tooltip. `placeholder`: what an empty number box
 *  means, when the column has a word for it ("no limit", "auto"; branch record SIF-49) - a bare "-" otherwise. */
export function Cell({ column, value, onChange, fixed = null, off = null, unit, stored = null, onPatch, tell, saved = null, placeholder }: { column: Json; value: Json;
  onChange: (v: Json) => void; fixed?: string | null; off?: string | null; unit?: string | null; stored?: string | null;
  onPatch?: (fields: Json) => void; tell?: (text: string) => void; saved?: string | null; placeholder?: string }) {
  const title = withSaved(saved, off ?? fixed ?? column.guidance), disabled = off !== null;
  if (column.name === 'nominal_only') return <select aria-label="Judged at" title={title} disabled={disabled}
    value={value ? 'nominal' : 'all'} onChange={e => onChange(e.target.value === 'nominal')}>
    <option value="all">All planned conditions</option><option value="nominal">Nominal only</option></select>;
  if (fixed !== null) return <input title={title} className="readonly" readOnly value={value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value)} />;
  if (column.options) {
    // A value the list does not hold - or none where one is required (a row from the agent or an import) - is shown as it
    // is: the browser showed the first option as if it were chosen, and choosing that one then changed nothing.
    const missing = value != null ? !column.options.includes(value) : !column.nullable;
    return <select title={title} disabled={disabled} value={value ?? ''} onChange={e => onChange(e.target.value === '' && column.nullable ? null : e.target.value)}>
      {column.nullable && <option value="">(none)</option>}{missing && <option value={value ?? ''} disabled={value == null}>{value ?? '(not set)'}</option>}
      {column.options.map((o: string) => <option key={o} value={o}>{o}</option>)}</select>;
  }
  if (column.type === 'boolean') return <input type="checkbox" title={title} disabled={disabled} checked={!!value} onChange={e => onChange(e.target.checked)} />;
  // The unit a plain number is in, at the end of the tooltip of a box that takes typing (branch record SIF-49): the cell
  // shows a prefix of its own (1 um), and "2" typed into a row stored in m is 2 m.
  if ((column.type === 'number' || column.type === 'integer') && unit !== undefined)
    return <QuantityBox title={disabled ? title : [title, plainNumberIn(unit)].filter(Boolean).join(' ')} disabled={disabled} nullable={!!column.nullable}
      placeholder={placeholder} value={value} unit={unit} stored={stored} tell={tell}
      onCommit={(v, u) => onPatch ? onPatch({ [column.name]: v, ...(u ? { unit: u } : {}) }) : onChange(v)} />;
  // A text left unread is said in words, as a QuantityBox says it (branch record SIF-49): it used to vanish on leaving the cell.
  const where = column.label ?? column.name;
  if (column.type === 'number' || column.type === 'integer') {
    return <Typed title={title} disabled={disabled} className="numeric" size={NUMBER_SIZE} placeholder={placeholder ?? (column.nullable ? '-' : '')} value={value} onChange={onChange}
      format={v => v == null ? '' : String(v)}
      parse={t => { const n = readNumber(t); return t.trim() === '' ? { value: column.nullable ? null : 0 } : n !== undefined ? { value: n } : undefined; }}
      onRefused={t => tell?.(`"${t.trim()}" in ${where} is not a number: ${NUMBER_FORMS}.`)} />;
  }
  if (column.name === 'unit') return <UnitSelect title={title} disabled={disabled} value={value} onChange={onChange} />;
  if (column.type === 'array' || column.type === 'object') {
    return <Typed title={title + ' (JSON)'} disabled={disabled} value={value} onChange={onChange} format={v => v == null ? '' : JSON.stringify(v)}
      parse={t => { if (t.trim() === '') return { value: null }; try { return { value: JSON.parse(t) }; } catch { return undefined; } }}
      onRefused={t => tell?.(`"${t.trim()}" in ${where} is not JSON: a list is written as ["a", "b"].`)} />;
  }
  return <input title={title} disabled={disabled} size={TEXT_SIZE[column.name]} value={value ?? ''} onChange={e => onChange(e.target.value === '' && column.nullable ? null : e.target.value)} />;
}

/** A number of a row in its unit (record 7.208): written the one way (450 nm, 400 uA), typed in any form - 400u, 400 uA,
 *  0.4mA, 4e-4. Parameters and Specs have no Unit column: `unit` is the unit the row's values are read in - its own, or the
 *  one its parameter (w, l: a length) or its Probe says when its own is of another quantity or missing - and a plain number
 *  is in it. A value of another quantity ("5 mV" in a length row) is left unread and said in words (`tell`). The row takes
 *  that unit with the value (`onCommit`'s second argument) when its own was not of it; a row without a unit takes the one
 *  the typed value says. Shown in the unit the row stores (`stored`). */
function QuantityBox({ value, unit, stored, nullable, placeholder, title, disabled, onCommit, tell }: { value: Json; unit: string | null; stored: string | null;
  nullable: boolean; placeholder?: string; title: string; disabled: boolean; onCommit: (v: Json, unit: string | null) => void; tell?: (text: string) => void }) {
  const adopted = useRef<string | null>(null);
  const read = (text: string) => {
    const r = readQuantity(text, unit);
    if ('problem' in r) return undefined;
    adopted.current = r.unit ?? (unit && unit !== stored ? unit : null);
    return { value: r.value ?? (nullable ? null : 0) };
  };
  return <Typed title={title} disabled={disabled} className="numeric" size={NUMBER_SIZE} placeholder={placeholder ?? (nullable ? '-' : '')} value={value}
    format={v => v == null ? '' : typeof v === 'number' ? quantity(v, stored) : String(v)} parse={read} onChange={v => onCommit(v, adopted.current)}
    onRefused={text => { const r = readQuantity(text, unit); if ('problem' in r) tell?.(r.problem); }} />;
}

/** The Probes' Unit column (record 7.208): what the probe measures, chosen from a list in English letters - a list like the
 *  page's others (the browser's own suggestion list looked different; user, 2026-10-05). A unit not in the list stays as it
 *  is. A Spec on the Probe follows a change of quantity (`withFollowers`). */
function UnitSelect({ value, title, disabled, onChange }: { value: Json; title: string; disabled: boolean; onChange: (v: Json) => void }) {
  const choices = unitChoices(), current = value ?? '';
  const shown = choices.find(u => sameUnit(u, current)) ?? current;
  return <select title={title} disabled={disabled} value={shown} onChange={e => { if (!sameUnit(e.target.value, current)) onChange(e.target.value); }}>
    {!choices.includes(shown) && <option value={shown}>{shown === '' ? '(none)' : unitLabel(shown)}</option>}
    {choices.map(u => <option key={u} value={u}>{u}</option>)}</select>;
}
