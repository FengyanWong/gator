// The folders of the Tasks, Runs and RL model windows (record 7.263, after the task folders of record 7.250): the
// folder list at a window's left and the Move to... bar above its table.
import { useRef, useState } from 'react';
import { api, FolderKind, Json } from '../api';
import { Icon } from './Icons';
import { useNewest } from '../newest';

/** The folders of the workbench's windows (task folders: record 7.250; generalized in record 7.263, plan "Categories for
 *  runs and models"): the Tasks window's tasks, the Runs window's runs, and - with the RL model window, build step 4 - the
 *  saved models. Each kind is stored by the backend in a file of its own (`/api/task-folders`, `/api/run-folders`,
 *  `/api/model-folders`); runs and models are keyed by their run folder. Organization only: a folder never renames,
 *  moves or deletes a task or a run. */
export type { FolderKind };
type FolderState = { folders: Record<string, string>; assignments: Record<string, string> };
const ALL: Record<FolderKind, string> = { tasks: 'All tasks', runs: 'All runs', models: 'All models' };
const PLURAL: Record<FolderKind, string> = { tasks: 'tasks', runs: 'runs', models: 'models' };
const LIST_NAME: Record<FolderKind, string> = { tasks: 'Task folders', runs: 'Run folders', models: 'Model folders' };

/** The kind's folders, the folder chosen in its window ('all', 'unfiled' or a folder id), and its one writer at a time. */
export function useFolders(kind: FolderKind) {
  const [data, setData] = useState<FolderState>({ folders: {}, assignments: {} });
  const [folder, setFolder] = useState('all');
  const [busy, setBusy] = useState(false);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState('');
  const request = useNewest();
  const writing = useRef(false);
  const accept = (value: FolderState) => {
    setData(value); setReady(true);
    setFolder(id => id === 'all' || id === 'unfiled' || value.folders[id] ? id : 'all');
  };
  const refresh = async () => {
    if (writing.current) return;
    const id = request.next();
    setBusy(true);
    try {
      const value = await api.folders(kind);
      if (id()) { accept(value); setError(''); }
    } catch (e: any) {
      if (id()) { setError(`Folders could not be read: ${e.message}`); setReady(false); }
    } finally { if (id()) setBusy(false); }
  };
  const change = async (action: () => Promise<Json>) => {
    if (writing.current || !ready) return null;
    writing.current = true; request.drop(); setBusy(true); setError('');
    try {
      const value = await action(); accept(value); return value;
    } catch (e: any) { setError(`Folders were not saved: ${e.message}`); return null; }
    finally { writing.current = false; setBusy(false); }
  };
  /** Selected keys into a folder ('unfiled' = out of every folder). */
  const move = (keys: string[], id: string) => change(() => api.moveToFolder(kind, keys, id === 'unfiled' ? null : id));
  const names = Object.entries(data.folders).sort((a, b) => a[1].localeCompare(b[1]));
  const of = (key: string) => data.assignments[key] ?? 'unfiled';
  /** A folder's name: All, Unfiled or the user's; undefined for a folder that is gone. */
  const name = (id: string): string | undefined => id === 'all' ? ALL[kind] : id === 'unfiled' ? 'Unfiled' : data.folders[id];
  /** The heading of the folder chosen. */
  const title = name(folder) ?? ALL[kind];
  /** Whether a key is in the folder chosen. */
  const holds = (key: string) => folder === 'all' || of(key) === folder;
  return { kind, data, folder, setFolder, busy, ready, error, refresh, change, move, names, of, name, title, holds };
}
export type FolderView = ReturnType<typeof useFolders>;

/** The folder list on the left of a window: All, Unfiled and the user's folders with their counts, and the icons that make,
 *  rename and delete one. `keys`: every listed item (counts count listed items: an assignment of a run that is gone is
 *  kept, and not counted). Questions are asked in the window the list is in (`popup`). `selected`: how many rows are ticked. */
