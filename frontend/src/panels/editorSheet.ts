// Pure spreadsheet edits. The view applies each returned patch map as one Undo step.
import type { ConfigRow, EditorColumn, EditorRow, EditorSection } from '../contracts';
import { convert, quantity, readQuantity } from '../units.ts';
import { exact, QUANTITY, readNumber } from './editorRules.ts';

export interface SheetData {
  tab: EditorSection;
  rows: EditorRow[];
  visible: EditorColumn[];
  keyField: string;
}
export interface CellRules {
  blocked: (row: EditorRow, column: EditorColumn) => boolean;
  unitOf: (row: EditorRow) => string | null;
}
export interface SheetEdit {
  changes: Map<number, ConfigRow>;
  note: { text: string; warn: boolean };
}
export const shortText = (value: unknown) => { const text = exact(value); return !text ? '(empty)' : text.length > 40 ? `${text.slice(0, 40)}...` : text; };

/** Fill editable targets, converting quantities to each target's stored unit. */
export function fillCells(sheet: SheetData, rules: CellRules, column: EditorColumn, from: number, targets: number[]): SheetEdit {
  const { tab, rows, keyField } = sheet;
  const value = rows[from][column.name] === undefined ? column.default : rows[from][column.name];
  const changes = new Map<number, ConfigRow>();
  let kept = 0, other = 0;
  for (const target of targets) {
    if (rules.blocked(rows[target], column)) { kept += 1; continue; }
    // a quantity goes in the unit the target row stores (record 7.208: 600 nm into a row in m is 6e-7); another quantity is kept
    let filled = value;
    if (typeof value === 'number' && QUANTITY[tab]?.includes(column.name) && (rows[target].unit ?? '') !== (rows[from].unit ?? '')) {
      filled = convert(value, rows[from].unit, rows[target].unit);
      if (filled === null) { other += 1; continue; }
    }
    if (exact(rows[target][column.name] === undefined ? column.default : rows[target][column.name]) !== exact(filled))
      changes.set(target, { [column.name]: filled != null && typeof filled === 'object' ? JSON.parse(JSON.stringify(filled)) : filled });
  }
  const what = `${column.label ?? column.name} = ${typeof value === 'number' && QUANTITY[tab]?.includes(column.name)
    ? quantity(value, rows[from].unit) : shortText(value)} of ${rows[from][keyField]}`;
  return { changes, note: { text: [changes.size ? `Filled ${changes.size} cell${changes.size === 1 ? '' : 's'} with ${what} (one Undo step).`
    : targets.length > kept ? `Nothing to fill: the cell${targets.length - kept === 1 ? ' holds' : 's hold'} ${what} already.` : 'Nothing filled.',
    kept ? `${kept} cell${kept === 1 ? ' that follows' : 's that follow'} another field kept.` : '',
    other ? `${other} cell${other === 1 ? '' : 's'} of another quantity kept.` : ''].filter(Boolean).join(' '), warn: other > 0 } };
}

