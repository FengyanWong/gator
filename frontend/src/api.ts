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
  resetNetworkSettings: (encoder: string, to: string) => call('POST', '/api/network-settings/' + encodeURIComponent(encoder) + '/reset', { to }),
  tasks: () => call('GET', '/api/tasks'),
  starter: (taskKey: string) => call('GET', '/api/tasks/starter' + q({ task_key: taskKey })),
  loadCircuit: (circuit: Json) => call('POST', '/api/circuit/load', { circuit }),
  modifyCircuit: (body: Json) => call('POST', '/api/circuit/modify', body),
  nativeLibraries: (profile_id: string) => call('POST', '/api/virtuoso/libraries', { profile_id }),
  nativeCells: (profile_id: string, library: string) => call('POST', '/api/virtuoso/cells', { profile_id, library }),
  nativeImport: (profile_id: string, library: string, cell: string, testbench: string | null) => call('POST', '/api/virtuoso/import', { profile_id, library, cell, testbench }),
  createProfile: (config: Json, name: string, recipe: string, expected_frequency_hz: number | null) => call('POST', '/api/virtuoso/profile', { config, name, recipe, expected_frequency_hz }),
  profilePreflight: (name: string, profile_id: string) => call('POST', '/api/virtuoso/profile/preflight', { name, profile_id }),
  profileReference: (name: string) => call('POST', '/api/virtuoso/profile/reference', { name }),
  nativeRead: (profile_id: string, library: string, cell: string) => call('POST', '/api/virtuoso/read', { profile_id, library, cell }),
  validate: (config: Json) => call('POST', '/api/config/validate', { config }),
  diff: (before: Json, after: Json) => call('POST', '/api/config/diff', { before, after }),
  browse: (path?: string) => call('GET', '/api/output/browse' + q({ path })),
  checkOutput: (path: string, create = false) => call('POST', '/api/output/check', { path, create }),
  connectionProfiles: () => call('GET', '/api/connection/profiles'),
  connectionStatus: (profile_id: string) => call('GET', '/api/connection/status' + q({ profile_id })),
  connectionCheck: (profile_id: string, scope: string, trigger = 'user') => call('POST', '/api/connection/check', { profile_id, scope, trigger }),
  connectionSetup: () => call('GET', '/api/connection/setup'),
  connectionCreateProfile: (profile_id: string) => call('POST', '/api/connection/profile', { profile_id }),
  connectionConnect: (profile_id: string) => call('POST', '/api/connection/connect', { profile_id }),
  runs: (output_root?: string) => call('GET', '/api/runs' + q({ output_root })),
  suggestMode: (config: Json, source_run_dir?: string | null) => call('POST', '/api/runs/suggest-mode', { config, source_run_dir }),
  model: (run_dir: string, checkpoint_id: string, config?: Json) => call('POST', '/api/runs/model', { run_dir, checkpoint_id, config }),
  defaultModel: (project: string) => call('GET', '/api/runs/default-model' + q({ project })),
  savedModels: (output_root?: string) => call('GET', '/api/runs/models' + q({ output_root })),
  modelStructure: (run_dir: string, checkpoint_id: string) => call('POST', '/api/runs/model/structure', { run_dir, checkpoint_id }),
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
  agentSettings: () => call('GET', '/api/agent/settings'),
  saveAgentSettings: (body: Json) => call('PUT', '/api/agent/settings', body),
  agentDiagnostics: () => call('GET', '/api/agent/diagnostics'),
  agentReadiness: (config: Json) => call('POST', '/api/agent/readiness', { config }),      // free: no model is called, nothing is probed
  propose: (body: Json) => call('POST', '/api/agent/propose', body),
  cancelAgent: (request_id: string) => call('POST', '/api/agent/cancel', { request_id }),
  exportTask: (body: Json) => call('POST', '/api/agent/export-task', body),
  importResult: (body: Json) => call('POST', '/api/agent/import-result', body),
  approve: (body: Json) => call('POST', '/api/agent/approve', body),
  apply: (body: Json) => call('POST', '/api/agent/apply', body),
  reject: (proposal_id: string) => call('POST', '/api/agent/reject', { proposal_id }),
};

export async function downloadPackage(run_dir: string) {
  const response = await fetch('/api/runs/export-package', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ run_dir }),
  });
  if (!response.ok) throw new ApiError(response.status, await response.json().catch(() => ({})));
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url; link.download = 'run__data.zip'; link.click();
  URL.revokeObjectURL(url);
}

export function saveJson(name: string, value: Json) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url; link.download = name; link.click();
  URL.revokeObjectURL(url);
}

export const copy = (text: string) => navigator.clipboard?.writeText(text);
export const bytes = (n?: number | null) => n == null ? '-' : n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KiB`
  : n < 1073741824 ? `${(n / 1048576).toFixed(1)} MiB` : `${(n / 1073741824).toFixed(2)} GiB`;
export const num = (v: unknown) => typeof v === 'number' ? (Number.isInteger(v) ? String(v) : v.toPrecision(6)) : v == null ? '' : String(v);
