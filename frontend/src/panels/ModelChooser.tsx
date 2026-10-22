import { Fragment, useEffect, useMemo, useRef, useState } from 'react';
import { useRequest } from '../store';
import { api, copy, Json } from '../api';
import { folderName, plural, stamp } from '../format';
import { childrenOf, designName, ENCODER_SHORT, historyOf, pointText, startedFrom } from '../lineage';
import { openRunsAt } from '../openAt';
import { CircuitGraphView } from './CircuitGraphView';
import { FolderMoveBar, Folders, useFolders } from './Folders';
import { TableHead, useTableView } from './TableView';
import { ModelStructure } from './ModelStructure';
import { CompatibilityList, compatibilityMode } from './CompatibilityList';
import { runMode } from './rlModelText';
import { pointKey, readSavePoint, withSavePoint } from '../savePoint';
import { styled } from './popupWindow';
/** When, as the Runs and Tasks windows and the model's facts write it - 2026-10-20 13:09:10 (branch record SIF-17; the table
 *  wrote "20 Oct, 13:09:10"). */
const when = (utc?: string | null) => stamp(utc) ?? 'unknown time';

/** The saved models of the RL model window (record 7.265; plan "RL model window: the load-model window, renewed"). A saved
 *  model is the RL model one run saved, in that run's folder; every save is a "save point". One row per saved model, with
 *  folders (the `models` kind, record 7.263), a filter and sortable columns, like the Tasks and Runs windows.
 *
 *  A click only inspects: the row's Details open under it - its save points, Rename, its compatibility with the draft's task,
 *  its network structure and circuit graph view, its relationships and history. Using one is a press: "Use this save point",
 *  or a double click on the row for its newest one, sets the draft's source to exactly that save point - a concrete id,
 *  never "latest" - with the model's network and component list, as one Undo step (Right.tsx `useSavePoint`). `usable`: the
 *  Mode loads a model (Fine-tune, Evaluate only); in New model the table is for looking only, as "Look at a saved model" was.
 *  Every model has a name of its own (record 7.225): the Name box in its Details renames it (POST /api/runs/model/rename). */

const KIND: Record<string, string> = { periodic: 'automatic save', manual: 'saved with "Save now"', pause: 'saved at pause', stop: 'saved at stop',
  final: 'saved at the end of the run', safety: 'safety save' };
/** A network in one line: "graph_transformer 16/2/1". `short`: the table's form ("GT 16/2/1", as the model line beside the RL
 *  model button writes it): the window has room for it. */
export const netLabel = (n: Json, short = false) => n?.encoder_type ? `${short ? ENCODER_SHORT[n.encoder_type] ?? n.encoder_type : n.encoder_type} ${n.hidden_dim}/${n.heads}/${n.layers}${n.structural_encoding && n.structural_encoding !== 'none' ? ` · ${n.structural_encoding}` : ''}` : 'unknown network';
const netShort = (n: Json) => netLabel(n, true);
/** Its size, under its design's name (branch record SIF-1): hidden width / heads / layers, and RWSE where it has it. */
const sizeLabel = (n: Json) => n?.encoder_type ? `${n.hidden_dim}/${n.heads}/${n.layers}${n.structural_encoding && n.structural_encoding !== 'none' ? ` · ${String(n.structural_encoding).toUpperCase()}` : ''}` : '?';
// A name or task key may break after ':' and '_' ("synthetic:" / "gpdk045_" / "ota5"), never inside a word.
const breakable = (text: string) => text.split(/(?<=[:_])/).map((part, i) => <Fragment key={i}>{i > 0 && <wbr />}{part}</Fragment>);
/** The name a model is listed under. */
export const modelName = (m: Json): string => m?.model_label ?? m?.task_name ?? m?.task_id ?? folderName(m?.run_dir ?? '');
/** The name of the model a run folder saved: as the run list names it, or the folder's own name when it is not listed. */
export const modelNameAt = (runs: Json[], dir: string): string => { const row = runs.find(r => r.run_dir === dir); return row ? modelName(row) : folderName(dir); };
/** The task by the name the page gives it - without "real:", as since record 7.249 (branch record SIF-13); the key on hover. */
const trainedKey = (m: Json) => m.circuit_task ?? m.task_key ?? m.circuit_class ?? 'unknown task';
const trainedOn = (m: Json) => m.run_kind === 'offline_pretraining' ? 'multi-task (offline)' : String(trainedKey(m)).replace(/^real:/, '');
export const RESTORABLE: Record<string, string> = { full_state: 'full state', weights_only: 'weights only' };
/** What each one allows: the Restorable column's help, and the model in use's facts after the bold word (branch record SIF-80:
 *  "Restorable full state" there with no meaning, where the Network row beside it says its own). */
