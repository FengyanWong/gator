import { Icon } from './Icons';
import { useMemo, useRef, useState } from 'react';
import { api, Json, num, saveJson } from '../api';
import { migrateConfig } from '../store';
import { Typed } from './Typed';
import { MatchedDevices } from './MatchedDevices';

export type Section = 'parameters' | 'targets' | 'measurements';
const TITLES: Record<Section, string> = { parameters: 'Parameters', measurements: 'Probes', targets: 'Specs' };   // key order = tab order
/** The sections a whole-configuration import replaces beside the three tables, as the confirmation names them. */
const IMPORTED_SECTIONS: Record<string, string> = { project: 'project name', circuit: 'circuit source', run: 'run settings',
  output: 'output settings', research: 'research labels' };

/** The scale offered while nobody has typed one, or null when the row gives nothing to size it by yet: then the scale stays
 * empty and the backend sizes it from the limits (the size of the threshold, else 1), instead of freezing a bare 1 W or
 * 1 Hz into a row whose limits are typed afterwards (record 7.112). */
function suggestedScale(row: Json): number | null {
  if (row.unit === 'dB') return 3;
  if (row.unit === 'deg') return 10;
  if (row.constraint === 'target' && row.tolerance > 0) return row.tolerance;
  if (row.constraint === 'interval' && row.lower != null && row.upper != null && row.upper > row.lower) return (row.upper - row.lower) / 2;
  return Math.max(...[row.lower, row.upper, row.target].filter(v => typeof v === 'number').map(Math.abs), 0) || null;
}
const SCALE_FIELDS = ['unit', 'lower', 'upper', 'target', 'tolerance', 'constraint'];
/** The scale after an edit of a field it depends on: an empty scale, or one still equal to the row's suggestion before the
 * edit, follows the edit; a scale the user typed stays. */
function followScale(before: Json, after: Json): number | null {
  const untouched = before.normalization_scale == null || before.normalization_scale === suggestedScale(before);
  return untouched ? suggestedScale(after) : after.normalization_scale;
}

const MORE_KEY = 'gator-workbench-editor-more-columns';

