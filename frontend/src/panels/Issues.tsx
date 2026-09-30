import { useEffect, useState } from 'react';
import type { Json } from '../api';

const BLOCKING = ['error', 'blocker'];

/** `parameters[2].lower` -> the key of that row, which is what the editor tables show (not the index). */
function rowKey(path: string, config: Json, schema: Json): string | null {
  const match = /^(\w+)\[(\d+)\]/.exec(path);
  if (!match) return null;
  const keyField = schema?.section_keys?.[match[1]];
  return keyField ? config?.[match[1]]?.[Number(match[2])]?.[keyField] ?? null : null;
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
  return (<>
    <button className={`issues-button${open ? ' active' : ''}`} aria-expanded={open} aria-controls="blocking-issues"
      title={open ? 'Hide the list' : 'Show every blocking issue'} onClick={() => setOpen(o => !o)}>{blocking.length} blocking issue(s)</button>
    {open && <div id="blocking-issues" className="issue-list" role="region" aria-label="Blocking issues">
      <div className="issue-list-head"><b>{blocking.length} blocking issue(s)</b>
        <span className="hint">Start and the baseline simulation stay disabled until all of them are resolved. The list follows every edit.</span>
        <span className="spacer" /><button onClick={() => setOpen(false)}>Hide</button></div>
      <div className="issue-list-body"><table className="grid small">
        <thead><tr><th title="Order of the validation report">#</th>
          <th title="error: the configuration is inconsistent. blocker: consistent, but the current backend cannot execute it.">Level</th>
          <th title="Stable identifier of the check">Code</th><th title="Field of the configuration, and the key of its row in the editor">Where</th>
          <th title="What is wrong and what resolves it">Message</th></tr></thead>
        <tbody>{blocking.map((issue: Json, n: number) => {
          const key = rowKey(issue.path ?? '', validation.sent ?? config, schema);   // the row of the configuration the report is about (App.tsx `sent`)
          return <tr key={n}><td className="numeric">{n + 1}</td><td className="issue error">{issue.level}</td><td>{issue.code}</td>
            <td><code>{issue.path || '(whole configuration)'}</code>{key && <span className="hint"> row {key}</span>}</td>
            <td>{issue.message}{issue.technical && <details className="more"><summary>Technical details</summary><code>{issue.technical}</code></details>}</td></tr>;
        })}</tbody></table></div>
    </div>}
  </>);
}
