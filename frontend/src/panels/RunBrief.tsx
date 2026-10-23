import { useState } from 'react';
import { api, Json } from '../api';
import { clock, durationWhole as span, folderName, runTask, sig, taskNameOf, timeLine, TIME_LINE_HELP } from '../format';
import { startedFrom } from '../lineage';
import { openRunsAt } from '../openAt';
import { usePopupWindow } from './popupWindow';
import { Blocked, PopupPortal } from './popupParts';
import { Icon } from './Icons';
import { runMode } from './rlModelText';
import { RUNNING_WINDOW } from '../contract';
import { cardLive, isLive, type RunControl } from '../runState';

/** The run brief (record 7.264; plan "The run brief", added by record 7.259 - user: "pressing the green running text on
 *  banner will show you small popup window showing the running runs brief"). The header's run chip opens a small window of
 *  its own, "Running now": a card for the header's run, in any state, then one for every other live run under the output
 *  folder (another browser tab, the command line, a task's baseline). It only shows. Show results puts a run in the bottom
 *  tabs - what the chip's press did until then - and closes the window, as the Runs window's Show results does (branch
 *  record SIF-110); Open in Runs opens the Runs window at it; the header's buttons stay the only run controls. No timer of
 *  its own: the header's card follows the header's status poll, and the other cards are read when the window opens and by
 *  Refresh, with the time they were read. */

const ago = (utc?: string | null) => {
  const at = utc ? Date.parse(utc) : NaN;
  return Number.isNaN(at) ? null : `${span(Math.max(0, (Date.now() - at) / 1000))} ago`;
};

/** One run's card. `row`: its line of the run list (its name, task and lineage); `status`: its status (the header's poll for
 *  the header's run, a read when the window opened for the others). */
function BriefCard({ dir, row, status, header, byDir, from, onShow }: { dir: string; row: Json | null; status: Json | null; header: boolean;
  byDir: Map<string, Json>; from: Window; onShow: (dir: string) => void }) {
  const budget = status?.budget;
  const used: number | null = budget?.charged ?? row?.evaluations ?? null, total: number | null = budget?.max_evaluations ?? row?.max_evaluations ?? null;
  const live = cardLive(status, row);
  const working: number | null = status?.active_seconds ?? row?.active_seconds ?? null;
  const first = status?.first_feasible?.first_feasible_eval_count ?? row?.first_feasible_eval_count ?? null;
  const best = status?.best_design;
  const mock = status?.mock ?? status?.manifest?.mock ?? row?.mock;
  const share = used != null && total ? Math.min(100, Math.round(used / total * 100)) : 0;
  const origin = row ? startedFrom(row, byDir).text : '-';
  // The task and the Mode as the Runs window names them (branch record SIF-44: "real:mscr_ota7t · scratch", and a baseline
  // read "scratch" too); the task's key in the tooltip. A real run's word takes the line's " · " (branch record SIF-78: a bare
  // "real" after "model graphgps_ldo1 (31)" read as part of the model's name); MOCK keeps its badge.
  return <section className="brief-card" data-run-dir={dir} aria-label={folderName(dir)}>
    <div className="brief-title"><b title={row?.task_key ?? status?.manifest?.task_id ?? dir}>{row ? runTask(row)
        : status?.manifest?.task_id ? taskNameOf(status.manifest.task_id) : folderName(dir)}</b>
      <span> · {runMode(row ?? { mode: status?.mode, run_kind: status?.manifest?.run_kind }) || 'Mode unknown'} · {row?.model_label ? `model ${row.model_label}` : 'no model saved'}</span>
      {mock ? <>{' '}<span className="badge model-tag mock-tag">MOCK</span></> : <span className="hint brief-data"> · real data</span>}</div>
    <div className="hint brief-where">{header ? "In this page's header" : "Not in this page's header"} · {status?.state ?? row?.state ?? 'unknown state'}</div>
    <div className="brief-progress" title={used != null && total ? `${used} of ${total} evaluations` : undefined}>
      <span className="brief-bar"><span style={{ width: `${share}%` }} /></span>
      <span className="brief-count">{used ?? '?'} / {total ?? '?'} evaluations</span></div>
    {/* the working time as the Runs window's Duration names it, "so far" while live (branch record SIF-78: "worked 5 min 01 s"
        here, "4 min 23 s so far" there, for one number); not "Running for" - the header's card can be a paused or ended run.
        The line is format.ts timeLine, which Run status and the run chip show too (branch record SIF-98). */}
    <div className="hint brief-time" title={TIME_LINE_HELP}>{timeLine(working, used, total, live) ?? 'No working time yet'}</div>
    <div>{first != null ? `First feasible design at evaluation ${first}` : 'None feasible yet'}
      {/* three digits, as Run status writes it (SIF-44: "reward -0.0370463") */}
      {best ? ` · best so far: ${typeof best.reward === 'number' ? `reward ${sig(best.reward)}` : 'no reward recorded'}${best.feasible ? ', meets every spec' : ''}` : ''}</div>
    <div className="hint">{origin === '-' ? 'No model loaded' : `Started from ${origin}`} · last save point {ago(status?.last_checkpoint_utc) ?? 'none yet'}</div>
    {/* Show results closes the window, as Show results in the Runs window closes that one (record 7.291, user request
        2026-10-09: "after selecting one target task, model or run, close the pop up window"; branch record SIF-110: this one
        stayed over the page, the tabs it had just changed behind it). Refresh and Open in Runs keep it open. */}
    <div className="row">
      <button onClick={() => { onShow(dir); from.close(); }} title="Show results: the bottom tabs show this run (Run status, Logs, Data tables...). Nothing else changes. The window then closes.">Show results</button>
      <button onClick={() => openRunsAt({ run_dir: dir, from })} title="Open in Runs: the Runs window opens at this run, its Details open.">Open in Runs</button>
    </div>
  </section>;
}

