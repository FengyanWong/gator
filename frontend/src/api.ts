// Thin typed client for the local backend. Every request is same-origin JSON. What is not a request moved out (plan-refactoring
// C10): the number formatters to format.ts (si to units.ts), the shared cached reads to shared.ts.
// The browser never sends hosts, ports, commands or arbitrary paths: the backend has no such fields.
import type { ModelReply, RunSummary, TaskStarter, TaskSummary, WorkbenchConfig } from './contracts';
import { placeOf } from './panels/issuePlace';

export type Json = any;
/** What a folder holds (record 7.263): tasks (by task key), runs and saved models (both by run folder). */
export type FolderKind = 'tasks' | 'runs' | 'models';
const FOLDER_ROUTE: Record<FolderKind, string> = { tasks: '/api/task-folders', runs: '/api/run-folders', models: '/api/model-folders' };

export class ApiError extends Error {
  constructor(public status: number, public detail: Json) {
    // A refusal carries {message, code, ...}; some carry {detail} or {meaning}; a plain HTTPException carries a string.
    super([detail?.message, detail?.detail, detail?.meaning, detail].find(v => typeof v === 'string' && v) ?? `HTTP ${status}`);
  }
}

/** Bound reads even when a callback ignores cancellation. The fetch signal also releases the browser connection.
 *  Writes have their own lifecycle and are never retried by this helper. */
export async function readWithDeadline<T>(read: (signal: AbortSignal) => Promise<T>, signal?: AbortSignal, timeoutMs = 30000): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort(signal?.reason);
  signal?.addEventListener('abort', abort, { once: true });
  if (signal?.aborted) abort();
  const timer = setTimeout(() => controller.abort(new Error('The read timed out. Check the backend connection and retry.')), timeoutMs);
  let rejectOnAbort: () => void = () => {};
  try {
    return await Promise.race([
      new Promise<never>((_, reject) => {
        rejectOnAbort = () => reject(controller.signal.reason);
        if (controller.signal.aborted) rejectOnAbort(); else controller.signal.addEventListener('abort', rejectOnAbort, { once: true });
      }),
      Promise.resolve().then(() => { controller.signal.throwIfAborted(); return read(controller.signal); }),
    ]);
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', abort);
    controller.signal.removeEventListener('abort', rejectOnAbort);
  }
}

async function call<T = Json>(method: string, url: string, body?: Json, signal?: AbortSignal): Promise<T> {
  const request = async (readSignal?: AbortSignal) => answer(await fetch(url, {
    method, signal: readSignal,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  }));
  // Hooks already supply a deadline-bound signal. Direct GETs (including shared cached reads) need one here too.
  return method === 'GET' && !signal ? readWithDeadline(request) : request(signal);
}

async function answer(response: Response): Promise<Json> {
  const text = await response.text();
  let data: Json = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { message: text.slice(0, 500) }; }
  if (!response.ok) throw new ApiError(response.status, data?.detail ?? data);
  return data;
}

const q = (params: Record<string, string | number | boolean | undefined | null>) =>
  '?' + Object.entries(params).filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join('&');

