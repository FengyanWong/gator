// Thin typed client for the local backend. Every request is same-origin JSON.
// The browser never sends hosts, ports, commands or arbitrary paths: the backend has no such fields.

export type Json = any;

export class ApiError extends Error {
  constructor(public status: number, public detail: Json) {
    // Agent errors carry {code, meaning, detail} rather than {message}; a plain HTTPException carries a string.
    super([detail?.message, detail?.detail, detail?.meaning, detail].find(v => typeof v === 'string' && v) ?? `HTTP ${status}`);
  }
}

async function call(method: string, url: string, body?: Json): Promise<Json> {
  const response = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  return answer(response);
}

async function answer(response: Response): Promise<Json> {
  const text = await response.text();
  let data: Json = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { message: text.slice(0, 500) }; }
  if (!response.ok) throw new ApiError(response.status, data?.detail ?? data);
  return data;
}

// An agent request whose answer arrives LIVE, as Server-Sent Events: `onProgress` gets the thinking summary and the reply
// text while they are written (backend agents/live.py). It ends like `call`: with the proposal, or with an ApiError(409)
// carrying the same detail. A server older than live answers ignores the Accept header and sends one JSON body: taken as is.
async function proposeLive(body: Json, onProgress: (event: Json) => void): Promise<Json> {
  const response = await fetch('/api/agent/propose', { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body) });
  if (!response.ok || !response.body || !(response.headers.get('Content-Type') ?? '').startsWith('text/event-stream')) return answer(response);
  const reader = response.body.getReader(), decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    for (let end = buffer.indexOf('\n\n'); end >= 0; end = buffer.indexOf('\n\n')) {
      const frame = buffer.slice(0, end), kind = /^event: ?(.*)$/m.exec(frame)?.[1], data = /^data: ?(.*)$/m.exec(frame)?.[1];
      buffer = buffer.slice(end + 2);
      if (!kind || data === undefined) continue;                  // a keep-alive comment while the agent works
      const payload = JSON.parse(data);
      if (kind === 'result') return payload;
      if (kind === 'error') throw new ApiError(409, payload);
      onProgress(payload);
    }
    if (done) throw new Error('the connection to the workbench server closed before the answer was complete');
  }
}

