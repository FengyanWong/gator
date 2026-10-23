import { useEffect, useState } from 'react';
import type { Json } from '../api';
import { BLOCKING_ISSUES_ID, BLOCKING_LEVELS } from '../contract';
import { plural } from '../format';
import { columnOf, drawsColumn, fieldLabel, type Section, SECTION_TITLES } from './editorRules';
import { Icon } from './Icons';

const BLOCKING = BLOCKING_LEVELS;

/** An issue's Where pressed in the list (branch record SIF-95): the editors open its tab and go to its row, detail
 *  { section, index, key, field }. The place was text only ("targets[3].lower row inl1"): the user switched tab by hand and
 *  looked for the row among 66, which the Find box could hide. */
export const GO_TO_ISSUE = 'gator-go-to-issue';

/** `parameters[2].lower` -> its table, the row's index in the report, the key of that row - which is what the editor tables
 *  show - and its field; null for a place no row has (the table itself, a row without an ID). The index goes along since the
 *  review of SIF-95: a duplicate ID is reported on its later row, which the key alone found as the first. */
export function rowOf(path: string, config: Json, schema: Json): { section: Section; index: number; key: string; field: string | null } | null {
  const match = /^(\w+)\[(\d+)\](?:\.(\w+))?/.exec(path);
  if (!match) return null;
  const keyField = schema?.section_keys?.[match[1]], index = Number(match[2]);
  const key = keyField ? config?.[match[1]]?.[index]?.[keyField] ?? null : null;
  return key == null || key === '' ? null : { section: match[1] as Section, index, key: String(key), field: match[3] ?? null };
}

/** The cell a Where press chooses, in the tooltip's words (review of SIF-95: "Specs opens with its Unit chosen" chose the Spec
 *  ID): the field's column where its table draws one - one behind More columns too, which the press shows - else the row's ID
 *  (Editors.tsx goes the same way). */
function chosenCell(row: { section: Section; field: string | null }, schema: Json, config: Json): string {
  const name = row.field && columnOf(row.section, row.field);
  const column = name ? (schema?.editors?.[row.section] ?? []).find((c: Json) => c.name === name) : null;
  if (name && column && drawsColumn(row.section, column, config)) return `its ${fieldLabel(row.section, name)} chosen${column.advanced ? ', More columns shown' : ''}`;
  const id = `its ${fieldLabel(row.section, schema?.section_keys?.[row.section] ?? 'ID')} chosen`;
  return row.field ? `${id}, as no column shows its ${fieldLabel(row.section, row.field)}` : id;
}

/** Validation state in the header. Blocking issues are a BUTTON: a press lists every one of them in full. Before,
 *  they were only counted there, and an issue outside the three editor tabs (run, output, research, a rejected
 *  configuration) was shown nowhere. The list follows each validation and stays open while issues are being fixed;
 *  with none left it closes, so a later problem never opens it by itself. */
export function ValidationStatus({ validation, config, schema }: { validation: Json; config: Json; schema: Json }) {
  const [open, setOpen] = useState(false);
  const blocked = !!validation?.blocks_run;
  useEffect(() => { if (!blocked) setOpen(false); }, [blocked]);
  if (!blocked) return <span className="ok">{validation ? 'configuration valid' : 'validating...'}</span>;
  const blocking: Json[] = (validation.issues ?? []).filter((i: Json) => BLOCKING.includes(i.level));
  // "1 blocking issue", "3 blocking issues" - it read "1 blocking issue(s)" (branch record SIF-45).
  const count = plural(blocking.length, 'blocking issue');
  return (<>
    <button className={`issues-button${open ? ' active' : ''}`} aria-expanded={open} aria-controls={BLOCKING_ISSUES_ID}
      title={open ? 'Hide the list' : 'Show every blocking issue'} onClick={() => setOpen(o => !o)}>{count}</button>
    {open && <div id={BLOCKING_ISSUES_ID} className="issue-list" role="region" aria-label="Blocking issues">
      <div className="issue-list-head"><b>{count}</b>
        <span className="hint">Start and Calibration stay disabled until all of them are resolved. The list follows every edit.</span>
        {/* Hide is the close mark at the head's end (branch record SIF-112), as Matched devices' and the refusal line's; the
            header's button, named in its words, shows the list again */}
        <span className="spacer" /><button onClick={() => setOpen(false)}
          title={`Hide: The list folds away; the red "${count}" button in the header shows it again.`}><Icon name="close" label="Hide" /></button></div>
      <div className="issue-list-body"><table className="grid small">
        <thead><tr><th title="Order of the validation report">#</th>
          <th title="error: the configuration is inconsistent. blocker: consistent, but the current backend cannot execute it.">Level</th>
          <th title="Stable identifier of the check">Code</th><th title="Field of the configuration, and the key of its row in the editor: press a row's to go there">Where</th>
          <th title="What is wrong and what resolves it">Message</th></tr></thead>
        <tbody>{blocking.map((issue: Json, n: number) => {
          const row = rowOf(issue.path ?? '', validation.sent ?? config, schema);   // the row of the configuration the report is about (App.tsx `sent`)
          const where = <><code>{issue.path || '(whole configuration)'}</code>{row && <span className="hint"> row {row.key}</span>}</>;
          // A row's place is a button that goes there (branch record SIF-95), in the words it had; the list stays open, a
          // checklist (record 7.12). A run or output field stays text: the editors do not show it.
          return <tr key={n}><td className="numeric">{n + 1}</td><td className="issue error">{issue.level}</td><td>{issue.code}</td>
            <td>{row ? <button type="button" className="item-link issue-go" onClick={() => window.dispatchEvent(new CustomEvent(GO_TO_ISSUE, { detail: row }))}
              title={`Go to ${row.key}: ${SECTION_TITLES[row.section] ?? row.section} opens with ${chosenCell(row, schema, config)}. The list stays open.`}>
              {where}</button> : where}</td>
            <td>{issue.message}{issue.technical && <details className="more"><summary>Technical details</summary><code>{issue.technical}</code></details>}</td></tr>;
        })}</tbody></table></div>
    </div>}
  </>);
}