export const api = {
  meta: () => call('GET', '/api/meta'),
  schema: () => call('GET', '/api/schema'),
  networkSettings: () => call('GET', '/api/network-settings'),
  saveNetworkSettings: (encoder: string, body: Json) => call('PUT', '/api/network-settings/' + encodeURIComponent(encoder), body),
  tasks: () => call<{ tasks: TaskSummary[] }>('GET', '/api/tasks'),
  // Folders (tasks: record 7.250; runs and models: 7.263): one store per kind, the same five calls.
  folders: (kind: FolderKind) => call('GET', FOLDER_ROUTE[kind]),
  createFolder: (kind: FolderKind, name: string) => call('POST', FOLDER_ROUTE[kind], { name }),
  renameFolder: (kind: FolderKind, id: string, name: string) => call('PATCH', `${FOLDER_ROUTE[kind]}/${encodeURIComponent(id)}`, { name }),
  deleteFolder: (kind: FolderKind, id: string) => call('DELETE', `${FOLDER_ROUTE[kind]}/${encodeURIComponent(id)}`),
  moveToFolder: (kind: FolderKind, keys: string[], folder_id: string | null) =>
    call('PUT', `${FOLDER_ROUTE[kind]}/assign`, kind === 'tasks' ? { task_keys: keys, folder_id } : { run_dirs: keys, folder_id }),
  starter: (taskKey: string) => call<TaskStarter>('GET', '/api/tasks/starter' + q({ task_key: taskKey })),
  // The name a task is shown under (record 7.302): its key, files, cell, runs and models stay as they are.
  renameTask: (task_key: string, name: string) => call('POST', '/api/tasks/rename', { task_key, name }),
  loadCircuit: (circuit: Json) => call('POST', '/api/circuit/load', { circuit }),
  nativeLibraries: (profile_id: string) => call('POST', '/api/virtuoso/libraries', { profile_id }),
  nativeCells: (profile_id: string, library: string) => call('POST', '/api/virtuoso/cells', { profile_id, library }),
  // work_here: the page asked whether the cell is a copy the user made and they said yes - the cell then becomes the one the task
  // flow works in (sent only then, so an older backend still reads a cell).
  nativeImport: (profile_id: string, library: string, cell: string, testbench: string | null, work_here = false) =>
    call('POST', '/api/virtuoso/import', { profile_id, library, cell, testbench, ...(work_here ? { work_here: true } : {}) }),
  deleteProfile: (name: string) => call('POST', '/api/virtuoso/profile/delete', { name }),
  // The ngspice window (backend ngspice_tasks.py): a deck read from a file inside the allowed input roots, checked without
  // being kept, saved as the task ngspice:<name>; a saved task's deck for editing; a task taken out of the list.
  ngspiceRead: (path: string) => call('POST', '/api/ngspice/read', { path }),
  ngspiceCheck: (body: Json) => call('POST', '/api/ngspice/check', body),
  ngspiceSave: (body: Json) => call('POST', '/api/ngspice/task/save', body),
  ngspiceTask: (name: string) => call('GET', '/api/ngspice/task' + q({ name })),
  ngspiceDelete: (name: string) => call('POST', '/api/ngspice/task/delete', { name }),
  nativeRead: (profile_id: string, library: string, cell: string) => call('POST', '/api/virtuoso/read', { profile_id, library, cell }),
  setupRead: (profile_id: string, library: string, cell: string, config: Json | null) => call('POST', '/api/virtuoso/setup/read', { profile_id, library, cell, config }),
  taskSave: (body: Json) => call('POST', '/api/virtuoso/task/save', body),
  taskBaseline: (body: Json) => call('POST', '/api/tasks/baseline', body),
  taskSaving: (signal?: AbortSignal) => call('GET', '/api/tasks/saving', undefined, signal),
  taskFile: (body: Json) => call('POST', '/api/virtuoso/task/file', body),
  taskFileCheck: (text: string) => call('POST', '/api/virtuoso/task/file/check', { text }),
  taskCheck: (profile_id: string | null, config: Json) => call('POST', '/api/virtuoso/task/check', { profile_id, config }),
  validate: (config: Json, signal?: AbortSignal, rowsFrom?: number | null) =>
    call('POST', '/api/config/validate', rowsFrom ? { config, rows_from: rowsFrom } : { config }, signal),
  diff: (before: Json, after: Json) => call('POST', '/api/config/diff', { before, after }),
  // Matched devices... (Parameters tab, record 7.103): the circuit's structures and the ties they suggest; with `apply`, the rows with those made.
  matchedDevices: (config: Json, apply: string[] | null = null) => call('POST', '/api/parameters/matched', { config, apply }),
  browse: (path?: string) => call('GET', '/api/output/browse' + q({ path })),
  // `usage`: the folder's size, walked only when asked (record 7.189) - and sent only then, so an older backend takes the look.
  checkOutput: (path: string, create = false, signal?: AbortSignal, usage = false) => call('POST', '/api/output/check', usage ? { path, create, usage } : { path, create }, signal),
  connectionProfiles: () => call('GET', '/api/connection/profiles'),
  connectionStatus: (profile_id: string) => call('GET', '/api/connection/status' + q({ profile_id })),
  connectionCheck: (profile_id: string, scope: string, trigger = 'user') => call('POST', '/api/connection/check', { profile_id, scope, trigger }),
  connectionSetup: () => call('GET', '/api/connection/setup'),
  // { profile_id, kind, ssh_host?, bridge_profile? } - names only: never an address, a path or a command
  connectionCreateProfile: (body: Json) => call('POST', '/api/connection/profile', body),
  connectionConnect: (profile_id: string) => call('POST', '/api/connection/connect', { profile_id }),
  // The connection module's folders (record 7.168): each one's default, the value in use and where it comes from. A save sends
  // { folder: path, or null for its default }; the backend checks every value before it writes anything.
  connectionDirectories: () => call('GET', '/api/connection/directories'),
  saveConnectionDirectories: (values: Record<string, string | null>) => call('PUT', '/api/connection/directories', { values }),
  // `fresh`: past the backend's run cache, every run folder read again - the page's Refresh list (record 7.274).
  runs: (output_root?: string, fresh?: boolean) => call<{ runs: RunSummary[] }>('GET', '/api/runs' + q({ output_root, fresh: fresh || undefined })),
  model: (run_dir: string, checkpoint_id: string, config?: Json, signal?: AbortSignal) => call<ModelReply>('POST', '/api/runs/model', { run_dir, checkpoint_id, config }, signal),
  defaultModel: (label: string, project?: string) => call('GET', '/api/runs/default-model' + q({ label, project })),
  savedModels: (output_root?: string, signal?: AbortSignal, fresh?: boolean) => call('GET', '/api/runs/models' + q({ output_root, fresh: fresh || undefined }), undefined, signal),
  renameModel: (run_dir: string, model_label: string) => call('POST', '/api/runs/model/rename', { run_dir, model_label }),
  modelStructure: (run_dir: string, checkpoint_id: string, signal?: AbortSignal) => call('POST', '/api/runs/model/structure', { run_dir, checkpoint_id }, signal),
  modelGraphView: (run_dir: string, checkpoint_id: string, evaluation: number | null) => call('POST', '/api/runs/model/graph-view', { run_dir, checkpoint_id, evaluation }),
  start: (body: Json) => call('POST', '/api/runs/start', body),
  continueRun: (body: Json) => call('POST', '/api/runs/continue', body),
  // One launcher (record 7.261): whether Continue can go on with a run, before the press (read-only), and what became of a
  // launch sent before the page was reloaded (done, pending or unknown).
  continuation: (run_dir: string, max_evaluations?: number | null, signal?: AbortSignal) =>
    call('GET', '/api/runs/continuation' + q({ run_dir, max_evaluations }), undefined, signal),
  launchRequest: (request_id: string) => call('GET', '/api/runs/request' + q({ request_id })),
  command: (run_dir: string, command: string) => call('POST', '/api/runs/command', { run_dir, command }),
  status: (run_dir: string, signal?: AbortSignal) => call('GET', '/api/runs/status' + q({ run_dir }), undefined, signal),
  // A run's own configuration, as it started (its effective_config.json): New run like this copies its run settings (record 7.267).
  runConfig: (run_dir: string) => call<WorkbenchConfig>('GET', '/api/runs/download' + q({ run_dir, path: 'effective_config.json' })),
  files: (run_dir: string, signal?: AbortSignal) => call('GET', '/api/runs/files' + q({ run_dir }), undefined, signal),
  // `tail`: the table's newest `limit` rows, or (false) its first ones - Data tables' order choice (branch record SIF-99).
  table: (run_dir: string, table: string, limit = 25, signal?: AbortSignal, tail = true) => call('GET', '/api/runs/table' + q({ run_dir, table, limit, tail }), undefined, signal),
  logs: (run_dir: string, kind: string, signal?: AbortSignal) => call('GET', '/api/runs/logs' + q({ run_dir, kind, limit: 200 }), undefined, signal),
  // The Training tab (record 7.193): the run's recorded training numbers from flush record `flushes` on, plus the unpublished tail.
  training: (run_dir: string, flushes: number, signal?: AbortSignal, tail_cursor?: string | null) => call('GET', '/api/runs/training' + q({ run_dir, flushes, tail_cursor }), undefined, signal),
  exportCsv: (run_dir: string, table: string) => call('POST', '/api/runs/export-csv', { run_dir, table }),
  exportAggregates: (run_dir: string) => call('POST', '/api/aggregates/export', { run_dir }),
  downloadUrl: (run_dir: string, path: string) => '/api/runs/download' + q({ run_dir, path }),
  aggregatesUrl: (run_dir: string) => '/api/aggregates/download' + q({ run_dir }),          // the experiment's research CSVs, one zip
  // Corner check (backend corner_check.py): the plan is free; start asks for the real budget through launchWithConsent.
  cornerPlan: (run_dir: string, designs?: number, signal?: AbortSignal) => call('GET', '/api/runs/corner-check/plan' + q({ run_dir, designs }), undefined, signal),
  cornerStart: (body: Json) => call('POST', '/api/runs/corner-check/start', body),
  cornerStatus: (run_dir: string, check_id: string, signal?: AbortSignal) => call('GET', '/api/runs/corner-check/status' + q({ run_dir, check_id }), undefined, signal),
  cornerStop: (run_dir: string, check_id: string) => call('POST', '/api/runs/corner-check/stop', { run_dir, check_id }),
  // The Agent window (records 7.226, 7.253): the folder and the two CLIs found (free), one of them opened in a terminal window of its own,
  // and the free checklist of what a run still needs - no model is called, nothing is probed.
  agentClis: () => call('GET', '/api/agent/clis'),
  openCli: (cli: 'claude' | 'codex') => call('POST', '/api/agent/open', { cli }),
  agentReadiness: (config: Json) => call('POST', '/api/agent/readiness', { config }),
  // Load PDK (backend pdk.py): the PDKs loaded so far, one of them in full, and an explicit read through a connection.
  pdks: () => call('GET', '/api/pdks'),
  pdk: (pdk_id: string) => call('GET', '/api/pdks/' + encodeURIComponent(pdk_id)),
  loadPdk: (profile_id: string, technology_library: string | null, model_file: string | null) =>
    call('POST', '/api/pdks/load', { profile_id, technology_library, model_file }),
};

