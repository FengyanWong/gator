// The table of what an import changes, row by row and field by field (plan-refactoring C6, out of Editors.tsx; Matched
// devices shows its diff with it too).
import type { Json } from '../api';
import { quantity } from '../units';
import { exact, fieldLabel, QUANTITY, SECTION_TITLES } from './editorRules';

/** A row's change in the page's words (branch record SIF-51: "modified" read as the program wrote it); the row's class keeps
 *  the program's word (diff-added, diff-removed), which the page's colours key on. */
const CHANGE: Record<string, string> = { added: 'new', removed: 'deleted', modified: 'changed' };

/** The table read just before Apply names what the editors show (branch record SIF-51): the tab (Probes, not "measurements"),
 *  the column's header (Tied to, not "binding_group"; the program's names stay in the tooltips), a number with its row's unit
 *  as its cell writes it (1 um, not 0.000001) and "(empty)" where a value is cleared. `unitOf`: the unit of a row in the editors,
 *  by its table and ID; a diff that changes the row's unit itself (an import may) or adds the row carries the unit of each side.
 *  Deleted rows come first, and a field empty on both sides is left out (branch record SIF-132): a file of 20 Specs listed
 *  each new row field by field, "Scale (empty) (empty)" among them, and the 2 rows it deletes after all of them. */
export function DiffView({ diff, unitOf }: { diff: Json[]; unitOf?: (section: string, key: string) => string | null }) {
  if (!diff.length) return <p className="hint">No differences.</p>;
  const empty = (v: Json) => v == null || v === '';
  const value = (d: Json, f: Json, side: 'before' | 'after') => {
    const v = f[side];
    if (empty(v)) return <span className="hint">(empty)</span>;
    if (typeof v !== 'number' || !QUANTITY[d.section]?.includes(f.field)) return exact(v);
    const unit = d.fields.find((g: Json) => g.field === 'unit');
    return quantity(v, unit ? unit[side] : unitOf?.(d.section, d.key));
  };
  // A stable sort keeps the backend's order (by ID) within the deleted rows and the rest; a row whose every field is empty on
  // both sides keeps its first, so it still has its line.
  const rows = [...diff].sort((a: Json, b: Json) => Number(b.change === 'removed') - Number(a.change === 'removed')).map((d: Json) => {
    const kept: Json[] = d.fields.filter((f: Json) => !(empty(f.before) && empty(f.after)));
    return { d, fields: kept.length ? kept : d.fields.slice(0, 1) };
  });
  return <table className="grid small"><thead><tr><th>Section</th><th>Row</th><th>Change</th><th>Field</th><th>Before</th><th>After</th></tr></thead>
    <tbody>{rows.flatMap(({ d, fields }) => fields.map((f: Json, i: number) => (
      <tr key={`${d.section}/${d.key}/${f.field}`} className={`diff-${d.change}`}>
        {i === 0 && <><td rowSpan={fields.length} title={d.section}>{SECTION_TITLES[d.section as keyof typeof SECTION_TITLES] ?? d.section}</td>
          <td rowSpan={fields.length}>{d.key}</td><td rowSpan={fields.length}>{CHANGE[d.change] ?? d.change}</td></>}
        <td title={f.field}>{fieldLabel(d.section, f.field)}</td><td>{value(d, f, 'before')}</td><td>{value(d, f, 'after')}</td>
      </tr>)))}</tbody></table>;
}
