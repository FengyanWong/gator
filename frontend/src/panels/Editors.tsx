import { Icon } from './Icons';
import { Fragment, memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { pointAt } from './CircuitPicture';
import { api, Json, saveJson } from '../api';
import { migrateConfig } from '../store';
import { Typed } from './Typed';
import { MatchedDevices } from './MatchedDevices';

export type Section = 'parameters' | 'targets' | 'measurements';
const TITLES: Record<Section, string> = { parameters: 'Parameters', measurements: 'Probes', targets: 'Specs' };   // key order = tab order
const ROW_TABS = Object.keys(TITLES);
/** The sections a whole-configuration import replaces beside the three tables, as the confirmation names them. */
const IMPORTED_SECTIONS: Record<string, string> = { project: 'project labels', circuit: 'circuit source', run: 'run settings',
  output: 'output settings', research: 'research labels' };

/** The scale offered while nobody has typed one, or null when the row gives nothing to size it by yet: then the scale stays
 * empty and the backend sizes it from the limits (the size of the threshold, else 1), instead of freezing a bare 1 W or
 * 1 Hz into a row whose limits are typed afterwards (record 7.112).
 * One rule since record 7.183: the size of the limit - which is what an empty scale means too - and 6 dB (a factor of two)
 * for a dB row, where "a fraction of a 40 dB limit" makes each dB count for little. On the 227 recorded designs the tighter
 * suggestions of before acted as hidden weights: 10 degrees on a phase row reordered the designs, and half the width of an
 * interval put most of a ring oscillator's designs above a miss of 0.9. */
function suggestedScale(row: Json): number | null {
  if (row.unit === 'dB') return 6;
  return Math.max(...[row.lower, row.upper].filter(v => typeof v === 'number').map(Math.abs), 0) || null;
}
/** What the page suggested until record 7.183 (3 dB, 10 degrees, half an interval): a row that still holds it was never typed
 * into, so it follows the next edit to today's suggestion instead of keeping the old number for good. */
function formerSuggestion(row: Json): number | null {
  if (row.unit === 'dB') return 3;
  if (row.unit === 'deg') return 10;
  if (row.constraint === 'interval' && row.lower != null && row.upper != null && row.upper > row.lower) return (row.upper - row.lower) / 2;
  return null;
}
const SCALE_FIELDS = ['unit', 'lower', 'upper', 'constraint'];
/** The scale after an edit of a field it depends on: an empty scale, or one still equal to the row's suggestion before the
 * edit, follows the edit; a scale the user typed stays. */
function followScale(before: Json, after: Json): number | null {
  const untouched = before.normalization_scale == null || before.normalization_scale === suggestedScale(before)
    || before.normalization_scale === formerSuggestion(before);
  return untouched ? suggestedScale(after) : after.normalization_scale;
}

const MORE_KEY = 'gator-workbench-editor-more-columns';

/** Specs: the limit and the objective in ONE list. An objective means "once every hard spec passes, the lower (higher) the
 *  better" and works on the limit on its side (minimize an upper limit, maximize a lower one), so a pair that could never
 *  work (>= then lower is better) is not offered. Saved as before: `constraint` + `direction_after_feasible`. */
const LIMIT_CHOICES: [string, string][] = [['>=', 'none'], ['>=', 'maximize'], ['<=', 'none'], ['<=', 'minimize'],
  ['interval', 'none'], ['interval', 'minimize'], ['interval', 'maximize']];
// "target ± tolerance" went with its two columns (review of 2026-10-03): it was exactly an interval [target - tolerance,
// target + tolerance], and a tolerance on any other row only loosened its limit. Older rows are rewritten so when they load.
const LIMIT_TEXT: Record<string, string> = { '>=': '≥ lower', '<=': '≤ upper', interval: 'interval' };
// A row without a constraint read "undefined", and an objective this list does not know read like a plain limit (review of
// 2026-10-01): both are shown as they are.
const limitLabel = (constraint: string, objective: string) => (constraint ? LIMIT_TEXT[constraint] ?? String(constraint) : '(not set)')
  + (objective === 'minimize' ? ', then lower is better' : objective === 'maximize' ? ', then higher is better'
    : objective && objective !== 'none' ? `, then ${objective}` : '');

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

/** Readable small and large numbers (record 7.181, design advice): a bound, limit or scale of a row in an unprefixed base unit
 *  reads in engineering notation - 0.0004 A as 400µ A, 4.5e-7 m as 450n m - below 0.01 and from 10,000 up; a prefixed unit
 *  (um, pF, mV) and everything else read as stored. Exact: the digits of the shortest form are moved, never computed, and a
 *  typed "450n" is read as the number 450e-9. The formula bar shows the stored number. */
const PREFIX: Record<number, string> = { [-15]: 'f', [-12]: 'p', [-9]: 'n', [-6]: 'µ', [-3]: 'm', 3: 'k', 6: 'M', 9: 'G', 12: 'T' };
const SUFFIX: Record<string, number> = { f: -15, p: -12, n: -9, u: -6, 'µ': -6, 'μ': -6, m: -3, k: 3, K: 3, M: 6, G: 9, T: 12 };
const BASE_UNITS = new Set(['m', 'F', 'ohm', 'Ohm', 'Ω', 'H', 'V', 'A', 'W', 'J', 'Hz', 's']);
const READABLE: Record<string, string[]> = { parameters: ['lower', 'upper', 'step', 'initial_value'], targets: ['lower', 'upper', 'normalization_scale'] };
export function engineering(v: number): string {
  const size = Math.abs(v);
  if (!Number.isFinite(v) || v === 0 || (size >= 0.01 && size < 1e4)) return String(v);
  const [mantissa, power] = v.toExponential().split('e');           // "-4.5", "-7": the shortest digits that read back exactly
  const exponent = Number(power), three = Math.floor(exponent / 3) * 3, prefix = PREFIX[three];
  if (prefix === undefined) return String(v);
  const digits = mantissa.replace('-', '').replace('.', ''), point = 1 + exponent - three;   // the point moves 0, 1 or 2 places
  const whole = digits.slice(0, point).padEnd(point, '0'), fraction = digits.slice(point);
  return `${v < 0 ? '-' : ''}${whole}${fraction ? `.${fraction}` : ''}${prefix}`;
}
/** A typed number: plain, with an exponent (2.5e-6), or with an SI letter (2.5u, 400µ, 10k). */
export function readNumber(text: string): number | undefined {
  const s = text.trim(), letter = /^([-+]?(?:\d+\.?\d*|\.\d+))([fpnuµμmkKMGT])$/.exec(s);
  const n = letter ? Number(`${letter[1]}e${SUFFIX[letter[2]]}`) : s === '' ? NaN : Number(s);
  return Number.isFinite(n) ? n : undefined;
}

/** One cell. `fixed`: why the value is shown and not typed - it follows another field (a Maestro output's Probe ID follows
 *  its output name). `off`: why the field does nothing on this row (a follower's bounds, step, scale, type and "optimized":
 *  its leader decides them) - shown greyed, with that reason as its tooltip (review of 2026-10-03). */
function Cell({ column, value, onChange, fixed = null, off = null, readable = false }: { column: Json; value: Json; onChange: (v: Json) => void;
  fixed?: string | null; off?: string | null; readable?: boolean }) {
  const title = off ?? fixed ?? column.guidance, disabled = off !== null;
  if (column.name === 'nominal_only') return <select aria-label="Judged at" title={title} disabled={disabled}
    value={value ? 'nominal' : 'all'} onChange={e => onChange(e.target.value === 'nominal')}>
    <option value="all">All planned conditions</option><option value="nominal">Nominal only</option></select>;
  if (fixed !== null) return <input title={title} className="readonly" readOnly value={value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value)} />;
  if (column.options) {
    // A value the list does not hold - or none where one is required (a row from the agent or an import) - is shown as it
    // is: the browser showed the first option as if it were chosen, and choosing that one then changed nothing.
    const missing = value != null ? !column.options.includes(value) : !column.nullable;
    return <select title={title} disabled={disabled} value={value ?? ''} onChange={e => onChange(e.target.value === '' && column.nullable ? null : e.target.value)}>
      {column.nullable && <option value="">(none)</option>}{missing && <option value={value ?? ''} disabled={value == null}>{value ?? '(not set)'}</option>}
      {column.options.map((o: string) => <option key={o} value={o}>{o}</option>)}</select>;
  }
  if (column.type === 'boolean') return <input type="checkbox" title={title} disabled={disabled} checked={!!value} onChange={e => onChange(e.target.checked)} />;
  if (column.type === 'number' || column.type === 'integer') {
    return <Typed title={title} disabled={disabled} className="numeric" placeholder={column.nullable ? '-' : ''} value={value} onChange={onChange}
      format={v => v == null ? '' : readable && typeof v === 'number' ? engineering(v) : String(v)}
      parse={t => { const n = readNumber(t); return t.trim() === '' ? { value: column.nullable ? null : 0 } : n !== undefined ? { value: n } : undefined; }} />;
  }
  if (column.type === 'array' || column.type === 'object') {
    return <Typed title={title + ' (JSON)'} disabled={disabled} value={value} onChange={onChange} format={v => v == null ? '' : JSON.stringify(v)}
      parse={t => { if (t.trim() === '') return { value: null }; try { return { value: JSON.parse(t) }; } catch { return undefined; } }} />;
  }
  return <input title={title} disabled={disabled} value={value ?? ''} onChange={e => onChange(e.target.value === '' && column.nullable ? null : e.target.value)} />;
}