export function useRunBrief({ control, runs, onRefreshRuns, onShow }: { control: RunControl; runs: Json[]; onRefreshRuns: () => Promise<Json[]>;
  onShow: (dir: string) => void }) {
  const { popup, root, blocked, open: openPopup } = usePopupWindow('gator-running',
    { title: RUNNING_WINDOW, features: 'popup,width=470,height=540', rootId: 'running-root' });
  const [others, setOthers] = useState<{ row: Json; status: Json | null }[]>([]);
  const [readAt, setReadAt] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  // The other live runs: the run list read again, and each one's status - once, when the window opens, and by Refresh.
  const read = async () => {
    setReading(true);
    try {
      const list = await onRefreshRuns();
      const live = list.filter(r => isLive(r) && r.run_dir !== control.dir);
      const statuses = await Promise.all(live.map(r => api.status(r.run_dir).catch(() => null)));
      setOthers(live.map((row, i) => ({ row, status: statuses[i] })));
    } finally { setReading(false); setReadAt(clock()); }
  };
  const open = () => { openPopup(); void read(); };
  const byDir = new Map(runs.map(r => [r.run_dir, r]));
  const view = popup && root && (
    <div className="run-brief">
      {/* Refresh is the refresh icon, as the bottom tabs' and the list windows' (branch record SIF-113), its word for screen
          readers and at the start of its tooltip; "Reading..." beside it says when it reads. Centred on the heading by
          roadster.css's icon block: on the head line's baseline an icon alone stands high. */}
      <div className="row brief-head"><h2>Running now</h2>
        <button onClick={() => void read()} disabled={reading} title="Refresh: read the run list and the other live runs again."><Icon name="refresh" label="Refresh" /></button>
        <span className="hint">{reading ? 'Reading...' : readAt ? `read at ${readAt}` : ''}</span></div>
      {control.dir ? <BriefCard dir={control.dir} row={byDir.get(control.dir) ?? null} status={control.status?.run_dir === control.dir ? control.status : null}
          header byDir={byDir} from={popup} onShow={onShow} />
        : <p className="hint">The header holds no run.</p>}
      {others.filter(o => o.row.run_dir !== control.dir).map(o => <BriefCard key={o.row.run_dir} dir={o.row.run_dir} row={o.row} status={o.status}
        header={false} byDir={byDir} from={popup} onShow={onShow} />)}
      {!reading && !others.some(o => o.row.run_dir !== control.dir) && <p className="hint brief-none">
        {control.dir ? 'Nothing else is live' : 'Nothing is live'} under this output folder{readAt ? ` (read at ${readAt})` : ''}.</p>}
    </div>);
  return { open, element: <>{blocked && <Blocked as="span" className="error run-brief-blocked" />}<PopupPortal popup={popup} root={root}>{view}</PopupPortal></> };
}
