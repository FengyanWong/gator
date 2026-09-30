import { Icon } from './Icons';
import { useEffect, useMemo, useRef, useState } from 'react';
import { api, Json, saveJson } from '../api';
import { migrateConfig } from '../store';
import { Typed } from './Typed';
import { MatchedDevices } from './MatchedDevices';

export type Section = 'parameters' | 'targets' | 'measurements';
const TITLES: Record<Section, string> = { parameters: 'Parameters', measurements: 'Probes', targets: 'Specs' };   // key order = tab order
const ROW_TABS = Object.keys(TITLES);
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

/** Specs: the limit and the objective in ONE list. An objective means "once every hard spec passes, the lower (higher) the
 *  better" and works on the limit on its side (minimize an upper limit, maximize a lower one), so a pair that could never
 *  work (>= then lower is better) is not offered. Saved as before: `constraint` + `direction_after_feasible`. */
const LIMIT_CHOICES: [string, string][] = [['>=', 'none'], ['>=', 'maximize'], ['<=', 'none'], ['<=', 'minimize'],
  ['interval', 'none'], ['interval', 'minimize'], ['interval', 'maximize'], ['target', 'none']];
const LIMIT_TEXT: Record<string, string> = { '>=': '≥ lower', '<=': '≤ upper', interval: 'interval', target: 'target ± tolerance' };
const limitLabel = (constraint: string, objective: string) => (LIMIT_TEXT[constraint] ?? String(constraint))
  + (objective === 'minimize' ? ', then lower is better' : objective === 'maximize' ? ', then higher is better' : '');

function LimitSelect({ row, title, onChange }: { row: Json; title: string; onChange: (fields: Json) => void }) {
  const objective = row.direction_after_feasible ?? 'none', current = `${row.constraint}|${objective}`;
  const offered = LIMIT_CHOICES.some(([c, o]) => `${c}|${o}` === current);
  return <select aria-label="Constraint" title={title} value={current} onChange={e => {
      const [constraint, direction_after_feasible] = e.target.value.split('|');
      onChange({ constraint, direction_after_feasible });
    }}>
    {/* a pair this list does not offer (an older row, an import) is shown as it is; validation says what is wrong with it */}
    {!offered && <option value={current}>{limitLabel(row.constraint, objective)}</option>}
    {LIMIT_CHOICES.map(([c, o]) => <option key={`${c}|${o}`} value={`${c}|${o}`}>{limitLabel(c, o)}</option>)}</select>;
}