/** What the formula bar shows of the chosen cell: where it is, its whole value as text, whether it is typed there, and why not. */
type BarCell = { id: string; where: string; text: string; editable: boolean; why: string; format: string };

/** The editors' formula bar (record 7.175, user: "add excel like single cell whole row text edit somewhere for long text editing
 *  which cant show everything in the cell"): the chosen cell's whole value in a box as wide as the table, as in a spreadsheet.
 *  What is typed there goes into the cell when Enter, Tab or leaving the box takes it - one Undo step - and Esc keeps the cell
 *  as it was. A list, a tick box and a value that follows another field are shown here, not typed. */
function FormulaBar({ cell, commit, back }: { cell: BarCell | null; commit: (text: string) => string | null; back: () => void }) {
  const [draft, setDraft] = useState<string | null>(null);         // null: not typing here, the box shows the cell's value
  const [problem, setProblem] = useState<string | null>(null);
  // The text is read from a ref too: Enter and Esc go back to the cell, which blurs the box at once, and that blur must see the
  // text already taken or dropped - read from the render it would write a text Esc had just dropped.
  const typed = useRef<string | null>(null);
  const keep = (text: string | null) => { typed.current = text; setDraft(text); };
  useEffect(() => { keep(null); setProblem(null); }, [cell?.id]);  // another cell: its own value
  const take = () => {
    if (typed.current === null) return true;
    const refused = commit(typed.current);
    setProblem(refused);
    if (!refused) keep(null);
    return !refused;
  };
  return (
    <div className="formula">
      <div className="formula-bar">
        <span className="formula-where" title={cell ? cell.format : 'Click a cell of the table to see its whole value here.'}>{cell ? cell.where : 'No cell chosen'}</span>
        <textarea rows={1} spellCheck={false} aria-label="Whole value of the chosen cell" disabled={!cell} readOnly={!cell?.editable}
          value={draft ?? cell?.text ?? ''} placeholder={cell ? '' : 'Click a cell to see and edit its whole value here'}
          title={!cell ? undefined : cell.editable ? 'The whole value of the chosen cell. Enter (or Tab, or clicking elsewhere) writes it into the cell; Esc keeps the cell as it was.' : cell.why}
          onChange={e => { keep(e.target.value.replace(/\r?\n/g, ' ')); setProblem(null); }}
          onKeyDown={e => {
            if (e.key === 'Enter') { e.preventDefault(); if (take()) back(); }
            else if (e.key === 'Escape') { e.preventDefault(); keep(null); setProblem(null); back(); }
            else if (e.key === 'Tab' && !take()) e.preventDefault();
          }}
          onBlur={take} />
      </div>
      {problem && <p className="error formula-problem">{problem}</p>}
    </div>);
}

