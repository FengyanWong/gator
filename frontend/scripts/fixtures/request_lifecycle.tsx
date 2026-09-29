// Real React effects and production panels, with every API request held locally by the browser check.
import { StrictMode, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api } from '../../src/api';
import { usePolling } from '../../src/store';
import { DataTab, FilesTab, StatusTab } from '../../src/panels/RunTabs';

const pending: any[] = [], downloads: string[] = [];
function read(kind: string, run: string) {
  return new Promise((resolve, reject) => pending.push({ kind, run, done: false, resolve, reject }));
}
api.status = run => read('status', run);
api.table = (run, table) => read(table, run);
api.files = run => read('files', run);
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

function Poll({ run, interval, controls }: { run: string; interval: number; controls: boolean }) {
  const result = usePolling(() => api.status(run), interval, true, [run]);
  return <><pre id="result">{JSON.stringify(result)}</pre>{controls && <StatusTab status={result.value} onContinue={() => {}} />}</>;
}

function Fixture() {
  const [run, setRun] = useState('A'), [tab, setTab] = useState('poll'), [interval, setInterval] = useState(50);
  return <><select id="run" value={run} onChange={e => setRun(e.target.value)}><option>A</option><option>B</option></select>
    <select id="tab" value={tab} onChange={e => setTab(e.target.value)}>{['poll', 'data', 'files', 'status'].map(t => <option key={t}>{t}</option>)}</select>
    <input id="interval" type="number" value={interval} onChange={e => setInterval(Number(e.target.value))} />
    <div id="panel">{tab === 'data' ? <DataTab runDir={run} /> : tab === 'files' ? <FilesTab runDir={run} />
      : <Poll run={run} interval={interval} controls={tab === 'status'} />}</div></>;
}
createRoot(document.getElementById('root')!).render(<StrictMode><Fixture /></StrictMode>);
