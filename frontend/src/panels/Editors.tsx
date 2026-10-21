import { Icon } from './Icons';
import { Fragment, memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { pointAt } from './CircuitPicture';
import { api, Json, saveJson } from '../api';
import { migrateConfig } from '../store';
import { convert, kindUnit, NUMBER_FORMS, quantity, readQuantity, sameQuantity } from '../units';
import { MatchedDevices } from './MatchedDevices';
import { Cell, LimitSelect } from './cells';
import { DiffView } from './DiffView';
import { exact, FOLLOWER_IGNORES, LABELS, limitLabel, QUANTITY, readNumber, type Section, SECTION_TITLES as TITLES, suggestedScale, unitIn, withFollowers,
  withSaved } from './editorRules';
import { type BarCell, FormulaBar } from './FormulaBar';
import { keep, readKept } from '../kept';
import { RELOAD_SAVED_REQUEST } from './taskChoice';
import { requestSaveAs } from './TaskSave';

const ROW_TABS = Object.keys(TITLES);
/** The start of a new row's ID (Add), in the tab's own word (branch record SIF-50). */
const NEW_ID: Record<Section, string> = { parameters: 'parameter', measurements: 'probe', targets: 'spec' };
/** The sections a whole-configuration import replaces beside the three tables, as the confirmation names them. */
const IMPORTED_SECTIONS: Record<string, string> = { project: 'project labels', circuit: 'circuit source', run: 'run settings',
  output: 'output settings', research: 'research labels' };

const MORE_KEY = 'gator-workbench-editor-more-columns';

/** An issue in a row by the first clause of its message (branch record SIF-5): "The unit of a formula is not checked", where the
 *  row said "equation_unit_unchecked"; the whole message and the code stay in its tooltip. */
const issueHead = (message?: string | null) => String(message ?? '').split(/(?<=[.:;])\s/)[0].replace(/[.:;]$/, '');

/** The table's room under which entering a cell (record 7.372) or Matched devices' answer (branch record SIF-73) folds the
 *  bottom panel: about four rows and the heading. */
const CRAMPED_PX = 200;

/** `taskSlot` / `taskNotes`: where the circuit panel puts "Save task" (right end of the tab line) and its messages (under
 *  the toolbar) - the save sits with the rows it stores (user request 2026-09-22). No "Save" button of its own any more:
 *  the configuration is kept in this browser by itself (store.ts, 0.8 s after each change), and a second "Save" next to
 *  "Save task" only confused.
 *  Record 7.362 (the user's Option D, "go with D"): the editors are the task's card. `taskHead` = the tab line's start, where
 *  the circuit panel names the task (its name opens the Tasks window) and its revision; `taskTools` = the tab line's end, before
 *  Save task (Check now); `taskStatus` = under the toolbar, the task's own lines (loading, blocked, MOCK, the check's result).
 *  "Show circuit" brings the circuit column back beside the rows (`circuitShown`, `onCircuit`: App.tsx). */
function EditorsView({ schema, config, setConfig, undo, redo, canUndo, canRedo, validation, taskSlot, taskNotes, taskHead, taskTools, taskStatus,
  circuitShown, onCircuit, onCramped }:
  { schema: Json; config: Json; setConfig: (c: Json | ((c: Json) => Json)) => void; undo: () => void; redo: () => void; canUndo: boolean; canRedo: boolean;
    validation: Json;
    taskSlot: (element: HTMLElement | null) => void; taskNotes: (element: HTMLElement | null) => void;
    taskHead: (element: HTMLElement | null) => void; taskTools: (element: HTMLElement | null) => void; taskStatus: (element: HTMLElement | null) => void;
    circuitShown: boolean; onCircuit: () => void;
    /** Called when a cell is entered, or Matched devices has drawn its answer (branch record SIF-73), while the table has room
     *  for under about four rows (record 7.372): App folds the bottom panel. */
    onCramped?: () => void }) {
  const [tab, setTab] = useState<Section>('parameters');
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [help, setHelp] = useState<Json>(null);
  // "More columns" shows the columns most rows leave at their default (Specs: soft_weight, active, basis; the Probes' two,
  // conditions and aggregation, were retired in record 7.105). They exist whether shown or not: Add fills them, an
  // import may set them, a task file keeps them.
  const [more, setMore] = useState<boolean>(() => readKept(s => s.getItem(MORE_KEY) === 'shown', () => false));
  const showMore = (now: boolean) => { setMore(now); keep(s => s.setItem(MORE_KEY, now ? 'shown' : 'hidden')); };   // no storage: the choice lasts for this page
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
  // Measured and observed again only when the tick-box header cell is another one (another tab, a new table): it ran at
  // every render - every keystroke - with a layout read and a new ResizeObserver (record 7.275). The observer catches
  // the width changes, and scrolling marks itself (onScroll below).
  const watched = useRef<{ sel: Element | null; watch: ResizeObserver | null }>({ sel: null, watch: null });
  useLayoutEffect(() => {
    const sel = table.current?.querySelector('thead th.sel') ?? null;
    if (watched.current.sel === sel) return;
    watched.current.watch?.disconnect();
    watched.current = { sel, watch: null };
    markScrolled(table.current?.parentElement);
    if (!sel) return;
    const measure = () => table.current?.style.setProperty('--sel-w', `${sel.getBoundingClientRect().width}px`);
    measure();
    watched.current.watch = new ResizeObserver(measure);
    watched.current.watch.observe(sel);
  });
  useEffect(() => () => watched.current.watch?.disconnect(), []);
  // The headers' words are editorRules.ts LABELS, which the import and Matched devices confirmations name the fields by too
  // (branch record SIF-51).
  // Units in words (record 7.208): only Probes have a Unit column; the values of Parameters and Specs carry theirs. A plain
  // number is in the row's own unit, not in the prefix its cell shows ("2" in a row stored in m showing "1 um" is 2 m): each
  // cell's tooltip names that unit (branch record SIF-49; "the unit the row shows" was left from the Unit column).
  const VALUE_HELP = ' Written with its unit (450 nm, 400 uA). Type 450n, 0.45 um or 0.4mA; a plain number is in the row\'s own unit, '
    + 'not in the prefix the cell shows (each cell\'s tooltip names that unit). '
    + 'A Parameters row is in the unit of its parameter (w, l: a length), a Spec in its Probe\'s: a value of another quantity is refused.';
  const columns: Json[] = schema.editors[tab].map((c: Json) => ({ ...c, label: c.label ?? LABELS[tab]?.[c.name] }))
    .map((c: Json) => c.name === 'unit' ? { ...c, guidance: 'The unit of what this Probe measures, chosen from the list (V, A, Hz, dB, deg...). '
      + 'A Spec on this Probe takes it.' } : QUANTITY[tab]?.includes(c.name) ? { ...c, guidance: (c.guidance ?? '') + VALUE_HELP } : c)
    .map((c: Json) => tab !== 'targets' ? c
    : c.name === 'constraint' ? { ...c, guidance: c.guidance + ' "then lower / higher is better" is the objective: among the designs that pass '
      + 'every hard spec, the best one is the lowest / highest here (one spec at most); with an Objective bonus weight above 0 (Reward and '
      + 'conditions) the reward also pushes it past the limit.' }
    : c.name === 'normalization_scale' ? { ...c, guidance: 'How far outside its limit a value counts as a miss of 1. Empty: as far as the limit itself. dB rows: 6 (a factor of 2), so with a limit of 30 dB, 24 dB is a miss of 1. Smaller = stricter. Pass or fail depends on the limits only.' } : c);
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

  // The unit a row's values are read in (record 7.208: no Unit column in Parameters and Specs): its own, unless what the row
  // is says another quantity - a parameter of a known kind (w, l: m), a Spec on one Probe (the Probe's unit) - or it has none.
  const expectedUnit = (row: Json): string | null => tab === 'parameters' ? kindUnit(row.parameter_name)
    : tab === 'targets' ? (config.measurements ?? []).find((m: Json) => m.measurement_id === String(row.equation ?? '').trim())?.unit || null : null;
  const effectiveUnit = (row: Json): string | null => { const e = expectedUnit(row); return e && !sameQuantity(row.unit, e) ? e : row.unit ?? null; };
  // One change of one row, several fields at once (the constraint list sets the limit and the objective): one Undo step.
  const patch = (index: number, fields: Json) => setConfig((c: Json) => withFollowers(tab, c, new Map([[index, fields]])));
  // A unit changed to another of the same quantity (um -> nm, record 7.208): the row's numbers move with it, exactly, so every
  // value stays the same; to another quantity they stay as they are.
  const update = (index: number, name: string, value: Json) => {
    const row = rows[index], moved: Json = { [name]: value };
    if (name === 'unit' && row) for (const f of QUANTITY[tab] ?? []) { const n = convert(row[f], row.unit, value); if (n !== null && n !== row[f]) moved[f] = n; }
    patch(index, moved);
  };
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
    // Named as the tab is (probe_3, spec_4), not by the section key (measurement_3, target_4; branch record SIF-50).
    const used = new Set(rows.map(r => r[keyField]));
    let n = rows.length + 1;
    while (used.has(`${NEW_ID[tab]}_${n}`)) n += 1;
    row[keyField] = `${NEW_ID[tab]}_${n}`;
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
  function jsonImport() {
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
          throw new Error(`every ${TITLES[tab]} row needs its ${LABELS[tab][keyField]} ("${keyField}" in the file)`);
        const next = migrateConfig(whole ? incoming : { ...config, [tab]: rowsIn });
        const { diff } = await api.diff(config, next);
        const others = Object.keys(IMPORTED_SECTIONS).filter(k => JSON.stringify(config[k] ?? null) !== JSON.stringify(next[k] ?? null));
        setPending({ next, diff, others, rows: whole ? null : { section: tab, value: next[tab] } });
      } catch (e: any) {
        // A file that is not JSON is said so, with what to choose, where the browser's parser text stood ("Unexpected token 'a',
        // "abc" is not valid JSON"); a missing ID names its header, Spec ID, beside the file's key (branch record SIF-50).
        setError(e instanceof SyntaxError ? 'Import failed: the file is not JSON. Choose a file written by Export JSON, or a list of rows.'
          : `Import failed: ${e.message}`);
      }
    };
    const applyImport = (p: NonNullable<typeof pending>) => {
      const { rows } = p;
      setConfig(rows ? (c: Json) => ({ ...c, [rows.section]: rows.value }) : p.next);
      setPending(null);
    };
    return { importJson, applyImport };
  }
  const { importJson, applyImport } = jsonImport();
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
    ? `A Maestro output's Probe ID is m_ + its output name (saving the task names it so): it follows the name, and so do the spec equations that use it.` : null;
  const offOf = (row: Json, c: Json): string | null => tab === 'parameters' && row.binding_group && FOLLOWER_IGNORES.includes(c.name)
    ? `Follows ${row.binding_group}: its leader's value times the ratio is written, so this field does nothing on this row.` : null;
  // What an empty number box means, in a word (branch record SIF-49): a bare "-" said neither "no limit" (a one-sided spec's
  // other side) nor "as far as the limit itself" (an empty Scale). A follower's greyed field keeps "-": its tooltip says why.
  const emptyOf = (row: Json, c: Json): string | undefined => offOf(row, c) ? undefined
    : tab === 'targets' && (c.name === 'lower' || c.name === 'upper') ? 'no limit' : c.name === 'normalization_scale' ? 'auto' : undefined;
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
      : value == null ? '' : typeof value === 'object' ? JSON.stringify(value)
      : typeof value === 'number' && QUANTITY[tab]?.includes(c.name) ? quantity(value, activeRow.unit) : String(value);
    return { id: `${tab}|${at}|${c.name}`, where: `${c.label ?? c.name} · ${activeRow[keyField] ?? `row ${at + 1}`}`, text, editable: why === null,
      why: why ?? '', format: `${c.name} (${c.type}${c.options ? ': ' + c.options.join(' | ') : ''}${c.required ? ', required' : ''}) - ${c.guidance ?? ''}` };
  })() : null;
  // The bar's text as the cell would take it: a number as the number cell reads it, a list as JSON; one change, one Undo step.
  const commitBar = (text: string): string | null => {
    if (!activeRow || !activeColumn) return null;
    const c = activeColumn;
    let value: Json;
    if ((c.type === 'number' || c.type === 'integer') && QUANTITY[tab]?.includes(c.name)) {
      const unit = effectiveUnit(activeRow), read = readQuantity(text, unit);
      if ('problem' in read) return read.problem;
      value = read.value ?? (c.nullable ? null : 0);
      const takes = read.unit ?? (unit && unit !== activeRow.unit ? unit : null);
      if (takes) { patch(at, { [c.name]: value, unit: takes }); return null; }
    } else if (c.type === 'number' || c.type === 'integer') {
      const s = text.trim(), n = readNumber(s);
      // a unitless number (Ratio, Soft weight): no Unit column to point at (branch record SIF-49)
      if (s !== '' && n === undefined) return `"${s}" is not a number: ${NUMBER_FORMS}.`;
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
    // Ctrl+Z and Ctrl+Y (or Ctrl+Shift+Z) are the toolbar's Undo and Redo here, as in a spreadsheet (record 7.188): a cell's typing
    // is one Undo step, so the whole entry goes back at once; the formula bar keeps the browser's own undo of its text.
    if ((e.ctrlKey || e.metaKey) && !e.altKey && /^[zy]$/i.test(e.key)) {
      e.preventDefault();
      (e.key.toLowerCase() === 'y' || e.shiftKey ? redo : undo)();
      return;
    }
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
  function sheetEdits() {
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
      let kept = 0, other = 0;
      for (const i of targets) {
        if (fixedOf(rows[i], c) || offOf(rows[i], c)) { kept += 1; continue; }
        // a quantity goes in the unit the target row stores (record 7.208: 600 nm into a row in m is 6e-7); another quantity is kept
        let filled = value;
        if (typeof value === 'number' && QUANTITY[tab]?.includes(c.name) && (rows[i].unit ?? '') !== (rows[from].unit ?? '')) {
          filled = convert(value, rows[from].unit, rows[i].unit);
          if (filled === null) { other += 1; continue; }
        }
        if (exact(rows[i][c.name] === undefined ? c.default : rows[i][c.name]) !== exact(filled))
          changes.set(i, { [c.name]: filled != null && typeof filled === 'object' ? JSON.parse(JSON.stringify(filled)) : filled });
      }
      if (changes.size) setConfig((cfg: Json) => withFollowers(tab, cfg, changes));
      const what = `${c.label ?? c.name} = ${typeof value === 'number' && QUANTITY[tab]?.includes(c.name) ? quantity(value, rows[from].unit) : shortText(value)} of ${rows[from][keyField]}`;
      setNote({ text: [changes.size ? `Filled ${changes.size} cell${changes.size === 1 ? '' : 's'} with ${what} (one Undo step).`
        : targets.length > kept ? `Nothing to fill: the cell${targets.length - kept === 1 ? ' holds' : 's hold'} ${what} already.` : 'Nothing filled.',
        kept ? `${kept} cell${kept === 1 ? ' that follows' : 's that follow'} another field kept.` : '',
        other ? `${other} cell${other === 1 ? '' : 's'} of another quantity kept.` : ''].filter(Boolean).join(' '), warn: other > 0 });
    };
    // Ctrl+C copies out, as in a spreadsheet (record 7.184): in a ticked row, the ticked rows in view - every column in view, a
    // header line first - as tab-separated lines for Excel; otherwise the cell alone. A value with its unit, as the cell writes
    // it (record 7.208: there is no Unit column to say it; a paste reads it back exactly); other numbers as stored, a limit as
    // its sign. The Copy button takes the ticked rows in view, or every row in view.
    const cellText = (row: Json, c: Json) => {
      const value = row[c.name] === undefined ? c.default : row[c.name];
      return (c.name === 'nominal_only' ? (value ? 'Nominal only' : 'All planned conditions')
        : typeof value === 'number' && QUANTITY[tab]?.includes(c.name) ? quantity(value, row.unit) : exact(value)).replace(/[\t\r\n]+/g, ' ');
    };
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
    const readAs = (c: Json, raw: string, row: Json): { value?: Json; problem?: string; unit?: string } => {
      const s = raw.trim();
      if (c.name === 'nominal_only') return /^nominal/i.test(s) ? { value: true } : /^all/i.test(s) ? { value: false } : { problem: `"${s}" in ${c.label ?? c.name}` };
      if (c.type === 'boolean') return /^(true|yes|on|1|x|✓)$/i.test(s) ? { value: true } : /^(false|no|off|0|)$/i.test(s) ? { value: false } : { problem: `"${s}" in ${c.label ?? c.name}` };
      if (c.name === 'constraint' && tab === 'targets') {
        const limit = ({ '>=': '>=', '≥': '>=', '<=': '<=', '≤': '<=', interval: 'interval' } as Record<string, string>)[s.toLowerCase()];
        return limit ? { value: limit } : { problem: `"${s}" in ${c.label ?? c.name}` };
      }
      if (c.options) {
        const option = c.options.find((o: string) => o.toLowerCase() === s.toLowerCase());
        return option !== undefined ? { value: option } : s === '' && c.nullable ? { value: null } : { problem: `"${s}" in ${c.label ?? c.name}` };
      }
      if ((c.type === 'number' || c.type === 'integer') && QUANTITY[tab]?.includes(c.name)) {
        if (s === '') return c.nullable ? { value: null } : {};
        const unit = effectiveUnit(row), read = readQuantity(s, unit);
        return 'problem' in read ? { problem: `"${s}" in ${c.label ?? c.name}` }
          : { value: read.value, unit: read.unit ?? (unit && unit !== row.unit ? unit : undefined) };
      }
      if (c.type === 'number' || c.type === 'integer') {
        if (s === '') return c.nullable ? { value: null } : {};
        const n = readNumber(s);
        return n !== undefined ? { value: n } : { problem: `"${s}" in ${c.label ?? c.name}` };
      }
      if (c.type === 'array' || c.type === 'object') {
        if (s === '') return { value: null };
        try { return { value: JSON.parse(s) }; } catch { return { problem: `"${s}" in ${c.label ?? c.name}` }; }
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
          const read = readAs(c, raw, row);
          if (read.problem) problems.push(read.problem);
          else if ('value' in read) { changes.set(index, { ...(changes.get(index) ?? {}), [c.name]: read.value, ...(read.unit ? { unit: read.unit } : {}) }); cells += 1; }
        });
      });
      if (changes.size) setConfig((cfg: Json) => withFollowers(tab, cfg, changes));
      const said = [cells ? `Pasted ${cells} cell${cells === 1 ? '' : 's'} into ${changes.size} row${changes.size === 1 ? '' : 's'} (one Undo step).` : 'Nothing pasted.',
        header ? 'The header line was skipped.' : '',
        problems.length ? `Not read, left as they were: ${problems.slice(0, 4).join(', ')}${problems.length > 4 ? ` and ${problems.length - 4} more` : ''}.` : '',
        kept ? `${kept} cell${kept === 1 ? ' that follows' : 's that follow'} another field kept.` : '',   // as fill down says it (branch record SIF-50)
        beyond ? `${beyond} line${beyond === 1 ? '' : 's'} below the last row left out: Add rows first.` : ''].filter(Boolean).join(' ');
      setNote({ text: said, warn: problems.length + beyond > 0 });
    };
    return { shortText, fillDown, copyOut, onTablePaste };
  }
  const { shortText, fillDown, copyOut, onTablePaste } = sheetEdits();

  // Rows not saved in the task (record 7.222, user: "In the parameter probe and spec windows, highlight the rows that are
  // unsaved"): validation compares the rows with the saved task's file, as the check before a run does, and names per table
  // the rows new here, the rows changed - with the saved values - and the saved rows deleted here. Marked by row ID, half a
  // second after a change like every validation mark; nothing for a task that is not saved (a cell read, an ngspice task).
  function unsavedMarks() {
    const unsavedIn = (s: Section): Json => validation?.unsaved_rows?.sections?.[s] ?? null;
    const unsaved = unsavedIn(tab);
    const isNew = (row: Json) => !!unsaved?.added?.includes(String(row[keyField] ?? ''));
    const changeOf = (row: Json): Json => unsaved?.changed?.[String(row[keyField] ?? '')] ?? null;
    // Specs show the objective inside the Limit list: a saved objective is that cell's.
    const cellOf = (field: string) => tab === 'targets' && field === 'direction_after_feasible' ? 'constraint' : field;
    // A saved value as its cell writes it: a quantity in the saved row's unit, a limit in words, a tick as on or off.
    const savedText = (row: Json, change: Json, field: string): string => {
      const fields = change.fields, value = fields[field];
      if (tab === 'targets' && cellOf(field) === 'constraint')
        return limitLabel('constraint' in fields ? fields.constraint : row.constraint,
          ('direction_after_feasible' in fields ? fields.direction_after_feasible : row.direction_after_feasible) ?? 'none');
      if (value == null) return '(empty)';
      if (field === 'nominal_only') return value ? 'Nominal only' : 'All planned conditions';
      if (typeof value === 'boolean') return value ? 'on' : 'off';
      return typeof value === 'number' && QUANTITY[tab]?.includes(field) ? quantity(value, change.unit ?? row.unit) : shortText(value);
    };
    const savedIn = (row: Json, name: string): string | null => {
      const change = changeOf(row), field = change && Object.keys(change.fields).find(f => cellOf(f) === name);
      return field ? savedText(row, change, field) : null;
    };
    // What a marked row says on its tick-box cell: new, or which fields changed and what the task holds - also of the columns
    // not in view (a Probe's unit followed by a Spec, a column behind More columns).
    const rowNote = (row: Json): string | null => {
      if (isNew(row)) return 'New row, not in the saved task: Save as stores it in a new task.';
      const change = changeOf(row);
      if (!change) return null;
      const cells = [...new Set(Object.keys(change.fields).map(cellOf))];
      const label = (name: string) => columns.find(c => c.name === name)?.label ?? name;
      return `Changed since the task was saved: ${cells.map(name => `${label(name)} (saved: ${savedIn(row, name)})`).join(', ')}.`;
    };
    // A tab's mark: how many of its rows are not saved, and the saved rows deleted here - which no row can show.
    const unsavedTitle = (s: Section): string | null => {
      const u = unsavedIn(s);
      if (!u) return null;
      const changed = Object.keys(u.changed ?? {}).length, added = (u.added ?? []).length, removed: string[] = u.removed ?? [];
      const parts = [changed ? `${changed} changed` : '', added ? `${added} new` : '',
        removed.length ? `${removed.length} saved row${removed.length === 1 ? '' : 's'} deleted here (${removed.slice(0, 3).join(', ')}${removed.length > 3 ? ', ...' : ''})` : '',
        u.reordered ? 'rows in another order' : ''].filter(Boolean);
      return parts.length ? `Not saved in the task: ${parts.join(', ')}. Save as stores the rows in a new task; Reload saved values brings back the saved ones.` : null;
    };
    return { isNew, changeOf, savedIn, rowNote, unsavedTitle };
  }
  const { isNew, changeOf, savedIn, rowNote, unsavedTitle } = unsavedMarks();
  // Beside the task's name (record 7.362): whether the rows are the saved task's - only for a saved task, which validation
  // compares with its file (record 7.222); the tabs' dots say where they differ.
  const savedState = !validation?.unsaved_rows?.sections ? null : (Object.keys(TITLES) as Section[]).some(s => unsavedTitle(s)) ? 'not saved' : 'saved';
  // "not saved" opens what differs, table by table, with Reload saved values and Save as (record 7.372): the tabs' dots said
  // it in their tooltips only.
  const [changesOpen, setChangesOpen] = useState(false);
  const [saveAsWhy, setSaveAsWhy] = useState<string | null>(null);        // why its Save as could not start (record 7.376)
  useEffect(() => { if (savedState !== 'not saved') setChangesOpen(false); }, [savedState]);
  useEffect(() => { if (!changesOpen) setSaveAsWhy(null); }, [changesOpen]);
  const idList = (list: string[]) => `${list.slice(0, 4).join(', ')}${list.length > 4 ? ', ...' : ''}`;
  const changesIn = (s: Section): string | null => {
    const u: Json = validation?.unsaved_rows?.sections?.[s];
    if (!u) return null;
    const changed = Object.keys(u.changed ?? {}), added: string[] = u.added ?? [], removed: string[] = u.removed ?? [];
    const parts = [changed.length ? `${changed.length} changed (${idList(changed)})` : '', added.length ? `${added.length} new (${idList(added)})` : '',
      removed.length ? `${removed.length} saved row${removed.length === 1 ? '' : 's'} deleted here (${idList(removed)})` : '', u.reordered ? 'rows in another order' : ''].filter(Boolean);
    return parts.length ? parts.join(', ') : null;
  };

  // The table (`room`, its scroll box) left under about four rows on a wide page whose bottom panel is open: App folds the
  // panel (record 7.372) - when a cell is entered, and when Matched devices has drawn its answer above the table (branch record
  // SIF-73: at 1366 x 768 with a message line, its box left the table its heading alone and no cell to enter).
  const foldIfCramped = (room?: HTMLElement | null) => {
    if (onCramped && room && window.innerWidth > 1100 && room.clientHeight < CRAMPED_PX && !room.closest('.layout.bottom-folded')) onCramped();
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
          Each editor has a colour of its own (record 7.158): its tab, its table's header row, and its ids where another editor shows them.
          A tab holding rows not saved in the task carries a dot, its tooltip says how many (record 7.222). */}
      <div className="tabs"><span className="task-head" ref={taskHead} />
        {savedState && <span className="task-saved-slot">{savedState === 'saved'
          ? <span className="task-saved" title="The rows of Parameters, Probes and Specs are the saved task's.">saved</span>
          : <button className={`task-saved unsaved${changesOpen ? ' open' : ''}`} aria-expanded={changesOpen} onClick={() => setChangesOpen(o => !o)}
              title="Not saved: press to see what differs from the saved task, with Reload saved values and Save as.">not saved</button>}</span>}
        {(Object.keys(TITLES) as Section[]).map(s => { const notSaved = unsavedTitle(s);
        return <button key={s} data-editor={s} className={[s === tab ? 'active' : '', notSaved ? 'has-unsaved' : ''].filter(Boolean).join(' ')}
          title={notSaved ?? undefined} onClick={() => { if (s !== tab) setMatched(0); setTab(s); setSelected({}); }}>{TITLES[s]} ({(config[s] ?? []).length})</button>; })}
        <span className="tab-actions">
          <button className={`circuit-toggle${circuitShown ? ' active' : ''}`} aria-pressed={circuitShown} onClick={onCircuit}
            title={circuitShown ? 'Hide circuit: The circuit column folds away and the rows take the width again.'
              : "Show circuit: The circuit's labels, picture, notes and hierarchy beside the rows - a Parameters row pointed at lights its devices in the picture."}>
            {circuitShown ? 'Hide circuit' : 'Show circuit'}</button>
          <span className="task-tools" ref={taskTools} /><span className="task-save-slot" ref={taskSlot} /></span></div>
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
        {/* The box shrinks with the window and its count sits inside it (record 7.185): the toolbar stays on one line at 1366 px. */}
        <span className={`find-box${findWords.length ? ' finding' : ''}`}>
          <input type="search" className="find-rows" placeholder="Find rows" aria-label="Find rows" value={find[tab] ?? ''}
            title={'Find rows: only the rows whose text cells in view (ID, instance path, expression, equation, notes ...) hold every word typed stay in view, '
              + 'folded or not; not case-sensitive. Enter goes to the first of them, Esc clears the box.'}
            onChange={e => setFind(f => ({ ...f, [tab]: e.target.value }))}
            onKeyDown={e => { if (e.key === 'Escape') setFind(f => ({ ...f, [tab]: '' })); else if (e.key === 'Enter') { e.preventDefault(); firstInView(); } }} />
          {findWords.length > 0 && <span className="find-count" title={`${rowsInView.length} of ${rows.length} rows in view`}>{rowsInView.length}/{rows.length}</span>}</span>
        <span className="spacer" />
        {hidden.length > 0 && <button className="text" onClick={() => showMore(!more)} title={(more ? 'Fewer columns: hide ' : 'More columns: also show ') + hidden.map(c => c.label ?? c.name).join(', ') + '. They keep their values either way.'}>{more ? 'Fewer columns' : `More columns (${hidden.length})`}</button>}
        {tab === 'parameters' && <button className="text" onClick={() => setMatched(n => n + 1)} title="Matched devices...: Reads the circuit for differential pairs, current-mirror loads, matched loads and cascodes and suggests tying their sizes. Press again to refresh the results. You review a diff; nothing is applied automatically.">Matched devices...</button>}
      </div>
      <div className="task-status" ref={taskStatus} />
      {changesOpen && savedState === 'not saved' && <div className="unsaved-summary" role="region" aria-label="Rows not saved in the task">
        <p><b>Not saved in the task:</b></p>
        <ul>{(Object.keys(TITLES) as Section[]).map(s => { const said = changesIn(s); return said && <li key={s}>
          <button className="item-link" onClick={() => { if (s !== tab) setMatched(0); setTab(s); setSelected({}); }} title={`Show ${TITLES[s]}`}>{TITLES[s]}</button>: {said}</li>; })}</ul>
        <div className="row">
          <button onClick={() => window.dispatchEvent(new CustomEvent(RELOAD_SAVED_REQUEST))}
            title="Reload saved values: The saved rows of the task come back into the editors. Asks first; Undo takes it back.">Reload saved values</button>
          <button className="primary" onClick={() => { const asked = requestSaveAs(); setSaveAsWhy(asked.taken ? null : asked.why); }}
            title="Save as: The rows here become a new task; it asks for the name.">Save as...</button>
          <button onClick={() => setChangesOpen(false)} title="Close: The rows stay as they are.">Close</button>
        </div>
        {saveAsWhy && <p className="warn">Save as cannot start now: {saveAsWhy}.</p>}
      </div>}
      <div className="task-notes" ref={taskNotes} />
      {tab === 'parameters' && matched > 0 && <MatchedDevices key={matched} config={config} setConfig={setConfig} onClose={() => setMatched(0)}
        onShown={() => foldIfCramped(table.current?.parentElement)} />}
      {/* The lines above the tables give their fact; what explains it is the line's tooltip (record 7.176, user: "reduce or
          delete these texts"). The rows the optimizer changes are "searched", as the task's Details call them (branch record
          SIF-40), where this line said "Independent action variables" (branch record SIF-50). A sentence with the optimizer in
          it (branch record SIF-73): "Searched rows: 7 of 66." under the empty Find rows box, beside the 7 rows a fold leaves
          in view, read as the result of a search. "..." only before the first validation answer: App keeps the last answer
          while the next one is on its way, so a missing count after that means validation could not count (a tie to a row
          that does not exist, a cycle, a refused configuration) and reads "?". */}
      {tab === 'parameters' && <p className="fact" title={'The rows the optimizer changes itself; the others follow a tied row or stay fixed. '
        + 'The initial value is the one read from the circuit. Equal initial values do not imply a binding. '
        + "The policy's proposed action and the executed (projected/quantized) value are both recorded."}>The optimizer searches <b>{validation == null ? '...'
          : (validation.facts?.independent_action_variables ?? '?')}</b> of {rows.length} rows.</p>}
      {tab === 'targets' && <p className="fact spec-probes" title={'Each spec judges its equation, written with Probe IDs, numbers, + - * / ** and brackets '
        + '(e.g. m_supply_power_w / m_osc_frequency_hz). A miss is measured against the size of the limit, unless a Scale is typed (More columns).'}>Probes: {probeIds.length
          ? probeIds.map((id, i) => <Fragment key={id}>{i > 0 && ', '}<code className="probe-id">{id}</code></Fragment>) : 'none yet - fill in the Probes tab first'}</p>}
      {/* The zero-floor hint (reward v2.1 B3) names its rows and goes once their Margin sides is upper: it stayed after the
          user followed it, named no row, and its column hides behind More columns (branch record SIF-50). */}
      {tab === 'targets' && (() => {
        const zero = rows.filter(r => r.constraint === 'interval' && r.lower === 0 && r.margin_sides !== 'upper').map(r => r[keyField]);
        return zero.length > 0 && <p className="hint zero-floor-hint">{zero.join(', ')}: the margin also measures the distance to 0. If 0 is only a physical floor, set Margin sides to upper (More columns).</p>;
      })()}
      {error && <p className="error">{error}</p>}
      {pending && <div className="confirm"><h4>Confirm import: {pending.diff.length} changed row{pending.diff.length === 1 ? '' : 's'}{pending.others.length
        ? `, and it replaces the ${pending.others.map(k => IMPORTED_SECTIONS[k]).join(', ')}` : ''}</h4>
        <div className="row"><button onClick={() => applyImport(pending)}>Apply</button><button onClick={() => setPending(null)}>Cancel</button></div>
        {(pending.diff.length > 0 || !pending.others.length) && <DiffView diff={pending.diff} unitOf={unitIn(config, schema.section_keys ?? {})} />}</div>}
      <FormulaBar cell={activeRow && !inView(activeRow, at) ? null : barCell} commit={commitBar} back={backToCell} />
      {note && <p className={`${note.warn ? 'warn' : 'hint'} paste-note`}>{note.text}</p>}
      <div className="scroll" onScroll={e => markScrolled(e.currentTarget)}
        onFocusCapture={e => {      // a cell entered while the table has room for under about four rows (record 7.372)
          foldIfCramped(e.currentTarget); }}>
        <table className="grid editor" ref={table}>
          <thead><tr><th className="sel"></th>{visible.map(c => <th key={c.name} data-field={c.name} title={c.guidance ? `${c.name}: ${c.guidance}` : c.name} onClick={() => setHelp(c)}>{c.label ?? c.name}{c.required ? ' *' : ''}</th>)}<th>Issues</th></tr></thead>
          <tbody onKeyDown={onTableKey} onPaste={onTablePaste}>{rows.map((row, index) => {
            const found = rowIssues(index);
            const point = tab === 'parameters' ? { onMouseEnter: () => pointAt(devicesOf(row)), onMouseLeave: () => pointAt([]),
              onFocus: () => pointAt(devicesOf(row)), onBlur: () => pointAt([]) } : {};
            const tied = tiedCount.get(row[keyField]) ?? 0, leader = leaderOf(row), open = !!openTies[row[keyField]];
            // Not saved in the task (record 7.222): the row is tinted, a changed cell more; folded tied rows that are not saved
            // colour their leader's count.
            const change = changeOf(row), note = rowNote(row);
            const tiedNotSaved = tied > 0 ? rows.filter(r => leaderOf(r) === row[keyField] && (isNew(r) || changeOf(r))).length : 0;
            return <tr key={index} data-index={index} hidden={!inView(row, index)} {...point}
              className={[found.some((i: Json) => i.level === 'error' || i.level === 'blocker') ? 'has-error' : '', leader ? 'tied' : '',
                isNew(row) ? 'unsaved-new' : change ? 'unsaved-changed' : ''].filter(Boolean).join(' ') || undefined}>
              <td className="sel" title={note ?? undefined}><input type="checkbox" checked={!!selected[row[keyField]]} onChange={e => setSelected(s => ({ ...s, [row[keyField]]: e.target.checked }))} />
                {tied > 0 ? <button className={`tie-toggle${tiedNotSaved ? ' unsaved' : ''}`} aria-expanded={open} onClick={() => setOpenTies(o => ({ ...o, [row[keyField]]: !open }))}
                  title={`${tied} tied row${tied === 1 ? '' : 's'} follow${tied === 1 ? 's' : ''} this one: ${open ? 'fold' : 'show'} ${tied === 1 ? 'it' : 'them'}.`
                    + (tiedNotSaved ? ` ${tiedNotSaved} of them ${tiedNotSaved === 1 ? 'is' : 'are'} not saved in the task.` : '')}>{open ? '▾' : '▸'}{tied}</button>
                  : leader ? <span className="tie-mark" title={`Follows ${leader}: its leader's value times the ratio is written.`}>↳</span> : null}</td>
              {/* A field the row does not STATE is shown with the value the backend uses for it (hard = on, active = on ...): a
                  starter row's absent `hard` used to look unchecked although the target is hard. A box the user cleared is null,
                  not absent, and stays empty. */}
              {visible.map(c => { const saved = change ? savedIn(row, c.name) : null;
                return <td key={c.name} data-field={c.name} className={[at === index && active?.name === c.name ? 'active-cell' : '', saved !== null ? 'unsaved-cell' : ''].filter(Boolean).join(' ') || undefined}
                onFocus={() => setActive({ index, name: c.name, key: String(row[keyField] ?? '') })}>{tab === 'targets' && c.name === 'constraint'
                ? <LimitSelect row={row} title={withSaved(saved, c.guidance)} onChange={fields => patch(index, fields)} />
                : <Cell column={c} value={row[c.name] === undefined ? c.default : row[c.name]} onChange={v => update(index, c.name, v)}
                    fixed={fixedOf(row, c)} off={offOf(row, c)} unit={QUANTITY[tab]?.includes(c.name) ? effectiveUnit(row) : undefined}
                    stored={row.unit ?? null} onPatch={fields => patch(index, fields)} tell={text => setNote({ text, warn: true })} saved={saved}
                    placeholder={emptyOf(row, c)} />}</td>; })}
              <td className="issues">{found.map((i: Json, n: number) => <div key={n} className={`issue ${i.level}`} data-code={i.code}
                title={`${i.message}\n(${i.level}: ${i.code})`}><b>{i.level}</b> {issueHead(i.message)}</div>)}</td>
            </tr>; })}</tbody>
        </table>
      </div>
      {help && <p className="guidance" onClick={() => setHelp(null)}><b>{help.label ?? help.name}</b> ({help.label ? `${help.name}, ` : ''}{help.type}{help.options ? ': ' + help.options.join(' | ') : ''}) - {help.guidance}</p>}
      {issues.filter((i: Json) => !/\[\d+\]/.test(i.path)).map((i: Json, n: number) => <p key={n} className={`issue ${i.level}`}>{i.level}: {i.message}</p>)}
    </section>
  );
}

// Run-status ticks and bottom-tab switches do not change the editor's inputs.
export const Editors = memo(EditorsView);
