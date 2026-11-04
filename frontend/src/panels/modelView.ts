// Small model labels and view state used while the optional RL model window is closed.
import { useRef, useState } from 'react';
import type { Json } from '../api';
import { folderName } from '../format';
import { useFolders } from './Folders';
import { useTableView } from './TableView';

export const modelName = (m: Json): string => m?.model_label ?? m?.task_name ?? m?.task_id ?? folderName(m?.run_dir ?? '');
export const modelNameAt = (runs: Json[], dir: string): string => { const row = runs.find(r => r.run_dir === dir); return row ? modelName(row) : folderName(dir); };

/** Keep filters, selection and the last list across window closes without importing the window's rendering code. */
export function useSavedModelsView() {
  const table = useTableView('saved', true);
  const folders = useFolders('models');
  const [design, setDesign] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const last = useRef<{ root: string | null; models: Json[] } | null>(null);
  return { table, folders, design, setDesign, open, setOpen, last };
}
export type SavedModelsView = ReturnType<typeof useSavedModelsView>;
