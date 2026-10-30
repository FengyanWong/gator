// Row selection and table focus. Pure row edits live in editorSheet.ts.
import { useEffect, useRef, useState, type RefObject } from 'react';
import type { EditorColumn, EditorRow, EditorSection } from '../contracts';

interface SelectionInput {
  rows: EditorRow[];
  keyField: string;
  rowsInView: number[];
  filtered: boolean;
  matchesFind: (row: EditorRow) => boolean;
  tab: EditorSection;
}
/** Keep hidden selections, discard deleted IDs and apply Shift+click over visible rows only. */
export function useRowSelection({ rows, keyField, rowsInView, filtered, matchesFind, tab }: SelectionInput) {
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const lastTicked = useRef<unknown>(null);
  // Ticks of rows that are gone (Delete, Undo, an import) go with them: a new row given a freed ID came already ticked.
  useEffect(() => setSelected(ticks => {
    const ids = new Set(rows.map(row => row[keyField]));
    const kept = Object.fromEntries(Object.entries(ticks).filter(([id, on]) => on && ids.has(id)));
    return Object.keys(kept).length === Object.keys(ticks).length ? ticks : kept;
  }), [rows, keyField]);

  const selection = rows.filter(row => selected[String(row[keyField])] && (!filtered || matchesFind(row)))
    .map(row => ({ section: tab, key: row[keyField], fields: [] as string[] }));
  // A tick box ticks its row; with Shift, every row in view from the box clicked last to this one takes its state, and the
  // header's box ticks or unticks every row in view (branch record SIF-96: deleting 20 rows took 20 ticks). A row that a fold
  // or Find hides keeps its tick.
  const tickRow = (key: unknown, on: boolean, span: boolean) => {
    const keys = rowsInView.map(index => rows[index][keyField]), from = span && lastTicked.current !== null ? keys.indexOf(lastTicked.current) : -1,
      to = keys.indexOf(key);
    const range = from >= 0 && to >= 0 ? keys.slice(Math.min(from, to), Math.max(from, to) + 1) : [key];
    lastTicked.current = key;
    setSelected(ticks => ({ ...ticks, ...Object.fromEntries(range.map(id => [id, on])) }));
  };
  const tickedInView = rowsInView.filter(index => selected[String(rows[index][keyField])]).length;
  const tickAll = (on: boolean) => {
    lastTicked.current = null;
    setSelected(ticks => ({ ...ticks, ...Object.fromEntries(rowsInView.map(index => [rows[index][keyField], on])) }));
  };
  return { selected, setSelected, lastTicked, selection, tickRow, tickAll, tickedInView };
}

interface FocusInput {
  table: RefObject<HTMLTableElement>;
  rows: EditorRow[];
  keyField: string;
  columns: EditorColumn[];
  fixedOf: (row: EditorRow, column: EditorColumn) => string | null;
}
/** Restore focus after adding or deleting a row; keep the existing per-render ordering. */
export function useRowFocus({ table, rows, keyField, columns, fixedOf }: FocusInput) {
  const focusNext = useRef<{ key: unknown } | { index: number } | null>(null);
  const addButton = useRef<HTMLButtonElement>(null);
  // The focus on the render after Add or Delete selected (branch record SIF-96): into the new row's first box that takes typing -
  // its ID, or a Maestro output's Output name, which its ID follows - with the text chosen; after a Delete, which disabled the
  // button pressed and let the focus fall to the page, to the tick box of the row now at that place, or to Add when no row is
  // left in view.
  useEffect(() => {
    const next = focusNext.current;
    focusNext.current = null;
    if (!next || !table.current) return;
    if ('key' in next) {
      const index = rows.findIndex(row => row[keyField] === next.key), idColumn = columns.find(column => column.name === keyField);
      if (index < 0) return;
      const tr = table.current.querySelector(`tbody > tr[data-index="${index}"]`);
      const box = tr?.querySelector<HTMLInputElement>(
        `td[data-field="${idColumn && fixedOf(rows[index], idColumn) ? 'source_name' : keyField}"] input:not(:disabled)`)
        ?? tr?.querySelector<HTMLInputElement>(`td[data-field="${keyField}"] input`);
      if (box) { box.scrollIntoView({ block: 'nearest', inline: 'nearest' }); box.focus(); box.select(); }
      return;
    }
    const shown = [...table.current.querySelectorAll<HTMLElement>('tbody > tr:not([hidden])')];
    const box = (shown.find(tr => Number(tr.dataset.index) >= next.index) ?? shown[shown.length - 1])?.querySelector<HTMLInputElement>('td.sel input');
    if (box) { box.scrollIntoView({ block: 'nearest' }); box.focus(); } else addButton.current?.focus();
  });

  return { focusNext, addButton };
}

/** Move through visible table rows without changing the chosen column. */
export const moveFrom = (box: HTMLElement, step: 1 | -1) => {
  const field = box.closest<HTMLElement>('td[data-field]')?.dataset.field;
  let tr = box.closest('tr') as HTMLTableRowElement | null;
  if (!field || !tr) return false;
  do { tr = (step > 0 ? tr.nextElementSibling : tr.previousElementSibling) as HTMLTableRowElement | null; } while (tr && tr.hidden);
  const next = tr?.querySelector(`td[data-field="${CSS.escape(field)}"]`)?.querySelector('input, select') as HTMLElement | null;
  if (!next) return false;
  next.focus();
  if (next instanceof HTMLInputElement && next.type !== 'checkbox') next.select();
  return true;
};