const q = (params: Record<string, string | number | boolean | undefined | null>) =>
  '?' + Object.entries(params).filter(([, v]) => v !== undefined && v !== null)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`).join('&');

export const api = {
  meta: () => call('GET', '/api/meta'),
  schema: () => call('GET', '/api/schema'),
  networkSettings: () => call('GET', '/api/network-settings'),
  saveNetworkSettings: (encoder: string, body: Json) => call('PUT', '/api/network-settings/' + encodeURIComponent(encoder), body),
  resetNetworkSettings: (encoder: string, to: string) => call('POST', '/api/network-settings/' + encodeURIComponent(encoder) + '/reset', { to }),
  tasks: () => call('GET', '/api/tasks'),
  starter: (taskKey: string) => call('GET', '/api/tasks/starter' + q({ task_key: taskKey })),
  loadCircuit: (circuit: Json) => call('POST', '/api/circuit/load', { circuit }),
  nativeLibraries: (profile_id: string) => call('POST', '/api/virtuoso/libraries', { profile_id }),
  nativeCells: (profile_id: string, library: string) => call('POST', '/api/virtuoso/cells', { profile_id, library }),
  nativeImport: (profile_id: string, library: string, cell: string, testbench: string | null) => call('POST', '/api/virtuoso/import', { profile_id, library, cell, testbench }),
  profileReference: (name: string) => call('POST', '/api/virtuoso/profile/reference', { name }),
  deleteProfile: (name: string) => call('POST', '/api/virtuoso/profile/delete', { name }),
  nativeRead: (profile_id: string, library: string, cell: string) => call('POST', '/api/virtuoso/read', { profile_id, library, cell }),
  workingCopy: (profile_id: string, library: string, cell: string) => call('POST', '/api/virtuoso/copy', { profile_id, library, cell }),
  setupRead: (profile_id: string, library: string, cell: string, config: Json | null) => call('POST', '/api/virtuoso/setup/read', { profile_id, library, cell, config }),
  taskSave: (body: Json) => call('POST', '/api/virtuoso/task/save', body),
  taskFile: (body: Json) => call('POST', '/api/virtuoso/task/file', body),
  taskFileCheck: (text: string) => call('POST', '/api/virtuoso/task/file/check', { text }),
  taskCheck: (profile_id: string | null, config: Json) => call('POST', '/api/virtuoso/task/check', { profile_id, config }),
  validate: (config: Json) => call('POST', '/api/config/validate', { config }),
  diff: (before: Json, after: Json) => call('POST', '/api/config/diff', { before, after }),
  browse: (path?: string) => call('GET', '/api/output/browse' + q({ path })),
  checkOutput: (path: string, create = false) => call('POST', '/api/output/check', { path, create }),
  connectionProfiles: () => call('GET', '/api/connection/profiles'),
  connectionStatus: (profile_id: string) => call('GET', '/api/connection/status' + q({ profile_id })),
  connectionCheck: (profile_id: string, scope: string, trigger = 'user') => call('POST', '/api/connection/check', { profile_id, scope, trigger }),
  connectionSetup: () => call('GET', '/api/connection/setup'),
  // { profile_id, kind, ssh_host?, bridge_profile? } - names only: never an address, a path or a command
  connectionCreateProfile: (body: Json) => call('POST', '/api/connection/profile', body),
  connectionConnect: (profile_id: string) => call('POST', '/api/connection/connect', { profile_id }),
  runs: (output_root?: string) => call('GET', '/api/runs' + q({ output_root })),
  model: (run_dir: string, checkpoint_id: string, config?: Json) => call('POST', '/api/runs/model', { run_dir, checkpoint_id, config }),
  defaultModel: (project: string) => call('GET', '/api/runs/default-model' + q({ project })),
  savedModels: (output_root?: string) => call('GET', '/api/runs/models' + q({ output_root })),
  modelStructure: (run_dir: string, checkpoint_id: string) => call('POST', '/api/runs/model/structure', { run_dir, checkpoint_id }),
  modelGraphView: (run_dir: string, checkpoint_id: string, evaluation: number | null) => call('POST', '/api/runs/model/graph-view', { run_dir, checkpoint_id, evaluation }),
  start: (body: Json) => call('POST', '/api/runs/start', body),
  continueRun: (body: Json) => call('POST', '/api/runs/continue', body),
  command: (run_dir: string, command: string) => call('POST', '/api/runs/command', { run_dir, command }),
  status: (run_dir: string) => call('GET', '/api/runs/status' + q({ run_dir })),
  files: (run_dir: string) => call('GET', '/api/runs/files' + q({ run_dir })),
  table: (run_dir: string, table: string, limit = 25) => call('GET', '/api/runs/table' + q({ run_dir, table, limit })),
  logs: (run_dir: string, kind: string) => call('GET', '/api/runs/logs' + q({ run_dir, kind, limit: 200 })),
  exportCsv: (run_dir: string, table: string) => call('POST', '/api/runs/export-csv', { run_dir, table }),
  exportAggregates: (run_dir: string) => call('POST', '/api/aggregates/export', { run_dir }),
  downloadUrl: (run_dir: string, path: string) => '/api/runs/download' + q({ run_dir, path }),
  aggregatesUrl: (run_dir: string) => '/api/aggregates/download' + q({ run_dir }),          // the experiment's research CSVs, one zip
  // Corner check (backend corner_check.py): the plan is free; start asks for the real budget through launchWithConsent.
  cornerPlan: (run_dir: string, designs?: number) => call('GET', '/api/runs/corner-check/plan' + q({ run_dir, designs })),
  cornerStart: (body: Json) => call('POST', '/api/runs/corner-check/start', body),
  cornerStatus: (run_dir: string, check_id: string) => call('GET', '/api/runs/corner-check/status' + q({ run_dir, check_id })),
  cornerStop: (run_dir: string, check_id: string) => call('POST', '/api/runs/corner-check/stop', { run_dir, check_id }),
  agentSettings: () => call('GET', '/api/agent/settings'),
  saveAgentSettings: (body: Json) => call('PUT', '/api/agent/settings', body),
  agentDiagnostics: () => call('GET', '/api/agent/diagnostics'),
  agentReadiness: (config: Json) => call('POST', '/api/agent/readiness', { config }),      // free: no model is called, nothing is probed
  proposeLive,              // POST /api/agent/propose: live events when the backend streams, else its plain JSON answer
  cancelAgent: (request_id: string) => call('POST', '/api/agent/cancel', { request_id }),
  exportTask: (body: Json) => call('POST', '/api/agent/export-task', body),
  importResult: (body: Json) => call('POST', '/api/agent/import-result', body),
  approve: (body: Json) => call('POST', '/api/agent/approve', body),
  apply: (body: Json) => call('POST', '/api/agent/apply', body),
  reject: (proposal_id: string) => call('POST', '/api/agent/reject', { proposal_id }),
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

export const copy = (text: string) => navigator.clipboard?.writeText(text);
export const bytes = (n?: number | null) => n == null ? '-' : n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KiB`
  : n < 1073741824 ? `${(n / 1048576).toFixed(1)} MiB` : `${(n / 1073741824).toFixed(2)} GiB`;
export const num = (v: unknown) => typeof v === 'number' ? (Number.isInteger(v) ? String(v) : v.toPrecision(6)) : v == null ? '' : String(v);