function save(name: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url; link.download = name; link.click();
  URL.revokeObjectURL(url);
}

/** Fetch a backend download and save it under the name the backend gives it (Content-Disposition); returns that name.
 *  A plain link would leave the workbench for a page of JSON when the file is missing: this throws the message instead. */
export async function download(url: string, fallbackName: string, init?: RequestInit): Promise<string> {
  const response = await fetch(url, init);
  if (!response.ok) { const data = await response.json().catch(() => null); throw new ApiError(response.status, data?.detail ?? data); }
  const header = response.headers.get('Content-Disposition') ?? '';
  const encoded = /filename\*=utf-8''([^;]+)/i.exec(header)?.[1];
  const name = (encoded ? decodeURIComponent(encoded) : /filename="([^"]+)"/i.exec(header)?.[1]) || fallbackName;
  save(name, await response.blob());
  return name;
}

export const downloadPackage = (run_dir: string) => download('/api/runs/export-package', 'run__data.zip',
  { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run_dir }) });

export const saveJson = (name: string, value: Json) => save(name, new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));

/** Puts text on the clipboard of `from`, the window the click happened in (branch record SIF-94): a browser refuses a write
 *  from a window that does not have focus, so a click in a pop-up copies through the pop-up's own clipboard, as the
 *  Connection, Agent and Runs windows do theirs; the main page's when none is given or it has closed. No clipboard here
 *  rejects too, so every caller can say "could not copy": it returned nothing then, and a refused write went unsaid. */
