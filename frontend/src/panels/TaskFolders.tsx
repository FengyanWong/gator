import { useRef, useState } from 'react';
import { api, Json } from '../api';
import { Icon } from './Icons';

type FolderState = { folders: Record<string, string>; assignments: Record<string, string> };

export function useTaskFolders() {
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
      const value = await api.taskFolders();
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
  const names = Object.entries(data.folders).sort((a, b) => a[1].localeCompare(b[1]));
  const of = (key: string) => data.assignments[key] ?? 'unfiled';
  return { data, folder, setFolder, busy, ready, error, refresh, change, names, of };
}

export function TaskFolders({ state, tasks, popup, onSelect }: {
  state: ReturnType<typeof useTaskFolders>; tasks: Json[]; popup: Window; onSelect: (id: string) => void;
}) {
  const { data, folder, busy, ready, names, of, change } = state;
  const counts = new Map<string, number>();
  tasks.forEach(t => counts.set(of(t.task_key), (counts.get(of(t.task_key)) ?? 0) + 1));
  const currentName = data.folders[folder];
  const create = async () => {
    const name = popup.prompt('New folder name');
    if (name == null) return;
    const saved = await change(() => api.createTaskFolder(name));
    if (saved) onSelect(saved.created_id);
  };
  const rename = async () => {
    const name = popup.prompt('Rename folder', currentName);
    if (name != null) await change(() => api.renameTaskFolder(folder, name));
  };
  const remove = async () => {
    if (!popup.confirm(`Delete folder “${currentName}”? Its tasks will move to Unfiled. No tasks or runs are deleted.`)) return;
    if (await change(() => api.deleteTaskFolder(folder))) onSelect('unfiled');
  };
  const item = (id: string, name: string, count: number) => <button key={id} className={`task-folder${folder === id ? ' active' : ''}`}
    data-folder-id={id} aria-current={folder === id ? 'page' : undefined} onClick={() => onSelect(id)} disabled={busy}>
    <span>{name}</span><span className="hint">{count}</span></button>;
  return <nav className="task-folders" aria-label="Task folders">
    <div className="row task-folder-heading"><b>Folders</b><button onClick={create} disabled={busy || !ready} title="New folder"><Icon name="new-folder" label="New folder" /></button></div>
    {item('all', 'All tasks', tasks.length)}
    {item('unfiled', 'Unfiled', counts.get('unfiled') ?? 0)}
    {names.map(([id, name]) => item(id, name, counts.get(id) ?? 0))}
    {currentName && <div className="row task-folder-actions">
      <button onClick={rename} disabled={busy || !ready} title="Rename folder"><Icon name="rename" label="Rename" /></button>
      <button onClick={remove} disabled={busy || !ready} title="Delete folder: move its tasks to Unfiled"><Icon name="delete" label="Delete folder" /></button>
    </div>}
  </nav>;
}