function Cell({ column, value, onChange }: { column: Json; value: Json; onChange: (v: Json) => void }) {
  const title = column.guidance;
  if (column.name === 'nominal_only') return <select aria-label="Judged at" title={title}
    value={value ? 'nominal' : 'all'} onChange={e => onChange(e.target.value === 'nominal')}>
    <option value="all">All planned conditions</option><option value="nominal">Nominal only</option></select>;
  // A column the circuit read fills (initial_value): shown, never typed - a typed value could only differ from the circuit.
  if (column.readonly) return <input title={title} className="readonly" readOnly value={value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value)} />;
  if (column.options) {
    // A value the list does not hold - or none where one is required (a row from the agent or an import) - is shown as it
    // is: the browser showed the first option as if it were chosen, and choosing that one then changed nothing.
    const missing = value != null ? !column.options.includes(value) : !column.nullable;
    return <select title={title} value={value ?? ''} onChange={e => onChange(e.target.value === '' && column.nullable ? null : e.target.value)}>
      {column.nullable && <option value="">(none)</option>}{missing && <option value={value ?? ''} disabled={value == null}>{value ?? '(not set)'}</option>}
      {column.options.map((o: string) => <option key={o} value={o}>{o}</option>)}</select>;
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

const exact = (v: Json) => (v == null ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v));
export function DiffView({ diff }: { diff: Json[] }) {
  if (!diff.length) return <p className="hint">No differences.</p>;
  return <table className="grid small"><thead><tr><th>Section</th><th>Row</th><th>Change</th><th>Field</th><th>Before</th><th>After</th></tr></thead>
    <tbody>{diff.flatMap((d: Json) => d.fields.map((f: Json, i: number) => (
      <tr key={`${d.section}/${d.key}/${f.field}`} className={`diff-${d.change}`}>
        {i === 0 && <><td rowSpan={d.fields.length}>{d.section}</td><td rowSpan={d.fields.length}>{d.key}</td><td rowSpan={d.fields.length}>{d.change}</td></>}
        <td>{f.field}</td><td>{exact(f.before)}</td><td>{exact(f.after)}</td>
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
    ? { ...c, label: 'Judged at' } : c.name === 'missing_is_failure' ? { ...c, label: 'Missing value = failed' } : c.name === 'margin_sides' ? { ...c, label: 'Margin sides' }
    : c.name === 'constraint' ? { ...c, guidance: c.guidance + ' "then lower / higher is better" is the objective: among the designs that pass '
      + 'every hard spec, the best one is the lowest / highest here (one spec at most); with an Objective bonus weight above 0 (Reward and '
      + 'conditions) the reward also pushes it past the limit.' }
    : c.name === 'normalization_scale' ? { ...c, guidance: 'Threshold distance divided by this positive scale, then shaped by the selected capped or compressed reward. Empty uses the threshold size. Feasibility uses the actual bounds, not the reward.' } : c);
  // Specs shows the objective inside the constraint list (LimitSelect), and "Judged at" only while the run plans training
  // corners: without corners every spec is judged at nominal, so the choice would do nothing. Both keep their values.
  const corners = (config.run?.conditions?.policy ?? 'off') !== 'off';
  const shown = columns.filter(c => tab !== 'targets' || (c.name !== 'direction_after_feasible' && (c.name !== 'nominal_only' || corners)));
  const hidden = shown.filter(c => c.advanced);
  const visible = shown.filter(c => more || !c.advanced);
  const keyField: string = schema.section_keys[tab];
  const rows: Json[] = config[tab] ?? [];
  const issues = useMemo(() => (validation?.issues ?? []).filter((i: Json) => i.path.startsWith(tab)), [validation, tab]);
  // The report's row paths (targets[3]) name rows of the configuration it was made for (`sent`, App.tsx). After Delete,
  // Undo or an import moved the rows, an issue is drawn only on the row it was found for, until the new report comes.
  const reported: Json[] | null = validation?.sent?.[tab] ?? null;
  const rowIssues = (index: number) => reported && reported[index]?.[keyField] !== rows[index]?.[keyField] ? []
    : issues.filter((i: Json) => i.path.startsWith(`${tab}[${index}]`));
  // Ticks of rows that are gone (Delete, Undo, an import) go with them: a new row given a freed ID came already ticked.
  useEffect(() => setSelected(s => {
    const ids = new Set(rows.map(r => r[keyField]));
    const kept = Object.fromEntries(Object.entries(s).filter(([id, on]) => on && ids.has(id)));
    return Object.keys(kept).length === Object.keys(s).length ? s : kept;
  }), [rows, keyField]);

  // One change of one row, several fields at once (the constraint list sets the limit and the objective): one Undo step.
  // The scale follows only a field that really changes: picking an objective re-sends the unchanged limit, and an empty
  // (backend-sized) scale must not be frozen into the row by that.
  const patch = (index: number, fields: Json) =>
    setConfig((c: Json) => ({ ...c, [tab]: c[tab].map((r: Json, i: number) => i === index ? (() => {
      const row = { ...r, ...fields };
      if (tab === 'targets' && Object.keys(fields).some(name => SCALE_FIELDS.includes(name) && fields[name] !== r[name])) row.normalization_scale = followScale(r, row);
      return row;
    })() : r) }));
  const update = (index: number, name: string, value: Json) => patch(index, { [name]: value });
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
  const remove = () => setConfig((c: Json) => ({ ...c, [tab]: c[tab].filter((r: Json) => !selected[r[keyField]]) }));

  // JSON import goes through a DIFF CONFIRMATION before it replaces anything. The backend's diff covers the three tables;
  // a whole configuration also replaces the other sections, and the confirmation names each one that changes (it used to
  // show "0 changed rows" while it replaced the run settings - review of 2026-09-29). Rows for one table write only that
  // table on Apply: the rest of the configuration as it is THEN, so an edit made while the box was open stays (it used to
  // be put back to the configuration of the moment of the import).
  const importJson = async (f: File) => {
    setError(null);
    try {
      const incoming = JSON.parse(await f.text());
      // A whole configuration is one this workbench wrote (Export JSON): a file that merely has a schema_version - such as
      // configs/gpdk045_conditions.json - was taken for one, and Apply left a blank page (audit 2026-09-30).
      const whole = incoming?.schema_version === 'gator-workbench-config-v1';
      const rowsIn = Array.isArray(incoming?.[tab]) ? incoming[tab] : Array.isArray(incoming) ? incoming : null;
      if (whole && !(['project', 'circuit', 'run', 'output'].every(k => incoming[k] && typeof incoming[k] === 'object')
          && ROW_TABS.every(k => incoming[k] == null || Array.isArray(incoming[k]))))
        throw new Error('the file says it is a workbench configuration, but its sections (project, circuit, run, output and the three tables) are not all there');
      if (!whole && !rowsIn)
        throw new Error(`the file is neither a workbench configuration (from Export JSON) nor ${TITLES[tab]} rows (a list, or an object with "${tab}")`);
      if (!whole && rowsIn!.some((r: Json) => !r || typeof r !== 'object' || !r[keyField]))
        throw new Error(`every ${TITLES[tab]} row needs its ${keyField}`);
      const next = migrateConfig(whole ? incoming : { ...config, [tab]: rowsIn });
      const { diff } = await api.diff(config, next);
      const others = Object.keys(IMPORTED_SECTIONS).filter(k => JSON.stringify(config[k] ?? null) !== JSON.stringify(next[k] ?? null));
      setPending({ next, diff, others, rows: whole ? null : { section: tab, value: next[tab] } });
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
        <div className="row"><button onClick={() => applyImport(pending)}>Apply</button><button onClick={() => setPending(null)}>Cancel</button></div>
        {(pending.diff.length > 0 || !pending.others.length) && <DiffView diff={pending.diff} />}</div>}
      <div className="scroll">
        <table className="grid editor">
          <thead><tr><th className="sel"></th>{visible.map(c => <th key={c.name} data-field={c.name} title={c.guidance} onClick={() => setHelp(c)}>{c.label ?? c.name}{c.required ? ' *' : ''}</th>)}<th>Issues</th></tr></thead>
          <tbody>{rows.map((row, index) => {
            const found = rowIssues(index);
            return <tr key={index} className={found.some((i: Json) => i.level === 'error' || i.level === 'blocker') ? 'has-error' : ''}>
              <td className="sel"><input type="checkbox" checked={!!selected[row[keyField]]} onChange={e => setSelected(s => ({ ...s, [row[keyField]]: e.target.checked }))} /></td>
              {/* A field the row does not STATE is shown with the value the backend uses for it (hard = on, tolerance = 0 ...): a
                  starter row's absent `hard` used to look unchecked although the target is hard. A box the user cleared is null,
                  not absent, and stays empty. */}
              {visible.map(c => <td key={c.name}>{tab === 'targets' && c.name === 'constraint'
                ? <LimitSelect row={row} title={c.guidance} onChange={fields => patch(index, fields)} />
                : <Cell column={c} value={row[c.name] === undefined ? c.default : row[c.name]} onChange={v => update(index, c.name, v)} />}</td>)}
              <td className="issues">{found.map((i: Json, n: number) => <div key={n} className={`issue ${i.level}`} title={i.message}>{i.level}: {i.code}</div>)}</td>
            </tr>; })}</tbody>
        </table>
      </div>
      {help && <p className="guidance" onClick={() => setHelp(null)}><b>{help.name}</b> ({help.type}{help.options ? ': ' + help.options.join(' | ') : ''}) - {help.guidance}</p>}
      {issues.filter((i: Json) => !/\[\d+\]/.test(i.path)).map((i: Json, n: number) => <p key={n} className={`issue ${i.level}`}>{i.level}: {i.message}</p>)}
    </section>
  );
}
