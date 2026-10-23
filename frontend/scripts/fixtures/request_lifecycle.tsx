// Real React effects and production panels, with every API request held locally by the browser check.
import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api } from '../../src/api';
import { useRequest } from '../../src/store';
import { DATA_CHOICE, DataTab, FilesTab, LogsTab, StatusTab } from '../../src/panels/RunTabs';

const pending: any[] = [], downloads: string[] = [];
function read(kind: string, run: string, signal?: AbortSignal) {
  // Ignore abort deliberately: tests can deliver stale replies even after the transport was cancelled.
  return new Promise((resolve, reject) => pending.push({ kind, run, signal, done: false, resolve, reject }));
}
api.status = (run, signal) => read('status', run, signal);
api.table = (run, table, _limit, signal) => read(table, run, signal);
api.files = (run, signal) => read('files', run, signal);
api.logs = (run, kind, signal) => read(kind, run, signal);
// The Run status tab's one action that names a run is "Export status", which saves through a link's click: the name is
// kept here instead of downloaded (its run commands went on 2026-09-29; they are the header's).
HTMLAnchorElement.prototype.click = function () { downloads.push(this.download); };
(window as any).fixture = {
  pending, downloads,
  finish(kind: string, run: string, value: any, error = false) {
    const request = pending.find(p => !p.done && p.kind === kind && p.run === run);
    if (!request) throw new Error(`No pending ${kind} for ${run}`);
    request.done = true;
    if (error) request.reject(new Error('FIXTURE read failed')); else request.resolve(value);
  }
};

function Poll({ run, interval, timeout, controls }: { run: string; interval: number; timeout: number; controls: boolean }) {
  const result = useRequest(signal => api.status(run, signal), [run], { pollEvery: interval, timeoutMs: timeout });
  return <><button id="refresh" onClick={result.refresh}>Refresh</button><pre id="result">{JSON.stringify(result)}</pre>{controls && <StatusTab status={result.value} runDir={null} error={null} check={null} refusal={null} onContinue={() => {}} onDismissRefusal={() => {}} onFineTune={() => {}} continueBlocked={null} config={{}} setConfig={() => {}} />}</>;
}

function Fixture() {
  const [run, setRun] = useState('A'), [tab, setTab] = useState('poll'), [interval, setInterval] = useState(50);
  const [timeout, setTimeoutMs] = useState(30000);
  // the table and the log chosen, held above the tabs as the bottom panel holds them (branch record SIF-105)
  const [choice, setChoice] = useState(DATA_CHOICE), [kind, setKind] = useState('events');
  return <><select id="run" value={run} onChange={e => setRun(e.target.value)}><option>A</option><option>B</option></select>
    <select id="tab" value={tab} onChange={e => setTab(e.target.value)}>{['poll', 'data', 'files', 'status', 'logs'].map(t => <option key={t}>{t}</option>)}</select>
    <input id="interval" type="number" value={interval} onChange={e => setInterval(Number(e.target.value))} />
    <input id="timeout" type="number" value={timeout} onChange={e => setTimeoutMs(Number(e.target.value))} />
    <div id="panel">{tab === 'data' ? <DataTab runDir={run} status={null} choice={choice} setChoice={setChoice} /> : tab === 'files' ? <FilesTab runDir={run} />
      : tab === 'logs' ? <LogsTab runDir={run} alive={false} kind={kind} setKind={setKind} />
      : <Poll run={run} interval={interval} timeout={timeout} controls={tab === 'status'} />}</div></>;
}
createRoot(document.getElementById('root')!).render(<StrictMode><Fixture /></StrictMode>);
