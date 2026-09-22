import { useMemo, useRef, useState } from 'react';
import { api, Json, num, saveJson } from '../api';
import { migrateConfig } from '../store';

export type Section = 'parameters' | 'targets' | 'measurements';
const TITLES: Record<Section, string> = { parameters: 'Parameters', measurements: 'Probes', targets: 'Specs' };   // key order = tab order

function Cell({ column, value, onChange }: { column: Json; value: Json; onChange: (v: Json) => void }) {
  const title = column.guidance;
  if (column.options) {
    return <select title={title} value={value ?? ''} onChange={e => onChange(e.target.value === '' && column.nullable ? null : e.target.value)}>
      {column.nullable && <option value="">(none)</option>}{column.options.map((o: string) => <option key={o} value={o}>{o}</option>)}</select>;
  }
  if (column.type === 'boolean') return <input type="checkbox" title={title} checked={!!value} onChange={e => onChange(e.target.checked)} />;
  if (column.type === 'number' || column.type === 'integer') {
    return <input title={title} className="numeric" value={value ?? ''} placeholder={column.nullable ? '-' : ''}
      onChange={e => { const t = e.target.value.trim(); onChange(t === '' ? (column.nullable ? null : 0) : Number.isFinite(Number(t)) ? Number(t) : value); }} />;
  }
  if (column.type === 'array' || column.type === 'object') {
    return <input title={title + ' (JSON)'} value={value == null ? '' : JSON.stringify(value)}
      onChange={e => { try { onChange(e.target.value.trim() === '' ? null : JSON.parse(e.target.value)); } catch { /* keep typing */ } }} />;
  }
  return <input title={title} value={value ?? ''} onChange={e => onChange(e.target.value === '' && column.nullable ? null : e.target.value)} />;
}

export function DiffView({ diff }: { diff: Json[] }) {
  if (!diff.length) return <p className="hint">No differences.</p>;
  return <table className="grid small"><thead><tr><th>Section</th><th>Row</th><th>Change</th><th>Field</th><th>Before</th><th>After</th></tr></thead>
    <tbody>{diff.flatMap((d: Json) => d.fields.map((f: Json, i: number) => (
      <tr key={`${d.section}/${d.key}/${f.field}`} className={`diff-${d.change}`}>
        {i === 0 && <><td rowSpan={d.fields.length}>{d.section}</td><td rowSpan={d.fields.length}>{d.key}</td><td rowSpan={d.fields.length}>{d.change}</td></>}
        <td>{f.field}</td><td>{num(typeof f.before === 'object' ? JSON.stringify(f.before) : f.before)}</td><td>{num(typeof f.after === 'object' ? JSON.stringify(f.after) : f.after)}</td>
      </tr>)))}</tbody></table>;
}

/** `taskSlot` / `taskNotes`: where the circuit panel puts "Save task" (right end of the tab line) and its messages (under
 *  the toolbar) - the save sits with the rows it stores (user request 2026-09-22). No "Save" button of its own any more:
 *  the configuration is kept in this browser by itself (store.ts, 0.8 s after each change), and a second "Save" next to
 *  "Save task" only confused. */