export function Folders({ state, keys, popup, onSelect, selected = 0 }: { state: FolderView; keys: string[]; popup: Window; onSelect: (id: string) => void; selected?: number }) {
  const { kind, data, folder, busy, ready, names, of, change } = state;
  const counts = new Map<string, number>();
  keys.forEach(key => counts.set(of(key), (counts.get(of(key)) ?? 0) + 1));
  const currentName = data.folders[folder];
  // With rows ticked a new folder is not opened (branch record SIF-101): opening it - empty - let the ticks go, so tick, New
  // folder, Move to… could not be done in that order. The ticks and the folder shown stay; the new folder is in Move to….
  const create = async () => {
    const one = PLURAL[kind].slice(0, -1);
    const name = popup.prompt(selected ? `New folder name - ${selected === 1 ? `the ticked ${one} stays` : `the ${selected} ticked ${PLURAL[kind]} stay`} ticked; then choose the folder in Move to…`
      : 'New folder name');
    if (name == null) return;
    const saved = await change(() => api.createFolder(kind, name));
    if (saved && !selected) onSelect(saved.created_id);
  };
  const rename = async () => {
    const name = popup.prompt('Rename folder', currentName);
    if (name != null) await change(() => api.renameFolder(kind, folder, name));
  };
  const remove = async () => {
    if (!popup.confirm(`Delete folder “${currentName}”? Its ${PLURAL[kind]} will move to Unfiled. No tasks or runs are deleted.`)) return;
    if (await change(() => api.deleteFolder(kind, folder))) onSelect('unfiled');
  };
  const item = (id: string, name: string, count: number) => <button key={id} className={`task-folder${folder === id ? ' active' : ''}`}
    data-folder-id={id} aria-current={folder === id ? 'page' : undefined} onClick={() => onSelect(id)} disabled={busy}>
    <span>{name}</span><span className="hint">{count}</span></button>;
  return <nav className="task-folders" data-folder-kind={kind} aria-label={LIST_NAME[kind]}>
    <div className="row task-folder-heading"><b>Folders</b><button onClick={create} disabled={busy || !ready} title="New folder"><Icon name="new-folder" label="New folder" /></button></div>
    {item('all', ALL[kind], keys.length)}
    {item('unfiled', 'Unfiled', counts.get('unfiled') ?? 0)}
    {names.map(([id, name]) => item(id, name, counts.get(id) ?? 0))}
    {currentName && <div className="row task-folder-actions">
      <button onClick={rename} disabled={busy || !ready} title="Rename folder"><Icon name="rename" label="Rename" /></button>
      <button onClick={remove} disabled={busy || !ready} title={`Delete folder: move its ${PLURAL[kind]} to Unfiled`}><Icon name="delete" label="Delete folder" /></button>
    </div>}
  </nav>;
}

/** The bar above a window's table: the folder chosen, how many are shown and selected, and "Move to..." for the selection.
 *  Its tooltip says what it moves, or - greyed out with nothing ticked - to tick rows first (branch record SIF-68). Until
 *  the folders are read the rows' checkboxes are greyed out too, so it says that instead (SIF-68 review follow-up). */
export function FolderMoveBar({ state, shown, selected, onMove }: { state: FolderView; shown: number; selected: number; onMove: (id: string) => void }) {
  const what = selected === 1 ? `selected ${PLURAL[state.kind].slice(0, -1)}` : `${selected} selected ${PLURAL[state.kind]}`;
  const unread = state.busy ? 'Not available: the folders are being read.' : 'Not available: the folders could not be read - press Refresh list.';
  return <div className="row task-move-bar">
    <b>{state.title}</b>
    <span className="hint">{shown} shown{selected > 0 ? ` · ${selected} selected` : ''}</span>
    <select aria-label={`Move selected ${PLURAL[state.kind]} to folder`} value="" disabled={!selected || state.busy || !state.ready} onChange={e => onMove(e.target.value)}
      title={!state.ready ? unread : selected ? `Move the ${what} to a folder.` : `Tick ${PLURAL[state.kind]} in the table first, then choose a folder here.`}>
      <option value="" disabled>Move to…</option><option value="unfiled">Unfiled</option>
      {state.names.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
    </select>
    {state.busy && <span className="hint" role="status">Updating folders…</span>}
  </div>;
}
