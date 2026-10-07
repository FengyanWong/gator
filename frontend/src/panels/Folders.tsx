import { useRef, useState } from 'react';
import { api, FolderKind, Json } from '../api';
import { Icon } from './Icons';

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
  const request = useRef(0);
  const writing = useRef(false);
  const accept = (value: FolderState) => {
    setData(value); setReady(true);
    setFolder(id => id === 'all' || id === 'unfiled' || value.folders[id] ? id : 'all');
  };
  const refresh = async () => {
    if (writing.current) return;
    const id = ++request.current;
    setBusy(true);
    try {
      const value = await api.folders(kind);
      if (id === request.current) { accept(value); setError(''); }
    } catch (e: any) {
      if (id === request.current) { setError(`Folders could not be read: ${e.message}`); setReady(false); }
    } finally { if (id === request.current) setBusy(false); }
  };
  const change = async (action: () => Promise<Json>) => {
    if (writing.current || !ready) return null;
    writing.current = true; ++request.current; setBusy(true); setError('');
    try {
      const value = await action(); accept(value); return value;
    } catch (e: any) { setError(`Folders were not saved: ${e.message}`); return null; }
    finally { writing.current = false; setBusy(false); }
  };
  /** Selected keys into a folder ('unfiled' = out of every folder). */
  const move = (keys: string[], id: string) => change(() => api.moveToFolder(kind, keys, id === 'unfiled' ? null : id));
  const names = Object.entries(data.folders).sort((a, b) => a[1].localeCompare(b[1]));
  const of = (key: string) => data.assignments[key] ?? 'unfiled';
  /** The heading of the folder chosen: All, Unfiled or its name. */
  const title = folder === 'all' ? ALL[kind] : folder === 'unfiled' ? 'Unfiled' : data.folders[folder] ?? ALL[kind];
  /** Whether a key is in the folder chosen. */
  const holds = (key: string) => folder === 'all' || of(key) === folder;
  return { kind, data, folder, setFolder, busy, ready, error, refresh, change, move, names, of, title, holds };
}
export type FolderView = ReturnType<typeof useFolders>;

/** The folder list on the left of a window: All, Unfiled and the user's folders with their counts, and the icons that make,
 *  rename and delete one. `keys`: every listed item (counts count listed items: an assignment of a run that is gone is
 *  kept, and not counted). Questions are asked in the window the list is in (`popup`). */
export function Folders({ state, keys, popup, onSelect }: { state: FolderView; keys: string[]; popup: Window; onSelect: (id: string) => void }) {
  const { kind, data, folder, busy, ready, names, of, change } = state;
  const counts = new Map<string, number>();
  keys.forEach(key => counts.set(of(key), (counts.get(of(key)) ?? 0) + 1));
  const currentName = data.folders[folder];
  const create = async () => {
    const name = popup.prompt('New folder name');
    if (name == null) return;
    const saved = await change(() => api.createFolder(kind, name));
    if (saved) onSelect(saved.created_id);
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

/** The bar above a window's table: the folder chosen, how many are shown and selected, and "Move to..." for the selection. */
export function FolderMoveBar({ state, shown, selected, onMove }: { state: FolderView; shown: number; selected: number; onMove: (id: string) => void }) {
  return <div className="row task-move-bar">
    <b>{state.title}</b>
    <span className="hint">{shown} shown{selected > 0 ? ` · ${selected} selected` : ''}</span>
    <select aria-label={`Move selected ${PLURAL[state.kind]} to folder`} value="" disabled={!selected || state.busy || !state.ready} onChange={e => onMove(e.target.value)}>
      <option value="" disabled>Move to…</option><option value="unfiled">Unfiled</option>
      {state.names.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
    </select>
    {state.busy && <span className="hint" role="status">Updating folders…</span>}
  </div>;
}