function Cell({ column, value, onChange }: { column: Json; value: Json; onChange: (v: Json) => void }) {
  const title = column.guidance;
  if (column.name === 'nominal_only') return <select aria-label="Judged at" title={title}
    value={value ? 'nominal' : 'all'} onChange={e => onChange(e.target.value === 'nominal')}>
    <option value="all">All planned conditions</option><option value="nominal">Nominal only</option></select>;
  if (column.name === 'direction_after_feasible') return <select aria-label="Objective" title={title}
    value={value ?? 'none'} onChange={e => onChange(e.target.value)}>
    <option value="none">None</option><option value="minimize">Minimize</option><option value="maximize">Maximize</option></select>;
  // A column the circuit read fills (initial_value): shown, never typed - a typed value could only differ from the circuit.
  if (column.readonly) return <input title={title} className="readonly" readOnly value={value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value)} />;
  if (column.options) {
    return <select title={title} value={value ?? ''} onChange={e => onChange(e.target.value === '' && column.nullable ? null : e.target.value)}>
      {column.nullable && <option value="">(none)</option>}{column.options.map((o: string) => <option key={o} value={o}>{o}</option>)}</select>;
  }
  if (column.type === 'boolean') return <input type="checkbox" title={title} checked={!!value} onChange={e => onChange(e.target.checked)} />;
  if (column.type === 'number' || column.type === 'integer') {
    return <Typed title={title} className="numeric" placeholder={column.nullable ? '-' : ''} value={value} onChange={onChange}
      format={v => v == null ? '' : String(v)}
      parse={t => { const s = t.trim(), n = Number(s); return s === '' ? { value: column.nullable ? null : 0 } : Number.isFinite(n) ? { value: n } : undefined; }} />;
  }
  if (column.type === 'array' || column.type === 'object') {
    return <Typed title={title + ' (JSON)'} value={value} onChange={onChange} format={v => v == null ? '' : JSON.stringify(v)}
      parse={t => { if (t.trim() === '') return { value: null }; try { return { value: JSON.parse(t) }; } catch { return undefined; } }} />;
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
  // "More columns" shows the columns most rows leave at their default (Specs: soft_weight, active, basis; the Probes' two,
  // conditions and aggregation, were retired in record 7.105). They exist whether shown or not: Add fills them, the agent
  // may set them, a task file keeps them.
  const [more, setMore] = useState<boolean>(() => { try { return localStorage.getItem(MORE_KEY) === 'shown'; } catch { return false; } });
  const showMore = (now: boolean) => { setMore(now); try { localStorage.setItem(MORE_KEY, now ? 'shown' : 'hidden'); } catch { /* no storage: the choice lasts for this page */ } };
  // `rows`: an import of one table's rows - Apply writes that table alone; null = a whole configuration, which replaces all.
  const [pending, setPending] = useState<{ next: Json; diff: Json[]; others: string[]; rows: { section: Section; value: Json[] } | null } | null>(null);
  const [matched, setMatched] = useState(false);            // the Matched devices box of the Parameters tab (record 7.103)
  const [error, setError] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);
  const columns: Json[] = schema.editors[tab].map((c: Json) => tab !== 'targets' ? c : c.name === 'nominal_only'
    ? { ...c, label: 'Judged at' } : c.name === 'direction_after_feasible' ? { ...c, label: 'Objective' }
    : c.name === 'missing_is_failure' ? { ...c, label: 'Missing value = failed' } : c.name === 'margin_sides' ? { ...c, label: 'Margin sides' }
    : c.name === 'normalization_scale' ? { ...c, guidance: 'Threshold distance divided by this positive scale, then shaped by the selected capped or compressed reward. Empty uses the threshold size. Feasibility uses the actual bounds, not the reward.' } : c);
  const hidden = columns.filter(c => c.advanced);
  const visible = columns.filter(c => more || !c.advanced);
  const keyField: string = schema.section_keys[tab];
  const rows: Json[] = config[tab] ?? [];
  const issues = useMemo(() => (validation?.issues ?? []).filter((i: Json) => i.path.startsWith(tab)), [validation, tab]);
  const rowIssues = (index: number) => issues.filter((i: Json) => i.path.startsWith(`${tab}[${index}]`));

  const update = (index: number, name: string, value: Json) =>
    setConfig((c: Json) => ({ ...c, [tab]: c[tab].map((r: Json, i: number) => i === index ? (() => {
      const row = { ...r, [name]: value };
      if (tab === 'targets' && SCALE_FIELDS.includes(name)) row.normalization_scale = followScale(r, row);
      return row;
    })() : r) }));
  const add = () => {
    const row: Json = {};
    // A required field without a default comes as `default: null` from the schema: that means "none", not null - a new
    // Specs row used to get constraint = null and normalization_scale = null, and the whole configuration failed validation.
    for (const c of columns) row[c.name] = c.default !== undefined && (c.default !== null || c.nullable) ? c.default
      : c.nullable ? null : c.options ? c.options[0] : c.type === 'number' ? 1 : c.type === 'boolean' ? false : '';
    // A free ID: `rows.length + 1` repeated an existing one after a deletion, and "Delete selected" then removed both rows.
    const used = new Set(rows.map(r => r[keyField]));
    let n = rows.length + 1;
    while (used.has(`${tab.slice(0, -1)}_${n}`)) n += 1;
    row[keyField] = `${tab.slice(0, -1)}_${n}`;
    // A new spec starts as the simplest equation over the probes: the first probe, in its unit.
    const first = config.measurements?.[0];
    if (tab === 'targets' && first && !row.equation) Object.assign(row, { equation: first.measurement_id ?? '', unit: row.unit || first.unit || '' });
    if (tab === 'targets' && row.normalization_scale == null) row.normalization_scale = suggestedScale(row);
    setConfig((c: Json) => ({ ...c, [tab]: [...(c[tab] ?? []), row] }));
  };
  const remove = () => { setConfig((c: Json) => ({ ...c, [tab]: c[tab].filter((r: Json) => !selected[r[keyField]]) })); setSelected({}); };

  // JSON import goes through a DIFF CONFIRMATION before it replaces anything. The backend's diff covers the three tables;
  // a whole configuration also replaces the other sections, and the confirmation names each one that changes (it used to
  // show "0 changed rows" while it replaced the run settings - review of 2026-09-29). Rows for one table write only that
  // table on Apply: the rest of the configuration as it is THEN, so an edit made while the box was open stays (it used to
  // be put back to the configuration of the moment of the import).
  const importJson = async (f: File) => {
    setError(null);
    try {
      const incoming = JSON.parse(await f.text());
      const rowsIn = incoming?.[tab] ?? (Array.isArray(incoming) ? incoming : null);
      if (!incoming?.schema_version && !Array.isArray(rowsIn))
        throw new Error(`the file is neither a whole configuration nor ${TITLES[tab]} rows (a list, or an object with "${tab}")`);
      const next = migrateConfig(incoming.schema_version ? incoming : { ...config, [tab]: rowsIn });
      const { diff } = await api.diff(config, next);
      const others = Object.keys(IMPORTED_SECTIONS).filter(k => JSON.stringify(config[k] ?? null) !== JSON.stringify(next[k] ?? null));
      setPending({ next, diff, others, rows: incoming.schema_version ? null : { section: tab, value: next[tab] } });
    } catch (e: any) { setError(`Import failed: ${e.message}`); }
  };
  const applyImport = (p: NonNullable<typeof pending>) => {
    const { rows } = p;
    setConfig(rows ? (c: Json) => ({ ...c, [rows.section]: rows.value }) : p.next);
    setPending(null);
  };
  const selection = rows.filter(r => selected[r[keyField]]).map(r => ({ section: tab, key: r[keyField], fields: [] as string[] }));

  return (
    <section className="panel editors">
      {/* Another tab closes the Matched devices box: kept "open", coming back to Parameters mounted it again, and mounting
          is its press - it asked the backend with nobody pressing anything, and a reviewed diff was gone. */}
      <div className="tabs">{(Object.keys(TITLES) as Section[]).map(s => <button key={s} className={s === tab ? 'active' : ''} onClick={() => { if (s !== tab) setMatched(false); setTab(s); setSelected({}); }}>{TITLES[s]} ({(config[s] ?? []).length})</button>)}
        <span className="tab-actions" ref={taskSlot} /></div>
      <div className="toolbar">
        <button onClick={add} title="Add: A new row at the end, with a free ID."><Icon name="add" label="Add" /></button>
        <button disabled={!selection.length} onClick={remove} title="Delete selected: The rows whose box is ticked. Undo takes them back."><Icon name="delete" label="Delete selected" /></button>
        <button disabled={!canUndo} onClick={undo} title="Undo: The last change to the configuration, from any panel - rows, run and output settings, an applied proposal."><Icon name="undo" label="Undo" /></button>
        <button disabled={!canRedo} onClick={redo} title="Redo: The change Undo took back."><Icon name="redo" label="Redo" /></button>
        <button onClick={() => saveJson(`${config.project.task_name}.config.json`, config)} title="Export JSON: The whole configuration - the three tables, the circuit, run and output settings, research labels - as one JSON file, downloaded."><Icon name="export" label="Export JSON" /></button>
        <button onClick={() => file.current?.click()} title="Import JSON...: Read a JSON file - a whole configuration, or rows for this tab. You see everything it changes before anything is replaced."><Icon name="import" label="Import JSON..." /></button>
        <input ref={file} type="file" accept="application/json" hidden onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; if (f) importJson(f); }} />
        <span className="spacer" />
        {hidden.length > 0 && <button className="text" onClick={() => showMore(!more)} title={(more ? 'Fewer columns: hide ' : 'More columns: also show ') + hidden.map(c => c.name).join(', ') + '. They keep their values either way.'}>{more ? 'Fewer columns' : `More columns (${hidden.length})`}</button>}
        {tab === 'parameters' && <button className="text" disabled={matched} onClick={() => setMatched(true)} title="Matched devices...: Reads the circuit for differential pairs, current-mirror loads, matched loads and cascodes and suggests tying their sizes. You review a diff; nothing is applied automatically.">Matched devices...</button>}
        <button onClick={() => onAgent(tab, [])} title="Draft with agent...: Opens the Agent tab set to draft this tab's rows. Nothing is sent until you write what you need there and press Enter; its proposal is a diff you approve."><Icon name="agent-draft" label="Draft with agent..." /></button>
        <button disabled={!selection.length} onClick={() => onAgent('modify_fields', selection)} title="Modify selected with agent...: Ask the agent for a change to the ticked rows. You review a diff; nothing is applied automatically."><Icon name="agent-modify" label="Modify selected with agent..." /></button>
      </div>
      <div className="task-notes" ref={taskNotes} />
      {tab === 'parameters' && matched && <MatchedDevices config={config} setConfig={setConfig} onClose={() => setMatched(false)} />}
      {tab === 'parameters' && <p className="fact">Independent action variables: <b>{validation?.facts?.independent_action_variables ?? '?'}</b> of {rows.length} rows.
        The initial value is the one read from the circuit. Equal initial values do not imply a binding. The policy's proposed action and the executed (projected/quantized) value are both recorded.</p>}
      {tab === 'targets' && <p className="fact spec-probes">Each spec judges its <b>equation</b>, written with Probe IDs, numbers, + - * / ** and brackets
        (e.g. m_supply_power_w / m_osc_frequency_hz). Probes: {(config.measurements ?? []).map((m: Json) => m.measurement_id).filter(Boolean).join(', ') || 'none yet - fill in the Probes tab first'}.
        An empty normalization_scale divides the violation by the size of the threshold.</p>}
      {tab === 'targets' && rows.some(r => r.constraint === 'interval' && r.lower === 0) && <p className="hint zero-floor-hint">The margin also measures the distance to 0. If 0 is only a physical floor, choose Margin sides: upper.</p>}
      {error && <p className="error">{error}</p>}
      {pending && <div className="confirm"><h4>Confirm import: {pending.diff.length} changed row{pending.diff.length === 1 ? '' : 's'}{pending.others.length
        ? `, and it replaces the ${pending.others.map(k => IMPORTED_SECTIONS[k]).join(', ')}` : ''}</h4>
        {(pending.diff.length > 0 || !pending.others.length) && <DiffView diff={pending.diff} />}
        <button onClick={() => applyImport(pending)}>Apply</button><button onClick={() => setPending(null)}>Cancel</button></div>}
      <div className="scroll">
        <table className="grid editor">
          <thead><tr><th></th>{visible.map(c => <th key={c.name} data-field={c.name} title={c.guidance} onClick={() => setHelp(c)}>{c.label ?? c.name}{c.required ? ' *' : ''}</th>)}<th>Issues</th></tr></thead>
          <tbody>{rows.map((row, index) => {
            const found = rowIssues(index);
            return <tr key={index} className={found.some((i: Json) => i.level === 'error' || i.level === 'blocker') ? 'has-error' : ''}>
              <td><input type="checkbox" checked={!!selected[row[keyField]]} onChange={e => setSelected(s => ({ ...s, [row[keyField]]: e.target.checked }))} /></td>
              {/* A field the row does not STATE is shown with the value the backend uses for it (hard = on, tolerance = 0 ...): a
                  starter row's absent `hard` used to look unchecked although the target is hard. A box the user cleared is null,
                  not absent, and stays empty. */}
              {visible.map(c => <td key={c.name}><Cell column={c} value={row[c.name] === undefined ? c.default : row[c.name]} onChange={v => update(index, c.name, v)} /></td>)}
              <td className="issues">{found.map((i: Json, n: number) => <div key={n} className={`issue ${i.level}`} title={i.message}>{i.level}: {i.code}</div>)}</td>
            </tr>; })}</tbody>
        </table>
      </div>
      {help && <p className="guidance" onClick={() => setHelp(null)}><b>{help.name}</b> ({help.type}{help.options ? ': ' + help.options.join(' | ') : ''}) - {help.guidance}</p>}
      {issues.filter((i: Json) => !/\[\d+\]/.test(i.path)).map((i: Json, n: number) => <p key={n} className={`issue ${i.level}`}>{i.level}: {i.message}</p>)}
    </section>
  );
}
