// The table of what an import changes, row by row and field by field (plan-refactoring C6, out of Editors.tsx; Matched
// devices shows its diff with it too).
import type { Json } from '../api';
import { exact } from './editorRules';

export function DiffView({ diff }: { diff: Json[] }) {
  if (!diff.length) return <p className="hint">No differences.</p>;
  return <table className="grid small"><thead><tr><th>Section</th><th>Row</th><th>Change</th><th>Field</th><th>Before</th><th>After</th></tr></thead>
    <tbody>{diff.flatMap((d: Json) => d.fields.map((f: Json, i: number) => (
      <tr key={`${d.section}/${d.key}/${f.field}`} className={`diff-${d.change}`}>
        {i === 0 && <><td rowSpan={d.fields.length}>{d.section}</td><td rowSpan={d.fields.length}>{d.key}</td><td rowSpan={d.fields.length}>{d.change}</td></>}
        <td>{f.field}</td><td>{exact(f.before)}</td><td>{exact(f.after)}</td>
      </tr>)))}</tbody></table>;
}