export function Editors({ schema, config, setConfig, undo, redo, canUndo, canRedo, validation, onAgent, taskSlot, taskNotes }:
  { schema: Json; config: Json; setConfig: (c: Json | ((c: Json) => Json)) => void; undo: () => void; redo: () => void; canUndo: boolean; canRedo: boolean;
    validation: Json; onAgent: (kind: string, selection: Json[]) => void;
    taskSlot: (element: HTMLElement | null) => void; taskNotes: (element: HTMLElement | null) => void }) {
  const [tab, setTab] = useState<Section>('parameters');
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [help, setHelp] = useState<Json>(null);
  const [pending, setPending] = useState<{ next: Json; diff: Json[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const columns: Json[] = schema.editors[tab];
  const keyField: string = schema.section_keys[tab];
  const rows: Json[] = config[tab] ?? [];
  const issues = useMemo(() => (validation?.issues ?? []).filter((i: Json) => i.path.startsWith(tab)), [validation, tab]);
  const rowIssues = (index: number) => issues.filter((i: Json) => i.path.startsWith(`${tab}[${index}]`));

  const update = (index: number, name: string, value: Json) =>
    setConfig((c: Json) => ({ ...c, [tab]: c[tab].map((r: Json, i: number) => i === index ? { ...r, [name]: value } : r) }));
  const add = () => {
    const row: Json = {};
    // A required field without a default comes as `default: null` from the schema: that means "none", not null - a new
    // Specs row used to get constraint = null and normalization_scale = null, and the whole configuration failed validation.
    for (const c of columns) row[c.name] = c.default !== undefined && (c.default !== null || c.nullable) ? c.default
      : c.nullable ? null : c.options ? c.options[0] : c.type === 'number' ? 1 : c.type === 'boolean' ? false : '';
    row[keyField] = `${tab.slice(0, -1)}_${rows.length + 1}`;
    // A new spec starts as the simplest equation over the probes: the first probe, in its unit.
    const first = config.measurements?.[0];
    if (tab === 'targets' && first && !row.equation) Object.assign(row, { equation: first.measurement_id ?? '', unit: row.unit || first.unit || '' });
    setConfig((c: Json) => ({ ...c, [tab]: [...(c[tab] ?? []), row] }));
  };
  const remove = () => { setConfig((c: Json) => ({ ...c, [tab]: c[tab].filter((r: Json) => !selected[r[keyField]]) })); setSelected({}); };

  // JSON import goes through a DIFF CONFIRMATION before it replaces anything.
  const importJson = async (f: File) => {
    setError(null);
    try {
      const incoming = JSON.parse(await f.text());
      const next = migrateConfig(incoming.schema_version ? incoming : { ...config, [tab]: incoming[tab] ?? incoming });
      const { diff } = await api.diff(config, next);
      setPending({ next, diff });
    } catch (e: any) { setError(`Import failed: ${e.message}`); }
  };
  const selection = rows.filter(r => selected[r[keyField]]).map(r => ({ section: tab, key: r[keyField], fields: [] as string[] }));

  return (
    <section className="panel editors">
      <div className="tabs">{(Object.keys(TITLES) as Section[]).map(s => <button key={s} className={s === tab ? 'active' : ''} onClick={() => { setTab(s); setSelected({}); }}>{TITLES[s]} ({(config[s] ?? []).length})</button>)}
        <span className="tab-actions" ref={taskSlot} /></div>
      <div className="toolbar">
        <button onClick={add}>Add</button>
        <button disabled={!selection.length} onClick={remove}>Delete selected</button>
        <button disabled={!canUndo} onClick={undo}>Undo</button>
        <button disabled={!canRedo} onClick={redo}>Redo</button>
        <button onClick={() => saveJson(`${config.project.task_name}.config.json`, config)}>Export JSON</button>
        <button onClick={() => file.current?.click()}>Import JSON...</button>
        <input ref={file} type="file" accept="application/json" hidden onChange={e => e.target.files?.[0] && importJson(e.target.files[0])} />
        <span className="spacer" />
        <button onClick={() => onAgent(tab, [])} title="Ask the agent for a proposal for this tab. You review a diff; nothing is applied automatically.">Draft with agent...</button>
        <button disabled={!selection.length} onClick={() => onAgent('modify_fields', selection)}>Modify selected with agent...</button>
      </div>
      <div className="task-notes" ref={taskNotes} />
      {tab === 'parameters' && <p className="fact">Independent action variables: <b>{validation?.facts?.independent_action_variables ?? '?'}</b> of {rows.length} rows.
        Equal initial values do not imply a binding. The policy's proposed action and the executed (projected/quantized) value are both recorded.</p>}
      {tab === 'targets' && <p className="fact spec-probes">Each spec judges its <b>equation</b>, written with Probe IDs, numbers, + - * / ** and brackets
        (e.g. m_supply_power_w / m_osc_frequency_hz). Probes: {(config.measurements ?? []).map((m: Json) => m.measurement_id).filter(Boolean).join(', ') || 'none yet - fill in the Probes tab first'}.</p>}
      {error && <p className="error">{error}</p>}
      {pending && <div className="confirm"><h4>Confirm import: {pending.diff.length} changed rows</h4><DiffView diff={pending.diff} />
        <button onClick={() => { setConfig(pending.next); setPending(null); }}>Apply</button><button onClick={() => setPending(null)}>Cancel</button></div>}
      <div className="scroll">
        <table className="grid editor">
          <thead><tr><th></th>{columns.map(c => <th key={c.name} title={c.guidance} onClick={() => setHelp(c)}>{c.name}{c.required ? ' *' : ''}</th>)}<th>Issues</th></tr></thead>
          <tbody>{rows.map((row, index) => {
            const found = rowIssues(index);
            return <tr key={index} className={found.some((i: Json) => i.level === 'error' || i.level === 'blocker') ? 'has-error' : ''}>
              <td><input type="checkbox" checked={!!selected[row[keyField]]} onChange={e => setSelected(s => ({ ...s, [row[keyField]]: e.target.checked }))} /></td>
              {/* A field the row does not STATE is shown with the value the backend uses for it (hard = on, tolerance = 0 ...): a
                  starter row's absent `hard` used to look unchecked although the target is hard. A box the user cleared is null,
                  not absent, and stays empty. */}
              {columns.map(c => <td key={c.name}><Cell column={c} value={row[c.name] === undefined ? c.default : row[c.name]} onChange={v => update(index, c.name, v)} /></td>)}
              <td className="issues">{found.map((i: Json, n: number) => <div key={n} className={`issue ${i.level}`} title={i.message}>{i.level}: {i.code}</div>)}</td>
            </tr>; })}</tbody>
        </table>
      </div>
      {help && <p className="guidance" onClick={() => setHelp(null)}><b>{help.name}</b> ({help.type}{help.options ? ': ' + help.options.join(' | ') : ''}) - {help.guidance}</p>}
      {issues.filter((i: Json) => !/\[\d+\]/.test(i.path)).map((i: Json, n: number) => <p key={n} className={`issue ${i.level}`}>{i.level}: {i.message}</p>)}
    </section>
  );
}