// What a follower row (binding_group set) leaves to its leader: the written value is the leader's times the ratio, so its own
// bounds, step, scale, type and "optimized" do nothing (Save task even clears its bounds).
const FOLLOWER_IGNORES = ['optimized', 'value_type', 'lower', 'upper', 'step', 'scale'];
// A Maestro output's Probe ID is m_ + its name, as Save task names it (virtuoso_setup.probe_id); spec equations are rewritten
// when it follows a renamed output. Equation names are plain identifiers (spec_equations.parse reads them with Python's ast).
const probeIdOf = (outputName: string) => `m_${outputName}`;
const renameInEquation = (equation: string, from: string, to: string) =>
  equation.replace(new RegExp(`(?<![A-Za-z0-9_.])${from.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?![A-Za-z0-9_])`, 'g'), to);

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
function EditorsView({ schema, config, setConfig, undo, redo, canUndo, canRedo, validation, onAgent, taskSlot, taskNotes }:
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
  const [matched, setMatched] = useState(0);               // each toolbar press opens a fresh read; zero closes the box
  const [error, setError] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);
  // The chosen cell of the formula bar (record 7.175): its row by position, checked by the row's ID (a Delete or an Undo moves
  // rows; while the ID itself is being typed, the position holds).
  const [active, setActive] = useState<{ index: number; name: string; key: string } | null>(null);
  // Tied rows opened under their leader, by the leader's ID (record 7.180), and what the last block paste, fill or copy did.
  const [openTies, setOpenTies] = useState<Record<string, boolean>>({});
  const [note, setNote] = useState<{ text: string; warn: boolean } | null>(null);
  // The find box's text, kept per table (record 7.184).
  const [find, setFind] = useState<Record<string, string>>({});
  const table = useRef<HTMLTableElement>(null);
  // The row's ID stays in view beside the tick box while the table scrolls sideways (record 7.182): it sticks at the tick-box
  // column's own width - which a tie toggle widens on Parameters, and a narrower window can change without a new render - and a
  // line marks its edge while columns pass under it.
  const markScrolled = (box: HTMLElement | null | undefined) => box?.classList.toggle('scrolled-x', box.scrollLeft > 0);
  useLayoutEffect(() => {
    markScrolled(table.current?.parentElement);
    const sel = table.current?.querySelector('thead th.sel');
    if (!sel) return;
    const measure = () => table.current?.style.setProperty('--sel-w', `${sel.getBoundingClientRect().width}px`);
    measure();
    const watch = new ResizeObserver(measure);
    watch.observe(sel);
    return () => watch.disconnect();
  });
  // `signal` holds a Maestro output's expression (ymax(VT("/OUT")), getData(... ?result "stb")): "signal" read like a
  // net name (review of 2026-10-03). For a profile metric it is a label of what is measured.
  const columns: Json[] = schema.editors[tab].map((c: Json) => tab === 'measurements' && c.name === 'signal' ? { ...c, label: 'Expression' }
    : tab !== 'targets' ? c : c.name === 'nominal_only'
    ? { ...c, label: 'Judged at' } : c.name === 'missing_is_failure' ? { ...c, label: 'Missing value = failed' } : c.name === 'margin_sides' ? { ...c, label: 'Margin sides' }
    : c.name === 'constraint' ? { ...c, guidance: c.guidance + ' "then lower / higher is better" is the objective: among the designs that pass '
      + 'every hard spec, the best one is the lowest / highest here (one spec at most); with an Objective bonus weight above 0 (Reward and '
      + 'conditions) the reward also pushes it past the limit.' }
    : c.name === 'normalization_scale' ? { ...c, label: 'Scale', guidance: 'The distance outside the limit that costs half of this row\'s penalty. Empty: the size of the limit, so a value 50 % outside costs a third and 100 % outside a half - the rule every saved task uses. Type a number only for a limit of 0, or to make this row count more (smaller) or less (larger) than the others. Passing or failing is decided by the limits alone.' } : c);
  // Specs shows the objective inside the constraint list (LimitSelect), and "Judged at" only while the run plans training
  // corners: without corners every spec is judged at nominal, so the choice would do nothing. Both keep their values.
  const corners = (config.run?.conditions?.policy ?? 'off') !== 'off';
  // A hidden column (schema.HIDDEN_COLUMNS: initial_value, result_source) is kept in the rows and never shown.
  const shown = columns.filter(c => !c.hidden && (tab !== 'targets' || (c.name !== 'direction_after_feasible' && (c.name !== 'nominal_only' || corners))));
  const hidden = shown.filter(c => c.advanced);
  const visible = shown.filter(c => more || !c.advanced);
  const keyField: string = schema.section_keys[tab];
  const rows: Json[] = config[tab] ?? [];
  const issues = useMemo(() => (validation?.issues ?? []).filter((i: Json) => i.path.startsWith(tab)), [validation, tab]);
  const issuesByRow = useMemo(() => {
    const grouped = new Map<number, Json[]>();
    for (const issue of issues) {
      const match = /^\[(\d+)\]/.exec(issue.path.slice(tab.length));
      if (match) { const index = Number(match[1]), row = grouped.get(index) ?? []; row.push(issue); grouped.set(index, row); }
    }
    return grouped;
  }, [issues, tab]);
  // The report's row paths (targets[3]) name rows of the configuration it was made for (`sent`, App.tsx). After Delete,
  // Undo or an import moved the rows, an issue is drawn only on the row it was found for, until the new report comes.
  const reported: Json[] | null = validation?.sent?.[tab] ?? null;
  const rowIssues = (index: number) => reported && reported[index]?.[keyField] !== rows[index]?.[keyField] ? []
    : issuesByRow.get(index) ?? [];
  // Ticks of rows that are gone (Delete, Undo, an import) go with them: a new row given a freed ID came already ticked.
  useEffect(() => setSelected(s => {
    const ids = new Set(rows.map(r => r[keyField]));
    const kept = Object.fromEntries(Object.entries(s).filter(([id, on]) => on && ids.has(id)));
    return Object.keys(kept).length === Object.keys(s).length ? s : kept;
  }), [rows, keyField]);

  // Fields that follow a change with it, in the same Undo step (review of 2026-10-03): a Maestro output's Probe ID follows its
  // output name, and the spec equations that use the ID follow it; a spec whose equation becomes one Probe takes that Probe's
  // unit while it has no limits yet (its unit must match the Probe's anyway; a prefix can be typed after); the scale follows
  // only a field that really changes - picking an objective re-sends the unchanged limit, and an empty (backend-sized) scale
  // must not be frozen into the row by that. One path for a typed cell, a pasted block and a fill since record 7.184 (a pasted
  // output name had left its Probe ID behind); a limit written without its objective keeps the objective where they still pair.
  const withFollowers = (c: Json, changes: Map<number, Json>): Json => {
    const renames: [string, string][] = [];
    const next = { ...c, [tab]: c[tab].map((r: Json, i: number) => {
      const fields = changes.get(i);
      if (!fields) return r;
      const row = { ...r, ...fields };
      if (tab === 'measurements' && typeof fields.source_name === 'string' && r.result_source === 'ade_output'
          && /^[A-Za-z_][A-Za-z0-9_]*$/.test(fields.source_name)) {
        row.measurement_id = probeIdOf(fields.source_name);
        if (r.measurement_id && r.measurement_id !== row.measurement_id) renames.push([String(r.measurement_id), row.measurement_id]);
      }
      if (tab === 'targets') {
        const probe = typeof fields.equation === 'string' && !('unit' in fields)
          ? (c.measurements ?? []).find((m: Json) => m.measurement_id === fields.equation.trim()) : null;
        if (probe?.unit && (!r.unit || (r.lower == null && r.upper == null))) row.unit = probe.unit;
        if ('constraint' in fields && !('direction_after_feasible' in fields)
            && !LIMIT_CHOICES.some(([limit, objective]) => limit === row.constraint && objective === (row.direction_after_feasible ?? 'none'))) row.direction_after_feasible = 'none';
        if (!('normalization_scale' in fields) && SCALE_FIELDS.some(name => row[name] !== r[name])) row.normalization_scale = followScale(r, row);
      }
      return row;
    }) };
    if (renames.length) next.targets = (c.targets ?? []).map((t: Json) => typeof t.equation === 'string'
      ? { ...t, equation: renames.reduce((e, [from, to]) => renameInEquation(e, from, to), t.equation) } : t);
    return next;
  };
  // One change of one row, several fields at once (the constraint list sets the limit and the objective): one Undo step.
  const patch = (index: number, fields: Json) => setConfig((c: Json) => withFollowers(c, new Map([[index, fields]])));
  const update = (index: number, name: string, value: Json) => patch(index, { [name]: value });
  const add = () => {
    const row: Json = {};
    // A required field without a default comes as `default: null` from the schema: that means "none", not null - a new
    // Specs row used to get constraint = null and normalization_scale = null, and the whole configuration failed validation.
    for (const c of columns) row[c.name] = c.default !== undefined && (c.default !== null || c.nullable) ? c.default
      : c.nullable ? null : c.options ? c.options[0] : c.type === 'number' ? 1 : c.type === 'boolean' ? false : '';
    // A new probe measures the way the task's other probes do - a task measures one way, Save task refuses a mix - where it
    // used to take result_source's default, backend_profile, in a Maestro task too (review of 2026-10-03). The first probe of a
    // task: ngspice and MOCK tasks read their backend's metrics, every other task reads Maestro outputs.
    if (tab === 'measurements') row.result_source = config.measurements?.[0]?.result_source
      ?? (/^(ngspice|synthetic):/.test(String(config.circuit?.task_id ?? '')) ? 'backend_profile' : 'ade_output');
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
  const remove = () => { const gone = new Set(selection.map(s => s.key)); setConfig((c: Json) => ({ ...c, [tab]: c[tab].filter((r: Json) => !gone.has(r[keyField])) })); };

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
  // A Parameters row under the pointer (or the keyboard) lights the devices it sizes in the circuit picture of the Project
  // column: its own and those of the rows tied to it (binding_group), so w_pair lights M1 and its follower's M2 (record 7.158).
  const devicesOf = (row: Json): string[] => {
    const leader = row.binding_group || row.variable_id;
    const tied = rows.filter(r => r.variable_id === leader || (r.binding_group && r.binding_group === leader));
    return [...new Set([row, ...tied].map(r => r.instance_path).filter(Boolean))] as string[];
  };
  useEffect(() => () => pointAt([]), [tab]);
  useEffect(() => { setActive(null); setOpenTies({}); setNote(null); }, [tab]);

  // Why a cell is shown and not typed: it follows another field, or its row's leader decides it (record 7.158 review).
  const fixedOf = (row: Json, c: Json): string | null => tab === 'measurements' && c.name === 'measurement_id' && row.result_source === 'ade_output'
    ? `A Maestro output's Probe ID is m_ + its output name (Save task names it so): it follows the name, and so do the spec equations that use it.` : null;
  const offOf = (row: Json, c: Json): string | null => tab === 'parameters' && row.binding_group && FOLLOWER_IGNORES.includes(c.name)
    ? `Follows ${row.binding_group}: its leader's value times the ratio is written, so this field does nothing on this row.` : null;
  const at = !active ? -1 : rows[active.index] && (active.name === keyField || String(rows[active.index][keyField] ?? '') === active.key)
    ? active.index : rows.findIndex(r => String(r[keyField] ?? '') === active.key);
  const activeRow = at >= 0 ? rows[at] : null;
  const activeColumn: Json = activeRow ? columns.find(c => c.name === active!.name) ?? null : null;
  const barCell: BarCell | null = activeRow && activeColumn ? (() => {
    const c = activeColumn, value = activeRow[c.name] === undefined ? c.default : activeRow[c.name];
    const choice = tab === 'targets' && c.name === 'constraint' ? 'A list: choose it in the cell.'
      : c.name === 'nominal_only' || c.options ? `A list: choose it in the cell${c.options ? ` (${c.options.join(' | ')})` : ''}.`
      : c.type === 'boolean' ? 'A tick box: tick it in the cell.' : null;
    const why = fixedOf(activeRow, c) ?? offOf(activeRow, c) ?? choice;
    const text = tab === 'targets' && c.name === 'constraint' ? limitLabel(activeRow.constraint, activeRow.direction_after_feasible ?? 'none')
      : c.name === 'nominal_only' ? (value ? 'Nominal only' : 'All planned conditions') : c.type === 'boolean' ? (value ? 'on' : 'off')
      : value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value);
    return { id: `${tab}|${at}|${c.name}`, where: `${c.label ?? c.name} · ${activeRow[keyField] ?? `row ${at + 1}`}`, text, editable: why === null,
      why: why ?? '', format: `${c.name} (${c.type}${c.options ? ': ' + c.options.join(' | ') : ''}${c.required ? ', required' : ''}) - ${c.guidance ?? ''}` };
  })() : null;
  // The bar's text as the cell would take it: a number as the number cell reads it, a list as JSON; one change, one Undo step.
  const commitBar = (text: string): string | null => {
    if (!activeRow || !activeColumn) return null;
    const c = activeColumn;
    let value: Json;
    if (c.type === 'number' || c.type === 'integer') {
      const s = text.trim(), n = readNumber(s);
      if (s !== '' && n === undefined) return `"${s}" is not a number: type it plain, with an exponent (2.5e-6) or an SI letter (2.5u); the unit column says the unit.`;
      value = s === '' ? (c.nullable ? null : 0) : n;
    } else if (c.type === 'array' || c.type === 'object') {
      if (text.trim() === '') value = null;
      else { try { value = JSON.parse(text); } catch { return 'Not JSON: a list is written as ["a", "b"].'; } }
    } else value = text === '' && c.nullable ? null : text;
    const before = activeRow[c.name] === undefined ? c.default : activeRow[c.name];
    if (JSON.stringify(value) !== JSON.stringify(before)) update(at, c.name, value);
    return null;
  };
  // Tied rows (record 7.180, design advice 4): a Parameters row whose binding_group names a row of the table follows that leader -
  // the leader decides its size - and is folded under it; the leader's first cell counts them and opens them. A tied row with an
  // issue, or with the chosen cell, is never folded away. The rows keep their order.
  const ids = new Set(rows.map(r => r[keyField]));
  const leaderOf = (row: Json): string | null => tab === 'parameters' && row.binding_group && ids.has(row.binding_group) ? row.binding_group : null;
  const tiedCount = new Map<string, number>();
  for (const r of rows) { const l = leaderOf(r); if (l) tiedCount.set(l, (tiedCount.get(l) ?? 0) + 1); }
  const foldedAway = (row: Json, index: number) => { const l = leaderOf(row); return !!l && !openTies[l] && at !== index
    && !rowIssues(index).some((i: Json) => i.level === 'error' || i.level === 'blocker'); };
  // The find box (record 7.184, design advice 4): while it holds text, the rows in view are those whose text cells in view hold
  // every word of it (not case-sensitive), folded or not; the keys, a pasted block, Ctrl+D, Ctrl+C, Copy and Delete selected
  // then work on the rows in view, and a chosen cell whose row went out of view is let go.
  const findWords = (find[tab] ?? '').toLowerCase().split(/\s+/).filter(Boolean);
  const textColumns = visible.filter(c => c.type === 'string' && !c.options);
  const matchesFind = (row: Json) => { const text = textColumns.map(c => String(row[c.name] ?? '')).join('\n').toLowerCase(); return findWords.every(w => text.includes(w)); };
  const inView = (row: Json, index: number) => findWords.length ? matchesFind(row) : !foldedAway(row, index);
  const rowsInView = rows.map((_, i) => i).filter(i => inView(rows[i], i));
  const selection = rows.filter(r => selected[r[keyField]] && (!findWords.length || matchesFind(r))).map(r => ({ section: tab, key: r[keyField], fields: [] as string[] }));
  const firstInView = () => (table.current?.querySelector('tbody > tr:not([hidden]) > td[data-field] :is(input, select)') as HTMLElement | null)?.focus();

  // Keys as in a spreadsheet (record 7.180, design advice 6): Up and Down go to the same column of the row above or below (folded
  // rows are passed over), Enter to the row below and Shift+Enter above. A list keeps its own keys; the tick box column is left be.
  const moveFrom = (box: HTMLElement, step: 1 | -1) => {
    const field = box.closest<HTMLElement>('td[data-field]')?.dataset.field;
    let tr = box.closest('tr') as HTMLTableRowElement | null;
    if (!field || !tr) return false;
    do { tr = (step > 0 ? tr.nextElementSibling : tr.previousElementSibling) as HTMLTableRowElement | null; } while (tr && tr.hidden);
    const next = tr?.querySelector(`td[data-field="${CSS.escape(field)}"]`)?.querySelector('input, select') as HTMLElement | null;
    if (!next) return false;
    next.focus();
    if (next instanceof HTMLInputElement && next.type !== 'checkbox') next.select();
    return true;
  };
  const onTableKey = (e: React.KeyboardEvent) => {
    const box = e.target as HTMLElement, cell = box.closest<HTMLElement>('td[data-field]');
    // Ctrl+D fills down and Ctrl+C copies out (record 7.184); with text chosen inside the box Ctrl+C copies that text, as ever.
    if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && cell && /^[dc]$/i.test(e.key)) {
      const chosenText = box instanceof HTMLInputElement && box.type !== 'checkbox' && box.selectionStart !== box.selectionEnd;
      if (e.key.toLowerCase() === 'd') { e.preventDefault(); fillDown(cell); }
      else if (!chosenText) { e.preventDefault(); copyOut(cell); }
      return;
    }
    if (!(box instanceof HTMLInputElement) || box.closest('td.sel') || e.altKey || e.ctrlKey || e.metaKey) return;
    const step = e.key === 'ArrowDown' || (e.key === 'Enter' && !e.shiftKey) ? 1 : e.key === 'ArrowUp' || (e.key === 'Enter' && e.shiftKey) ? -1 : 0;
    if (step && moveFrom(box, step)) e.preventDefault();
  };
  // Ctrl+D fills down, as in a spreadsheet (record 7.184): in a ticked row, with more rows ticked, the column takes the value of
  // the topmost ticked row in view in every ticked row in view; otherwise the cell takes the value of the row above in view. One
  // Undo step. A cell that follows another field, or that its leader decides, is kept; an ID is not filled (each row needs its own).
  const shortText = (v: Json) => { const t = exact(v); return !t ? '(empty)' : t.length > 40 ? `${t.slice(0, 40)}...` : t; };
  const fillDown = (cell: HTMLElement) => {
    const c = visible.find(v => v.name === cell.dataset.field), index = Number(cell.closest('tr')?.dataset.index);
    if (!c || !rows[index]) return;
    if (c.name === keyField) return setNote({ text: `An ID is not filled down: each row needs its own ${c.label ?? c.name}.`, warn: true });
    const ticked = rowsInView.filter(i => selected[rows[i][keyField]]);
    const [from, targets] = ticked.length > 1 && ticked.includes(index) ? [ticked[0], ticked.slice(1)] : [rowsInView[rowsInView.indexOf(index) - 1], [index]];
    if (from === undefined) return setNote({ text: 'No row above in view to fill from.', warn: true });
    const value = rows[from][c.name] === undefined ? c.default : rows[from][c.name];
    const changes = new Map<number, Json>();
    let kept = 0;
    for (const i of targets) {
      if (fixedOf(rows[i], c) || offOf(rows[i], c)) { kept += 1; continue; }
      if (exact(rows[i][c.name] === undefined ? c.default : rows[i][c.name]) !== exact(value))
        changes.set(i, { [c.name]: value != null && typeof value === 'object' ? JSON.parse(JSON.stringify(value)) : value });
    }
    if (changes.size) setConfig((cfg: Json) => withFollowers(cfg, changes));
    const what = `${c.label ?? c.name} = ${shortText(value)} of ${rows[from][keyField]}`;
    setNote({ text: [changes.size ? `Filled ${changes.size} cell${changes.size === 1 ? '' : 's'} with ${what} (one Undo step).`
      : targets.length > kept ? `Nothing to fill: the cell${targets.length - kept === 1 ? ' holds' : 's hold'} ${what} already.` : 'Nothing filled.',
      kept ? `${kept} cell${kept === 1 ? ' that follows' : 's that follow'} another field kept.` : ''].filter(Boolean).join(' '), warn: false });
  };
  // Ctrl+C copies out, as in a spreadsheet (record 7.184): in a ticked row, the ticked rows in view - every column in view, a
  // header line first - as tab-separated lines for Excel; otherwise the cell alone. Numbers as stored (4.5e-7, which Excel
  // reads), a limit as its sign. The Copy button takes the ticked rows in view, or every row in view.
  const cellText = (row: Json, c: Json) => (c.name === 'nominal_only' ? ((row[c.name] ?? c.default) ? 'Nominal only' : 'All planned conditions')
    : exact(row[c.name] === undefined ? c.default : row[c.name])).replace(/[\t\r\n]+/g, ' ');
  const toClipboard = (text: string) => {
    const put = (e: ClipboardEvent) => { e.clipboardData?.setData('text/plain', text); e.preventDefault(); };
    document.addEventListener('copy', put, true);
    try { return document.execCommand('copy'); } finally { document.removeEventListener('copy', put, true); }
  };
  const copyOut = (cell: HTMLElement | null) => {
    const index = cell ? Number(cell.closest('tr')?.dataset.index) : -1, ticked = rowsInView.filter(i => selected[rows[i][keyField]]);
    const block = cell ? (ticked.includes(index) ? ticked : null) : ticked.length ? ticked : rowsInView;
    const c = cell ? visible.find(v => v.name === cell.dataset.field) : null;
    if (!block && (!c || !rows[index])) return;
    const text = block ? [visible.map(v => v.label ?? v.name), ...block.map(i => visible.map(v => cellText(rows[i], v)))].map(line => line.join('\t')).join('\r\n')
      : cellText(rows[index], c);
    if (!toClipboard(text)) return setNote({ text: 'The browser did not let the page copy: choose the text and copy it, or try the Copy button.', warn: true });
    setNote({ text: block ? `Copied ${block.length} row${block.length === 1 ? '' : 's'} x ${visible.length} columns with a header line, for Excel; a paste back here skips that line.`
      : `Copied ${c.label ?? c.name} of ${rows[index][keyField]}: ${shortText(text)}.`, warn: false });
  };
  // A block copied from Excel (tab-separated lines) pasted into a cell fills the rows in view from that one down and the columns
  // in view from that one right, as one Undo step (record 7.180). Each text is read as its column takes it; a cell that follows
  // another field, or that its leader decides, is left as it is; what cannot be read is named and left as it was. One value
  // pastes into the box as before.
  const readAs = (c: Json, raw: string): { value?: Json; problem?: string } => {
    const s = raw.trim();
    if (c.name === 'nominal_only') return /^nominal/i.test(s) ? { value: true } : /^all/i.test(s) ? { value: false } : { problem: `"${s}" in ${c.name}` };
    if (c.type === 'boolean') return /^(true|yes|on|1|x|✓)$/i.test(s) ? { value: true } : /^(false|no|off|0|)$/i.test(s) ? { value: false } : { problem: `"${s}" in ${c.name}` };
    if (c.name === 'constraint' && tab === 'targets') {
      const limit = ({ '>=': '>=', '≥': '>=', '<=': '<=', '≤': '<=', interval: 'interval' } as Record<string, string>)[s.toLowerCase()];
      return limit ? { value: limit } : { problem: `"${s}" in ${c.name}` };
    }
    if (c.options) {
      const option = c.options.find((o: string) => o.toLowerCase() === s.toLowerCase());
      return option !== undefined ? { value: option } : s === '' && c.nullable ? { value: null } : { problem: `"${s}" in ${c.name}` };
    }
    if (c.type === 'number' || c.type === 'integer') {
      if (s === '') return c.nullable ? { value: null } : {};
      const n = readNumber(s);
      return n !== undefined ? { value: n } : { problem: `"${s}" in ${c.name}` };
    }
    if (c.type === 'array' || c.type === 'object') {
      if (s === '') return { value: null };
      try { return { value: JSON.parse(s) }; } catch { return { problem: `"${s}" in ${c.name}` }; }
    }
    return { value: raw === '' && c.nullable ? null : raw };
  };
  const onTablePaste = (e: React.ClipboardEvent) => {
    const cell = (e.target as HTMLElement).closest<HTMLElement>('td[data-field]');
    const text = e.clipboardData.getData('text/plain').replace(/\r?\n$/, '');
    if (!cell || !/[\t\n]/.test(text)) return;
    e.preventDefault();
    const shown = [...(table.current?.querySelectorAll<HTMLTableRowElement>('tbody > tr') ?? [])].filter(tr => !tr.hidden);
    const first = shown.indexOf(cell.closest('tr') as HTMLTableRowElement), column = visible.findIndex(c => c.name === cell.dataset.field);
    const changes = new Map<number, Json>(), problems: string[] = [];
    let cells = 0, kept = 0, beyond = 0, lines = text.split(/\r?\n/).map(line => line.split('\t'));
    // A first line that names the columns it lands on - the header of a copied block (record 7.184) - is skipped.
    const names = (c: Json | undefined, v: string) => !!c && [c.name, c.label].some(n => n && n.toLowerCase() === v.trim().replace(/\s*\*$/, '').toLowerCase());
    const header = lines.length > 1 && lines[0].every((v, j) => names(visible[column + j], v));
    if (header) lines = lines.slice(1);
    lines.forEach((values, i) => {
      const tr = shown[first + i];
      if (!tr) { beyond += 1; return; }
      const index = Number(tr.dataset.index), row = rows[index];
      values.forEach((raw, j) => {
        const c = visible[column + j];
        if (!c) return;
        if (fixedOf(row, c) || offOf(row, c)) { kept += 1; return; }
        const read = readAs(c, raw);
        if (read.problem) problems.push(read.problem);
        else if ('value' in read) { changes.set(index, { ...(changes.get(index) ?? {}), [c.name]: read.value }); cells += 1; }
      });
    });
    if (changes.size) setConfig((cfg: Json) => withFollowers(cfg, changes));
    const said = [cells ? `Pasted ${cells} cell${cells === 1 ? '' : 's'} into ${changes.size} row${changes.size === 1 ? '' : 's'} (one Undo step).` : 'Nothing pasted.',
      header ? 'The header line was skipped.' : '',
      problems.length ? `Not read, left as they were: ${problems.slice(0, 4).join(', ')}${problems.length > 4 ? ` and ${problems.length - 4} more` : ''}.` : '',
      kept ? `${kept} cell${kept === 1 ? '' : 's'} that follow another field kept.` : '',
      beyond ? `${beyond} line${beyond === 1 ? '' : 's'} below the last row left out: Add rows first.` : ''].filter(Boolean).join(' ');
    setNote({ text: said, warn: problems.length + beyond > 0 });
  };

  // Back to the cell after Enter or Esc, as a spreadsheet does.
  const backToCell = () => {
    if (!active || at < 0) return;
    const cell = table.current?.querySelector(`tbody > tr:nth-child(${at + 1}) > td[data-field="${CSS.escape(active.name)}"]`);
    (cell?.querySelector('input, select') as HTMLElement | null)?.focus();
  };
  const probeIds: string[] = (config.measurements ?? []).map((m: Json) => m.measurement_id).filter(Boolean);

  return (
    <section className="panel editors" data-editor={tab}>
      {/* Another tab closes the Matched devices box: kept "open", coming back to Parameters mounted it again, and mounting
          is its press - it asked the backend with nobody pressing anything, and a reviewed diff was gone.
          Each editor has a colour of its own (record 7.158): its tab, its table's header row, and its ids where another editor shows them. */}
      <div className="tabs">{(Object.keys(TITLES) as Section[]).map(s => <button key={s} data-editor={s} className={s === tab ? 'active' : ''} onClick={() => { if (s !== tab) setMatched(0); setTab(s); setSelected({}); }}>{TITLES[s]} ({(config[s] ?? []).length})</button>)}
        <span className="tab-actions" ref={taskSlot} /></div>
      <div className="toolbar">
        <button onClick={add} title="Add: A new row at the end, with a free ID."><Icon name="add" label="Add" /></button>
        <button disabled={!selection.length} onClick={remove} title="Delete selected: The rows whose box is ticked. Undo takes them back."><Icon name="delete" label="Delete selected" /></button>
        <button disabled={!canUndo} onClick={undo} title="Undo: The last change to the configuration, from any panel - rows, run and output settings, an applied proposal."><Icon name="undo" label="Undo" /></button>
        <button disabled={!canRedo} onClick={redo} title="Redo: The change Undo took back."><Icon name="redo" label="Redo" /></button>
        <button onClick={() => saveJson(`${config.project.task_name}.config.json`, config)} title="Export JSON: The whole configuration - the three tables, the circuit, run and output settings, research labels - as one JSON file, downloaded."><Icon name="export" label="Export JSON" /></button>
        <button onClick={() => file.current?.click()} title="Import JSON...: Read a JSON file - a whole configuration, or rows for this tab. You see everything it changes before anything is replaced."><Icon name="import" label="Import JSON..." /></button>
        <input ref={file} type="file" accept="application/json" hidden onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; if (f) importJson(f); }} />
        <button onClick={() => copyOut(null)} title={'Copy for Excel: the ticked rows in view - or every row in view when none is ticked - every column in view, '
          + 'a header line first, as tab-separated lines. In a cell, Ctrl+C copies the ticked rows the same way, or the cell alone; Ctrl+D fills down.'}><Icon name="copy" label="Copy for Excel" /></button>
        <input type="search" className="find-rows" placeholder="Find rows" aria-label="Find rows" value={find[tab] ?? ''}
          title={'Find rows: only the rows whose text cells in view (ID, instance path, expression, equation, notes ...) hold every word typed stay in view, '
            + 'folded or not; not case-sensitive. Enter goes to the first of them, Esc clears the box.'}
          onChange={e => setFind(f => ({ ...f, [tab]: e.target.value }))}
          onKeyDown={e => { if (e.key === 'Escape') setFind(f => ({ ...f, [tab]: '' })); else if (e.key === 'Enter') { e.preventDefault(); firstInView(); } }} />
        {findWords.length > 0 && <span className="find-count" title="Rows in view of this table's rows.">{rowsInView.length} of {rows.length}</span>}
        <span className="spacer" />
        {hidden.length > 0 && <button className="text" onClick={() => showMore(!more)} title={(more ? 'Fewer columns: hide ' : 'More columns: also show ') + hidden.map(c => c.name).join(', ') + '. They keep their values either way.'}>{more ? 'Fewer columns' : `More columns (${hidden.length})`}</button>}
        {tab === 'parameters' && <button className="text" onClick={() => setMatched(n => n + 1)} title="Matched devices...: Reads the circuit for differential pairs, current-mirror loads, matched loads and cascodes and suggests tying their sizes. Press again to refresh the results. You review a diff; nothing is applied automatically.">Matched devices...</button>}
        <button onClick={() => onAgent(tab, [])} title="Draft with agent...: Opens the Agent tab set to draft this tab's rows. Nothing is sent until you write what you need there and press Enter; its proposal is a diff you approve."><Icon name="agent-draft" label="Draft with agent..." /></button>
        <button disabled={!selection.length} onClick={() => onAgent('modify_fields', selection)} title="Modify selected with agent...: Ask the agent for a change to the ticked rows. You review a diff; nothing is applied automatically."><Icon name="agent-modify" label="Modify selected with agent..." /></button>
      </div>
      <div className="task-notes" ref={taskNotes} />
      {tab === 'parameters' && matched > 0 && <MatchedDevices key={matched} config={config} setConfig={setConfig} onClose={() => setMatched(0)} />}
      {/* The lines above the tables give their fact; what explains it is the line's tooltip (record 7.176, user: "reduce or
          delete these texts"). */}
      {tab === 'parameters' && <p className="fact" title={'The initial value is the one read from the circuit. Equal initial values do not imply a binding. '
        + "The policy's proposed action and the executed (projected/quantized) value are both recorded."}>Independent action variables: <b>{validation?.facts?.independent_action_variables ?? '?'}</b> of {rows.length} rows.</p>}
      {tab === 'targets' && <p className="fact spec-probes" title={'Each spec judges its equation, written with Probe IDs, numbers, + - * / ** and brackets '
        + '(e.g. m_supply_power_w / m_osc_frequency_hz). A miss is measured against the size of the limit, unless a Scale is typed (More columns).'}>Probes: {probeIds.length
          ? probeIds.map((id, i) => <Fragment key={id}>{i > 0 && ', '}<code className="probe-id">{id}</code></Fragment>) : 'none yet - fill in the Probes tab first'}</p>}
      {tab === 'targets' && rows.some(r => r.constraint === 'interval' && r.lower === 0) && <p className="hint zero-floor-hint">The margin also measures the distance to 0. If 0 is only a physical floor, choose Margin sides: upper.</p>}
      {error && <p className="error">{error}</p>}
      {pending && <div className="confirm"><h4>Confirm import: {pending.diff.length} changed row{pending.diff.length === 1 ? '' : 's'}{pending.others.length
        ? `, and it replaces the ${pending.others.map(k => IMPORTED_SECTIONS[k]).join(', ')}` : ''}</h4>
        <div className="row"><button onClick={() => applyImport(pending)}>Apply</button><button onClick={() => setPending(null)}>Cancel</button></div>
        {(pending.diff.length > 0 || !pending.others.length) && <DiffView diff={pending.diff} />}</div>}
      <FormulaBar cell={activeRow && !inView(activeRow, at) ? null : barCell} commit={commitBar} back={backToCell} />
      {note && <p className={`${note.warn ? 'warn' : 'hint'} paste-note`}>{note.text}</p>}
      <div className="scroll" onScroll={e => markScrolled(e.currentTarget)}>
        <table className="grid editor" ref={table}>
          <thead><tr><th className="sel"></th>{visible.map(c => <th key={c.name} data-field={c.name} title={c.guidance} onClick={() => setHelp(c)}>{c.label ?? c.name}{c.required ? ' *' : ''}</th>)}<th>Issues</th></tr></thead>
          <tbody onKeyDown={onTableKey} onPaste={onTablePaste}>{rows.map((row, index) => {
            const found = rowIssues(index);
            const point = tab === 'parameters' ? { onMouseEnter: () => pointAt(devicesOf(row)), onMouseLeave: () => pointAt([]),
              onFocus: () => pointAt(devicesOf(row)), onBlur: () => pointAt([]) } : {};
            const tied = tiedCount.get(row[keyField]) ?? 0, leader = leaderOf(row), open = !!openTies[row[keyField]];
            return <tr key={index} data-index={index} hidden={!inView(row, index)} {...point}
              className={[found.some((i: Json) => i.level === 'error' || i.level === 'blocker') ? 'has-error' : '', leader ? 'tied' : ''].filter(Boolean).join(' ') || undefined}>
              <td className="sel"><input type="checkbox" checked={!!selected[row[keyField]]} onChange={e => setSelected(s => ({ ...s, [row[keyField]]: e.target.checked }))} />
                {tied > 0 ? <button className="tie-toggle" aria-expanded={open} onClick={() => setOpenTies(o => ({ ...o, [row[keyField]]: !open }))}
                  title={`${tied} tied row${tied === 1 ? '' : 's'} follow${tied === 1 ? 's' : ''} this one: ${open ? 'fold' : 'show'} ${tied === 1 ? 'it' : 'them'}.`}>{open ? '▾' : '▸'}{tied}</button>
                  : leader ? <span className="tie-mark" title={`Follows ${leader}: its leader's value times the ratio is written.`}>↳</span> : null}</td>
              {/* A field the row does not STATE is shown with the value the backend uses for it (hard = on, active = on ...): a
                  starter row's absent `hard` used to look unchecked although the target is hard. A box the user cleared is null,
                  not absent, and stays empty. */}
              {visible.map(c => <td key={c.name} data-field={c.name} className={at === index && active?.name === c.name ? 'active-cell' : undefined}
                onFocus={() => setActive({ index, name: c.name, key: String(row[keyField] ?? '') })}>{tab === 'targets' && c.name === 'constraint'
                ? <LimitSelect row={row} title={c.guidance} onChange={fields => patch(index, fields)} />
                : <Cell column={c} value={row[c.name] === undefined ? c.default : row[c.name]} onChange={v => update(index, c.name, v)}
                    fixed={fixedOf(row, c)} off={offOf(row, c)} readable={!!READABLE[tab]?.includes(c.name) && BASE_UNITS.has(row.unit)} />}</td>)}
              <td className="issues">{found.map((i: Json, n: number) => <div key={n} className={`issue ${i.level}`} title={i.message}>{i.level}: {i.code}</div>)}</td>
            </tr>; })}</tbody>
        </table>
      </div>
      {help && <p className="guidance" onClick={() => setHelp(null)}><b>{help.name}</b> ({help.type}{help.options ? ': ' + help.options.join(' | ') : ''}) - {help.guidance}</p>}
      {issues.filter((i: Json) => !/\[\d+\]/.test(i.path)).map((i: Json, n: number) => <p key={n} className={`issue ${i.level}`}>{i.level}: {i.message}</p>)}
    </section>
  );
}

// Run-status ticks and bottom-tab switches do not change the editor's inputs.
export const Editors = memo(EditorsView);