export const RESTORABLE_MEANS: Record<string, string> = { full_state: 'the run that saved it can be continued exactly', weights_only: 'usable for Fine-tune and Evaluate only' };
/** A full save point of an older optimizer source, in the Runs window's words (review of branch record SIF-80): Continue needs
 *  exactly the source that wrote it (record 7.221), so "continued exactly" holds only for a save point of the source of now. */
export const RESTORABLE_OLDER = 'written by an older version of the optimizer code: only that version can continue it; Fine-tune and Evaluate only still load its model';

type Column = { key: string; title: string; help: string; numeric?: boolean; value: (m: Json, byDir: Map<string, Json>) => string | number | null };
const COLUMNS: Column[] = [
  { key: 'name', title: 'Name', help: 'The model\'s name: the RL model label of the run that saved it, numbered when another model has it already. Rename it in its Details.', value: m => modelName(m) },
  { key: 'task', title: 'Trained on', help: 'The task the model was trained on; "multi-task" for a model trained offline on recorded runs.', value: m => trainedOn(m) },
  { key: 'design', title: 'Design', help: 'The network design the model was built as - Graph Transformer, RGCN, GATv2, GraphGPS, CircuitGPS (v2 or v3) or parameter-group attention - and under it its size: hidden width / attention heads / layers, and RWSE (random-walk structural encoding) where the design has it. A fine-tuned model keeps the design of the model it started from; a run that loads it uses this network as it is.', value: m => `${designName(m.network)} ${sizeLabel(m.network)}` },
  { key: 'evaluations', numeric: true, title: 'Evaluations', help: 'The evaluations of training behind its newest save point.', value: m => m.trained_evaluations ?? null },
  { key: 'points', numeric: true, title: 'Save points', help: 'How many save points its run wrote.', value: m => m.checkpoints?.length ?? 0 },
  { key: 'saved', title: 'Last saved', help: 'When its newest save point was written (local time of this computer).', value: m => m.saved_utc ?? null },
  { key: 'from', title: 'Started from', help: 'Where the model came from: a template (a new model), a saved model it was fine-tuned from, or recorded runs (offline).', value: (m, byDir) => startedFrom(m, byDir).text },
  { key: 'data', title: 'Data', help: 'MOCK = trained on the built-in synthetic backend; real = Virtuoso / Spectre (or ngspice). A model only loads for a task of the same kind.', value: m => (m.mock ? 'mock' : 'real') },
  { key: 'restorable', title: 'Restorable', help: `${Object.entries(RESTORABLE_MEANS).map(([k, means]) => `${RESTORABLE[k]}: ${means}`).join('; ')}. A full save point ${RESTORABLE_OLDER}.`, value: m => RESTORABLE[m.restoration_capability] ?? m.restoration_capability ?? '' },
];

/** A save point a Use could not read, and why (useRlModel's netMessage). */
type UseError = { point: string; text: string };