export const copy = (text: string, from?: Window | null): Promise<void> => {
  const at = from && !from.closed ? from : window;
  return at.navigator.clipboard?.writeText(text) ?? Promise.reject(new Error('no clipboard'));
};
// A backend that does not know a route yet answers 404 / 405: it has to be restarted. A blocked connection gate is said
// with the panel's `gateText`; anything else in the backend's own words.
export const OLDER_BACKEND = 'This backend is older than the page and cannot do this yet: restart it (gator_workbench.cli serve).';
export const problemText = (e: any, gateText?: (gate: Json) => string): string => e.status === 404 || e.status === 405 ? OLDER_BACKEND
  : e.detail?.gate && gateText ? gateText(e.detail.gate) : schemaProblem(e) ?? e.message;
/** A configuration the backend cannot read (HTTP 422 naming its fields, backend schema.describe_errors): said field by
 *  field, and where to fix it. "The configuration does not match the schema" alone left the reader guessing (user report
 *  2026-09-30: Matched devices on real:mscr_ldo1_rgcn). Each field by its place in the editors' and windows' words, as the
 *  header's list names it (branch record SIF-141: it read "run.max_evaluations: ..."); a row as "row N", as no configuration
 *  here names its ID. issuePlace.ts and the modules it loads import this file for its types alone, if at all. */
