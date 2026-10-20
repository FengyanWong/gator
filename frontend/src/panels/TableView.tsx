import { useState } from 'react';
import type { FolderView } from './Folders';

/** A column title of the Tasks, Runs and saved models tables: its key, its words and its tooltip. */
type Head = { key: string; title: string; help: string };

type SortValue = string | number | null | undefined;

/** Arrange one read of a table. The callbacks derive text and sort values from the row: derive each at most once here,
 *  especially the Tasks columns that count and sort a task's runs. Nothing is retained across reads or rows replaced. */
export function arrangeRows<T>(rows: T[], keep: (row: T) => boolean, text: (row: T) => string,
  value: (row: T) => SortValue, words: string[], down: boolean): T[] {
  const shown = rows.filter(row => {
    if (!keep(row)) return false;
    if (!words.length) return true;
    const written = text(row);
    return words.every(word => written.includes(word));
  });
  // Array.sort never asks for a key with fewer than two rows; keep that lazy behavior.
  if (shown.length < 2) return shown;
  return shown.map(row => ({ row, value: value(row) })).sort((a, b) => {
    const x = a.value, y = b.value;
    if (x == null || x === '' || y == null || y === '') return (x == null || x === '' ? 1 : 0) - (y == null || y === '' ? 1 : 0);
    return (typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y))) * (down ? -1 : 1);
  }).map(entry => entry.row);
}

/** What the Tasks, Runs and saved models windows share of their tables (record 7.276; each carried its own copy, and the
 *  copies had begun to differ): the filter box, sorting by a column - a press on a column title sorts by it, again the
 *  other way, and rows without a value stay last - and the ticked rows that Move to... acts on. `down`: the direction the
 *  table opens in, and that a newly chosen column starts with (the Tasks window A to Z, the runs and saved models newest
 *  first). */
export function useTableView(key: string, down: boolean) {
  const [filter, setFilter] = useState('');
  const [sort, setSort] = useState({ key, down });
  const [selected, setSelected] = useState<string[]>([]);
  const words = filter.toLowerCase().split(/\s+/).filter(Boolean);
  return {
    filter, setFilter, sort, selected, setSelected,
    sortBy: (column: string) => setSort(s => ({ key: column, down: s.key === column ? !s.down : down })),
    select: (id: string, checked: boolean) => setSelected(ids => checked ? [...ids.filter(k => k !== id), id] : ids.filter(k => k !== id)),
    /** Moves the ticked rows into folder `id`; the ticks go once they are moved. */
    move: async (folders: FolderView, id: string) => { if (await folders.move(selected, id)) setSelected([]); },
    /** The rows `keep` keeps and in whose `text` (lower case) every word of the filter stands, sorted by `value`. */
    arrange: <T,>(rows: T[], keep: (row: T) => boolean, text: (row: T) => string, value: (row: T) => SortValue): T[] =>
      arrangeRows(rows, keep, text, value, words, sort.down),
  };
}
export type TableView = ReturnType<typeof useTableView>;

/** The header row: the box that ticks every row shown (half ticked while only some are), the column titles that sort,
 *  and the empty title over the Details buttons. `what`: the rows' name in the box's label ("runs"). */
export function TableHead<T>({ view, columns, shown, id, what, disabled }: {
  view: TableView; columns: Head[]; shown: T[]; id: (row: T) => string; what: string; disabled: boolean }) {
  const selected = new Set(view.selected);
  const every = shown.every(r => selected.has(id(r)));
  return (<thead><tr>
    <th className="task-select"><input type="checkbox" aria-label={`Select all shown ${what}`} disabled={disabled || !shown.length}
      checked={shown.length > 0 && every} ref={input => { if (input) input.indeterminate = view.selected.length > 0 && !every; }}
      onChange={e => view.setSelected(e.target.checked ? shown.map(id) : [])} /></th>
    {columns.map(c => <th key={c.key} className="sortable" title={`${c.help} Press to sort.`}
      aria-sort={view.sort.key === c.key ? (view.sort.down ? 'descending' : 'ascending') : undefined} onClick={() => view.sortBy(c.key)}>
      {c.title}{view.sort.key === c.key && <span className="sort-mark">{view.sort.down ? ' ▼' : ' ▲'}</span>}</th>)}
    <th className="plain"></th></tr></thead>);
}