/** One model's Details: what can be done with it, and what it is. `usingPoint`: the save point a Use is reading (pointKey). */
function ModelDetails({ model, models, runs, byDir, source, usable, config, netFields, from, usingPoint, useError, onUse, onRenamed, onSelect }: {
  model: Json; models: Json[]; runs: Json[]; byDir: Map<string, Json>; source: Json; usable: string | null; config: Json; netFields: string[]; from: Window | null;
  usingPoint: string | null; useError: UseError | null; onUse: (run_dir: string, checkpoint_id: string) => void; onRenamed: () => void; onSelect: (run_dir: string) => void }) {
  const points: Json[] = [...(model.checkpoints ?? [])].reverse();          // newest first
  const inUse = source.run_dir === model.run_dir;
  const [point, setPoint] = useState<string>(() => (inUse && source.checkpoint_id && source.checkpoint_id !== 'latest' ? source.checkpoint_id : points[0]?.checkpoint_id) ?? '');
  // The selected save point's compatibility with the draft's task, as "Use this save point" would load it (branch record
  // SIF-85): the save point is read first, as Use reads it, and the task on the page is checked with this model's own network
  // and component list (withSavePoint) in a Mode that loads it. It was checked with the page's network, so a model of another
  // design or size read "NOT compatible - it cannot be loaded" although Use brings its own network. An inspection: nothing in
  // the draft changes. The page's network stays in the deps: a key the save point does not fix stays the page's, as in Use.
  const { value: checked, error: checkError } = useRequest(async signal => {
    const read = await readSavePoint(model.run_dir, point, netFields, signal);
    return api.model(model.run_dir, point, { ...config, run: withSavePoint({ ...config.run, mode: usable ?? 'fine_tune' }, read) }, signal);
  }, [model.run_dir, point, usable, netFields.join(), JSON.stringify([config.circuit, config.parameters, config.targets, config.measurements, config.run?.network])],
    { enabled: !!point, delay: 250 });
  const failed = useError && points.some(p => pointKey(model.run_dir, p.checkpoint_id) === useError.point) ? useError : null;
  const [name, setName] = useState(modelName(model));
  const [renaming, setRenaming] = useState(false);
  const [renameNote, setRenameNote] = useState<{ level: 'hint' | 'warn'; text: string } | null>(null);
  useEffect(() => setName(modelName(model)), [model.run_dir, model.model_label]);
  const typed = name.trim();
  const canRename = !renaming && !!typed && typed !== modelName(model);
  const rename = () => {
    if (!canRename) return;
    setRenaming(true); setRenameNote(null);
    api.renameModel(model.run_dir, typed).then(r => { setRenameNote({ level: 'hint', text: `Renamed to "${r.model_label}".` }); onRenamed(); })
      .catch(e => setRenameNote({ level: 'warn', text: e.message })).finally(() => setRenaming(false));
  };
  const children = childrenOf(model, runs), history = historyOf(byDir.get(model.run_dir) ?? model, byDir);
  const asModel = (dir: string) => models.find(m => m.run_dir === dir);
  const link = (dir: string, text: string) => asModel(dir)
    ? <button className="item-link" onClick={() => onSelect(dir)} title={`${dir}\nShow this model here.`}>{text}</button>
    : <button className="item-link" onClick={() => openRunsAt({ run_dir: dir, from })} title={`${dir}\nOpen the Runs window at this run.`}>{text}</button>;
  const origin = startedFrom(model, byDir);
  const compatibility = checked?.compatibility;
  return (<div className="model-details">
    <h4>Save points <span className="hint">- newest first; a save point used is pinned: the run loads exactly it, even when its run saves newer ones</span></h4>
    <table className="grid small model-points"><thead><tr><th>Evaluations</th><th>Saved</th><th>Kind</th><th>Restorable</th><th className="plain"></th></tr></thead>
      {/* The pressed Use says "Using..." while its save point is read (branch record SIF-85: it showed nothing); the other
          buttons stay on - a newer choice wins (record 7.278). */}
      <tbody>{points.map(p => { const used = inUse && source.checkpoint_id === p.checkpoint_id, reading = usingPoint === pointKey(model.run_dir, p.checkpoint_id); return (
        <tr key={p.checkpoint_id} className={p.checkpoint_id === point ? 'current' : ''} title={p.checkpoint_id} onClick={() => setPoint(p.checkpoint_id)}>
          <td className="numeric">{p.evaluations ?? '?'}</td><td>{when(p.created_utc)}</td>
          <td>{KIND[p.kind] ?? p.kind}{p.is_best_policy ? ' · best policy' : ''}{p.is_latest ? ' · newest' : ''}</td>
          <td>{RESTORABLE[p.restoration_capability] ?? p.restoration_capability}</td>
          <td>{used ? <b className="ok">in use</b> : <button className="model-use" disabled={!usable || reading} aria-busy={reading || undefined}
            onClick={e => { e.stopPropagation(); onUse(model.run_dir, p.checkpoint_id); }}
            title={usable ? `Use this save point: the next run ${usable === 'frozen' ? 'evaluates' : 'fine-tunes'} exactly this model, with its network and component list (one Undo step).`
              : 'Choose Fine-tune or Evaluate only above to use a saved model. In New model the table is for looking only.'}>{reading ? 'Using...' : 'Use this save point'}</button>}</td></tr>); })}</tbody></table>
    {/* A Use that could not read its save point is said here too, by the button pressed (branch record SIF-85): the window
        says it far above the table, and the press looked like it did nothing. */}
    {failed && <p className="error use-error">{failed.text}</p>}
    <div className="row model-rename-row">
      <label title="The name this model is listed under. Every model under the output folder has a name of its own: a name another model carries is refused.">Name
        <input className="model-rename" value={name} maxLength={80} disabled={renaming} onChange={e => setName(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); rename(); } }} /></label>
      <button className="model-rename-apply" disabled={!canRename} onClick={rename} title="Give this saved model the name in the box.">{renaming ? 'Renaming...' : 'Rename'}</button></div>
    {renameNote && <p className={`${renameNote.level === 'warn' ? 'warn' : 'hint'} model-rename-note`}>{renameNote.text}</p>}
    {/* A save point by its evaluations, as the table above counts it; its id on hover (branch record SIF-67: "- save point
        ckpt-00000800-003f07c8", and the same id in Started from, History and the newer save point's note). */}
    <h4>With the task on the page and this model's own network <span className="hint">- save point <span title={point || undefined}>{pointText(point)}</span></span></h4>
    {checkError && <p className="error">{checkError}</p>}
    {checked?.compatibility_unchecked && <p className="hint">{checked.compatibility_unchecked.title}: {checked.compatibility_unchecked.what}</p>}
    {/* An incompatible model says what that means in the Modes' own words (it said "no fallback to scratch", the key of
        New model; branch record SIF-53). */}
    {compatibility && <details className="model-compatibility" open={!compatibility.compatible}><summary className={compatibility.compatible ? '' : 'error'}>
      {compatibility.compatible ? `Compatible for ${compatibilityMode(compatibility.mode)}`
        : `NOT compatible for ${compatibilityMode(compatibility.mode)} - it cannot be loaded, and a run never falls back to New model`}</summary>
      <CompatibilityList checks={compatibility.checks} /></details>}
    {!checked && !checkError && point && <p className="hint">Checking it against the task on the page...</p>}
    <h4>Relationships</h4>
    {/* A run's Mode in the words of the Mode buttons above (branch record SIF-44: "fine_tune, seed 0"); the task keeps its key. */}
    <table className="grid small run-relations model-relations"><tbody>
      <tr><td>Saved by</td><td><button className="item-link" onClick={() => openRunsAt({ run_dir: model.run_dir, from })} title="Open the Runs window at this run.">{folderName(model.run_dir)}</button>
        <span className="hint"> · {runMode(model) || '?'}, seed {model.seed ?? '?'}, {model.state ?? 'unknown state'}</span></td></tr>
      <tr><td>Started from</td><td>{origin.parent ? link(origin.parent, origin.text) : origin.text}{model.parent?.checkpoint_id && origin.at == null
        && <span className="hint" title={model.parent.checkpoint_id}>{` (save point ${pointText(model.parent.checkpoint_id)})`}</span>}</td></tr>
      <tr><td>Models trained from it</td><td>{children.filter(c => c.model_label && c.mode !== 'frozen').map((c, i) => <Fragment key={c.run_dir}>{i > 0 && ', '}{link(c.run_dir, c.model_label)}</Fragment>)}
        {!children.some(c => c.model_label && c.mode !== 'frozen') && <span className="hint">none under this output folder</span>}</td></tr>
      <tr><td>Runs that loaded it</td><td>{children.map((c, i) => <Fragment key={c.run_dir}>{i > 0 && ', '}<button className="item-link" onClick={() => openRunsAt({ run_dir: c.run_dir, from })}
        title={`${c.run_dir}\nOpen the Runs window at this run.`}>{`${folderName(c.run_dir)} (${c.mode === 'frozen' ? 'evaluated' : 'fine-tuned'})`}</button></Fragment>)}
        {!children.length && <span className="hint">none under this output folder</span>}</td></tr>
      <tr><td>History</td><td><details className="more model-history"><summary>{history.steps.length - 1 ? `${plural(history.steps.length - 1, 'model')} behind it, oldest first` : 'no saved model behind it'}</summary>
        <ol className="steps-list"><li className={history.root.missing ? 'warn' : 'hint'}>{history.root.text}</li>
          {history.steps.map(s => <li key={s.run_dir}>{s.run_dir === model.run_dir ? <b>this model</b> : link(s.run_dir, s.row?.model_label ?? folderName(s.run_dir))}
            {s.row && <span className="hint">{` · ${s.row.task_key ?? '?'} · ${runMode(s.row) || '?'} · ${s.row.evaluations != null ? plural(s.row.evaluations, 'evaluation') : 'evaluations unknown'}`}</span>}
            {s.checkpoint_id && <span className="hint" title={s.checkpoint_id}>{` - loaded the one above, its save point ${pointText(s.checkpoint_id)}`}</span>}</li>)}</ol></details></td></tr>
      <tr><td>Folder</td><td className="path" title="Click to copy" onClick={() => copy(model.run_dir)}>{model.run_dir}</td></tr>
    </tbody></table>
    {point && <ModelStructure runDir={model.run_dir} checkpointId={point} label={modelName(model)} />}
    {point && <CircuitGraphView runDir={model.run_dir} checkpointId={point} label={modelName(model)} />}
  </div>);
}

