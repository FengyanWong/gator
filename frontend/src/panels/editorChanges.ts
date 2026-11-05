// Saved-row lookups and shared wording for tooltips and the unsaved-changes dialog.
import type { EditorRow, SavedRowChange, UnsavedSection } from '../contracts';

/** Index added IDs and unsaved followers once per draw; keep every follower row, including duplicate IDs. */
export function indexUnsavedRows(rows: EditorRow[], keyField: string, unsaved: UnsavedSection | null | undefined,
  leaderOf: (row: EditorRow) => string | null) {
  const added = new Set(unsaved?.added ?? []);
  const isNew = (row: EditorRow) => added.has(String(row[keyField] ?? ''));
  const changeOf = (row: EditorRow): SavedRowChange | null => unsaved?.changed?.[String(row[keyField] ?? '')] ?? null;
  const unsavedTies = new Map<unknown, number>();
  for (const row of rows) {
    if (!isNew(row) && !changeOf(row)) continue;
    const leader = leaderOf(row);
    if (leader) unsavedTies.set(leader, (unsavedTies.get(leader) ?? 0) + 1);
  }
  return { isNew, changeOf, unsavedTies };
}

export const idList = (ids: string[], limit = 4) => `${ids.slice(0, limit).join(', ')}${ids.length > limit ? ', ...' : ''}`;

/** Both views count the same changes; the dialog also names changed/added rows and shows one more ID. */
export function unsavedSummary(rows: UnsavedSection | null | undefined, detail = false): string | null {
  if (!rows) return null;
  const changed = Object.keys(rows.changed ?? {}), added = rows.added ?? [], removed = rows.removed ?? [];
  const part = (ids: string[], label: string, names = detail) => ids.length
    ? `${ids.length} ${label}${names ? ` (${idList(ids, detail ? 4 : 3)})` : ''}` : '';
  const parts = [part(changed, 'changed'), part(added, 'new'),
    part(removed, `saved row${removed.length === 1 ? '' : 's'} deleted here`, true),
    rows.reordered ? 'rows in another order' : ''].filter(Boolean);
  return parts.length ? parts.join(', ') : null;
}
