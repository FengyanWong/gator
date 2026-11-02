// Shared wording for saved-row tooltips and the unsaved-changes dialog.
import type { UnsavedSection } from '../contracts';

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