export function schemaProblem(e: any): string | null {
  const errors: Json[] = Array.isArray(e?.detail?.errors) ? e.detail.errors : [];
  if (!errors.length) return null;
  const them = errors.length === 1 ? 'it' : 'them';
  return `The configuration is not valid yet, so this cannot be done: ${errors.slice(0, 3).map(x => `${placeOf(String(x.path ?? ''), null, {})}: ${String(x.message ?? '').replace(/\.\s*$/, '')}`).join('; ')}`
    + `${errors.length > 3 ? `; and ${errors.length - 3} more` : ''}. Put ${them} right first - the red blocking-issues button in the header lists ${them} too.`;
}
/** A failed request in plain words: the backend's own sentence, or - when no answer came at all ("Failed to fetch") -
 *  what that means. Where a machine code is shown at all, it goes into a folded "Technical details". */
export const NO_ANSWER = 'The workbench backend did not answer: it may have stopped (start it again with gator_workbench.cli serve), or the connection to it dropped.';
export const plainError = (e: any): string => e instanceof ApiError ? schemaProblem(e) ?? e.message : e instanceof TypeError ? NO_ANSWER : String(e?.message ?? e);
/** The connection gate refused a Virtuoso read or write: ONE wording for every panel (Save task and the working cell used
 *  a copy without the connection-kind case, and told an ngspice connection to "bring the link up"). `then`: what to press
 *  once the link is up, said by a window that puts its own Connection... button beside the words (branch record SIF-108: the
 *  Virtuoso window, whose chain is read again by Refresh); the words then do not send the user to the workbench's button. */
export const gateText = (gate: Json, then?: string) => gate.blocking?.includes('connection_kind') ? (gate.next_steps?.[0] ?? 'This kind of connection cannot do that.')
  : `Virtuoso cannot be reached (${[...(gate.blocking ?? []), ...(gate.uncertain ?? [])].join(', ') || gate.status}). Bring the link up in the Connection window${
    then ? `, ${then}` : ' (the "Connection" button in the workbench), then try again'}.`;