/** An absent value leaves a cell alone; null clears it. */
export function readPastedCell(tab: EditorSection, column: EditorColumn, raw: string, row: EditorRow,
  unitOf: CellRules['unitOf']): { value?: unknown; problem?: string; unit?: string } {
  const text = raw.trim();
  if (column.name === 'nominal_only') return /^nominal/i.test(text) ? { value: true } : /^all/i.test(text) ? { value: false }
    : { problem: `"${text}" in ${column.label ?? column.name}` };
  if (column.type === 'boolean') return /^(true|yes|on|1|x|✓)$/i.test(text) ? { value: true } : /^(false|no|off|0|)$/i.test(text) ? { value: false }
    : { problem: `"${text}" in ${column.label ?? column.name}` };
  if (column.name === 'constraint' && tab === 'targets') {
    const limit = ({ '>=': '>=', '≥': '>=', '<=': '<=', '≤': '<=', interval: 'interval' } as Record<string, string>)[text.toLowerCase()];
    return limit ? { value: limit } : { problem: `"${text}" in ${column.label ?? column.name}` };
  }
  if (column.options) {
    const option = column.options.find((choice: string) => choice.toLowerCase() === text.toLowerCase());
    return option !== undefined ? { value: option } : text === '' && column.nullable ? { value: null }
      : { problem: `"${text}" in ${column.label ?? column.name}` };
  }
  if ((column.type === 'number' || column.type === 'integer') && QUANTITY[tab]?.includes(column.name)) {
    if (text === '') return column.nullable ? { value: null } : {};
    const unit = unitOf(row), read = readQuantity(text, unit);
    return 'problem' in read ? { problem: `"${text}" in ${column.label ?? column.name}` }
      : { value: read.value, unit: read.unit ?? (unit && unit !== row.unit ? unit : undefined) };
  }
  if (column.type === 'number' || column.type === 'integer') {
    if (text === '') return column.nullable ? { value: null } : {};
    const parsed = readNumber(text);
    return parsed !== undefined ? { value: parsed } : { problem: `"${text}" in ${column.label ?? column.name}` };
  }
  if (column.type === 'array' || column.type === 'object') {
    if (text === '') return { value: null };
    try { return { value: JSON.parse(text) }; } catch { return { problem: `"${text}" in ${column.label ?? column.name}` }; }
  }
  return { value: raw === '' && column.nullable ? null : raw };
}

/** Paste through visible rows and columns, preserving locked cells and skipping a copied header. */
export function pasteCells(sheet: SheetData, rules: CellRules, text: string, shown: number[],
  origin: { row: number; column: number }): SheetEdit {
  const { tab, rows, visible } = sheet, { row: first, column: firstColumn } = origin;
  const changes = new Map<number, ConfigRow>(), problems: string[] = [];
  let cells = 0, kept = 0, beyond = 0, lines = text.split(/\r?\n/).map(line => line.split('\t'));
  // A first line that names the columns it lands on - the header of a copied block (record 7.184) - is skipped.
  const names = (column: EditorColumn | undefined, value: string) => !!column
    && [column.name, column.label].some(name => name && name.toLowerCase() === value.trim().replace(/\s*\*$/, '').toLowerCase());
  const header = lines.length > 1 && lines[0].every((value, across) => names(visible[firstColumn + across], value));
  if (header) lines = lines.slice(1);
  lines.forEach((values, down) => {
    const index = shown[first + down];
    if (index === undefined) { beyond += 1; return; }
    const row = rows[index];
    values.forEach((raw, across) => {
      const column = visible[firstColumn + across];
      if (!column) return;
      if (rules.blocked(row, column)) { kept += 1; return; }
      const read = readPastedCell(tab, column, raw, row, rules.unitOf);
      if (read.problem) problems.push(read.problem);
      else if ('value' in read) {
        changes.set(index, { ...(changes.get(index) ?? {}), [column.name]: read.value, ...(read.unit ? { unit: read.unit } : {}) });
        cells += 1;
      }
    });
  });
  const said = [cells ? `Pasted ${cells} cell${cells === 1 ? '' : 's'} into ${changes.size} row${changes.size === 1 ? '' : 's'} (one Undo step).`
    : 'Nothing pasted.',
    header ? 'The header line was skipped.' : '',
    problems.length ? `Not read, left as they were: ${problems.slice(0, 4).join(', ')}${problems.length > 4 ? ` and ${problems.length - 4} more` : ''}.`
      : '',
    kept ? `${kept} cell${kept === 1 ? ' that follows' : 's that follow'} another field kept.` : '',   // as fill down says it (branch record SIF-50)
    beyond ? `${beyond} line${beyond === 1 ? '' : 's'} below the last row left out: Add rows first.` : ''].filter(Boolean).join(' ');
  return { changes, note: { text: said, warn: problems.length + beyond > 0 } };
}