export function SavedModels({ source, usable, runs, outputRoot, config, netFields, popup, onUse, usingPoint = null, useError = null }: {
  source: Json; usable: string | null; runs: Json[]; outputRoot?: string | null; config: Json; netFields: string[]; popup: Window | null;
  onUse: (run_dir: string, checkpoint_id: string) => void; usingPoint?: string | null; useError?: UseError | null }) {
  // Read again when a run of the list changed - came, went, came to rest, or its model was renamed - not at every read of
  // the run list (each read here walks every run's save points on the slow D: drive; record 7.275). A live run's new
  // save points show at Refresh list or once it rests. Refresh list reads every run folder anew (`fresh`, record 7.274).
  const runsKey = useMemo(() => runs.map(r => `${r.run_dir}|${r.state}|${r.ended_utc ?? ''}|${r.model_label ?? ''}`).join('\n'), [runs]);
  const freshNext = useRef(false);
  const { value: models, error, loading, refresh: load } = useRequest<Json[]>(signal => {
    const fresh = freshNext.current;
    freshNext.current = false;
    return api.savedModels(outputRoot ?? undefined, signal, fresh).then(r => r.models ?? []);
  }, [runsKey, outputRoot], { keepPrevious: true });
  const folders = useFolders('models');
  useEffect(() => { void folders.refresh(); }, []);
  const table = useTableView('saved', true);
  const { filter, setFilter, selected, setSelected } = table;
  const [open, setOpen] = useState<string | null>(null);              // the model whose Details are open
  const byDir = useMemo(() => new Map(runs.map(r => [r.run_dir, r])), [runs]);
  const list = models ?? [];
  const text = (m: Json) => [modelName(m), m.task_name, m.task_id, trainedOn(m), m.circuit_class, designName(m.network), netLabel(m.network), netShort(m.network), m.mode, m.state, m.mock ? 'mock' : 'real',
    `seed${m.seed}`, folders.data.folders[folders.of(m.run_dir)]].join(' ').toLowerCase();
  const column = COLUMNS.find(c => c.key === table.sort.key) ?? COLUMNS[0];
  // One design only, chosen beside Refresh list (branch record SIF-10): the designs there are, the most models first.
  const [design, setDesign] = useState('');
  const designs = useMemo(() => {
    const count = new Map<string, number>();
    for (const m of list) { const d = designName(m.network); count.set(d, (count.get(d) ?? 0) + 1); }
    return [...count].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }, [list]);
  useEffect(() => { if (design && !designs.some(([d]) => d === design)) setDesign(''); }, [designs]);
  const shown = table.arrange(list, m => folders.holds(m.run_dir) && (!design || designName(m.network) === design), text, m => column.value(m, byDir));
  const inUse: Json = list.find(m => m.run_dir === source.run_dir) ?? null;
  // A newer save point of the model in use is offered, never followed by itself (the source is pinned).
  const pinned = inUse?.checkpoints?.find((p: Json) => p.checkpoint_id === source.checkpoint_id);
  const newest = inUse?.checkpoints?.find((p: Json) => p.is_latest) ?? inUse?.checkpoints?.[inUse.checkpoints.length - 1];
  const newer = usable && inUse && newest && pinned && newest.checkpoint_id !== pinned.checkpoint_id && (newest.evaluations ?? 0) > (pinned.evaluations ?? 0) ? newest : null;
  const chooseFolder = (id: string) => { folders.setFolder(id); setSelected([]); setOpen(null); };
  const useNewest = (m: Json) => { const p = m.checkpoints?.find((x: Json) => x.is_latest) ?? m.checkpoints?.[m.checkpoints.length - 1]; if (p) onUse(m.run_dir, p.checkpoint_id); };
  // The table scrolls in a box of its own (branch record SIF-86: 411 models made it about 20,000 px long, with the model in use
  // and the Mode's settings under it). When the list first arrives the model in use is brought to the middle of the box, if it
  // is out of its view - the box only, never the window. Once per window: a later sort, filter or Refresh list keeps the place.
  const box = useRef<HTMLDivElement>(null), placed = useRef(false);
  useEffect(() => {
    if (placed.current || !models) return;
    placed.current = true;
    const at = box.current, row = at?.querySelector<HTMLElement>('tr.model-row.current');
    if (at && row) void styled(popup ?? window).then(() => {
      // what the box shows of its rows: under its sticky titles, down to its bottom
      const head = at.querySelector('thead')?.offsetHeight ?? 0, top = at.getBoundingClientRect().top + head, height = at.clientHeight - head;
      const r = row.getBoundingClientRect();
      if (r.top < top || r.bottom > top + height) at.scrollTop += r.top - top - (height - r.height) / 2;
    });
  }, [models]);
  return (<div className="saved-models">
    <div className="row"><button onClick={() => { freshNext.current = true; load(); void folders.refresh(); }} disabled={loading}
      title="Refresh list: every run folder is read again from the disk.">Refresh list</button>
      <select className="model-design-filter" value={design} aria-label="Design" onChange={e => { setDesign(e.target.value); setSelected([]); }}
        title="Design: the saved models of one network design only, with how many there are of each.">
        <option value="">All designs</option>{designs.map(([d, n]) => <option key={d} value={d}>{d} ({n})</option>)}</select>
      <input className="model-filter" placeholder="Filter: name, task, design, mock / real ..." value={filter} onChange={e => { setFilter(e.target.value); setSelected([]); }} />
      <span className="hint model-count">{loading ? 'Reading the saved models...' : models ? `${plural(list.length, 'saved model')} under the output folder` : ''}</span></div>
    {error && <p className="error">The list of saved models could not be read: {error}</p>}
    {folders.error && <p className="error" role="alert">{folders.error} Press Refresh list to retry.</p>}
    {models && !list.length && !error && <p className="hint model-empty">No saved model yet under this output folder. A run saves one when it is paused, stopped or finished,
      and every N evaluations while it runs ("Model checkpoints" in the output settings must be on).</p>}
    {source.run_dir && models && !inUse && !loading && usable && <p className="warn model-missing">The model in use is not in this list: its run folder is outside the current output
      folder, or it no longer holds a complete save point. <span className="path" title="Click to copy" onClick={() => copy(source.run_dir)}>{source.run_dir}</span></p>}
    {newer && <p className="note model-newer">The model in use has a newer save point: <b>{newer.evaluations} evaluations</b> ({when(newer.created_utc)}); the next run loads the save point
      {' '}<span title={source.checkpoint_id}>{pointText(source.checkpoint_id)}</span>. <button className="model-use-newer" onClick={() => onUse(inUse.run_dir, newer.checkpoint_id)}>Use the newer one</button></p>}
    {list.length > 0 && <div className="task-browser">
      {popup && <Folders state={folders} keys={list.map(m => m.run_dir)} popup={popup} onSelect={chooseFolder} />}
      <div className="task-folder-content">
        <FolderMoveBar state={folders} shown={shown.length} selected={selected.length} onMove={id => void table.move(folders, id)} />
        <div className="scroll" ref={box}><table className="grid run-table model-table">
          <TableHead view={table} columns={COLUMNS} shown={shown} id={m => m.run_dir} what="models" disabled={folders.busy || !folders.ready} />
          <tbody>{shown.map(m => { const used = m.run_dir === source.run_dir, origin = startedFrom(m, byDir); return (<Fragment key={m.run_dir}>
            <tr className={`model-row${used ? ' current' : ''}`} aria-current={used ? 'true' : undefined} title={m.run_dir}
              onDoubleClick={e => { if ((e.target as HTMLElement).closest('button, input, select, label')) return; (popup ?? window).getSelection()?.removeAllRanges();
                if (usable) useNewest(m); else setOpen(m.run_dir); }}>
              <td className="task-select"><input type="checkbox" aria-label={`Select ${modelName(m)}`} checked={selected.includes(m.run_dir)}
                disabled={folders.busy || !folders.ready} onChange={e => table.select(m.run_dir, e.target.checked)} /></td>
              <td className="wrap-words"><b>{breakable(modelName(m))}</b>{used && <span className="badge model-tag in-use-tag">in use</span>}
                {folders.folder === 'all' && folders.data.folders[folders.of(m.run_dir)] && <div className="hint task-folder-label">{folders.data.folders[folders.of(m.run_dir)]}</div>}</td>
              <td className="wrap-words" title={m.run_kind === 'offline_pretraining' ? undefined : String(trainedKey(m))}>{breakable(trainedOn(m))}</td>
              <td className="wrap-words model-net" title={netLabel(m.network)}>{designName(m.network)}{' '}<span className="hint model-size">{sizeLabel(m.network)}</span></td>
              <td className="numeric">{m.trained_evaluations ?? '?'}</td><td className="numeric">{m.checkpoints?.length ?? 0}</td>
              <td className="wrap-words">{when(m.saved_utc)}</td><td className="wrap">{origin.text}</td>
              <td>{m.mock ? <span className="badge model-tag mock-tag">MOCK</span> : 'real'}</td>
              <td>{RESTORABLE[m.restoration_capability] ?? m.restoration_capability}</td>
              <td><button className="notes-link" aria-expanded={open === m.run_dir} onClick={() => setOpen(o => (o === m.run_dir ? null : m.run_dir))}>{open === m.run_dir ? 'Hide details' : 'Details'}</button></td>
            </tr>
            {open === m.run_dir && <tr className="run-details-row"><td colSpan={COLUMNS.length + 2}>
              <ModelDetails model={m} models={list} runs={runs} byDir={byDir} source={source} usable={usable} config={config} netFields={netFields} from={popup}
                usingPoint={usingPoint} useError={useError} onUse={onUse} onRenamed={load} onSelect={dir => { folders.setFolder('all'); setFilter(''); setOpen(dir); }} /></td></tr>}
          </Fragment>); })}</tbody></table></div>
        {shown.length === 0 && <p className="hint task-folder-empty">{filter || design ? 'No saved model matches the filter in this folder.' : 'This folder is empty. Select models in All models, then use Move to…'}</p>}
      </div></div>}
  </div>);
}
