import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, copy, Json, plainError } from '../api';
import { BLOCKED, usePopupWindow } from './popupWindow';

/** The Agent tab, minimal since 2026-10-06 (record 7.226; the user: "rewrite the whole agent tab to minimal"). Two buttons
 *  open Claude Code or Codex in a terminal window of its own, in the workbench's folder, started as the user starts it:
 *  their own settings decide what it may do, and the session is in their claude.ai or Codex history (backend
 *  agent_cli.py). What an agent should do - draft rows, read a run, help a design whose optimization is stuck - is asked
 *  there, in words: the workbench sends it nothing. "What's missing?" opens the backend's free checklist of what a run
 *  still needs, in a window of its own, worked out when it is pressed and never by itself. */

const MARK: Record<string, [string, string]> = { done: ['✔', 'ok'], missing: ['✘', 'error'], warning: ['!', 'warn'], unknown: ['?', 'hint'],
  not_applicable: ['–', 'hint'], at_start: ['▶', 'hint'] };
const CLIS: { cli: 'claude' | 'codex'; name: string }[] = [{ cli: 'claude', name: 'Claude Code' }, { cli: 'codex', name: 'Codex' }];
const clock = () => new Date().toLocaleTimeString([], { hour12: false });

/** The start checklist: each item, whose step it is, and what to do about it. */
function Checklist({ items }: { items: Json[] }) {
  return <ul className="checklist">{items.map((c, i) => { const [mark, css] = MARK[c.status] ?? MARK.unknown; return <li key={i} className={`check-${c.status}`}>
    <span className={`check-mark ${css}`}>{mark}</span><b>{c.title}</b>{c.status !== 'done' && c.status !== 'not_applicable' && <span className="check-who">{c.who === 'agent' ? 'an agent can help' : 'yours'}</span>}
    <span className="check-detail"> {c.detail}</span>{c.action && c.status !== 'done' && <div className="check-action">{c.action}</div>}</li>; })}</ul>;
}

// Stays mounted while another bottom tab is shown (`hidden`): the "What's missing?" window it draws stays open and filled.
export function AgentTab({ config, hidden }: { config: Json; hidden?: boolean }) {
  const [found, setFound] = useState<Json>(null);         // GET /api/agent/clis: the folder and the two CLIs (free)
  const [said, setSaid] = useState<Json>(null);           // what the last press came to: { level, text, command? }
  const [opening, setOpening] = useState<string | null>(null);
  const [check, setCheck] = useState<Json>(null);         // { report?, error?, at } of the last "What's missing?"
  const [checking, setChecking] = useState(false);
  const missing = usePopupWindow('gator-whats-missing', { title: 'GATOR - what is missing', features: 'popup,width=780,height=820', rootId: 'missing-root' });
  useEffect(() => { api.agentClis().then(setFound).catch(e => setSaid({ level: 'error', text: plainError(e) })); }, []);

  const open = async (cli: 'claude' | 'codex', name: string) => {
    setOpening(cli); setSaid(null);
    try {
      const opened = await api.openCli(cli);
      setSaid(opened.opened ? { level: 'ok', text: `${name} opens in a new window (${opened.terminal}), in ${opened.directory}. ${clock()}` }
        : { level: 'hint', text: `${opened.note} Start it yourself:`, command: opened.command });
    } catch (e: any) {
      setSaid({ level: 'error', text: `${name} was not opened: ${plainError(e)}`, command: e?.detail?.command });
    } finally { setOpening(null); }
  };
  // Opened inside the click (the pop-up rule), filled when the backend answers. A second press brings the window to the
  // front and works the list out again from the configuration as it is now.
  const whatIsMissing = () => {
    missing.open();
    setChecking(true);
    api.agentReadiness(config).then(report => setCheck({ report, at: clock() }))
      .catch(e => setCheck({ error: plainError(e), at: clock() })).finally(() => setChecking(false));
  };
  const cliOf = (cli: string): Json => (found?.clis ?? []).find((c: Json) => c.cli === cli);
  const report = check?.report;
  const blocking = (report?.items ?? []).filter((i: Json) => i.status === 'missing' && i.id !== 'start').length;

  return (<div className="agent" style={hidden ? { display: 'none' } : undefined}>
    <div className="agent-row">
      <span className="hint">In {found?.directory ?? 'the workbench folder'}:</span>
      {CLIS.map(({ cli, name }) => { const c = cliOf(cli); return <button key={cli} className="agent-cli" disabled={!!opening || (!!found && !c?.available)}
        onClick={() => open(cli, name)} title={c && !c.available ? c.note : `Opens ${name} in a terminal window of its own, in ${found?.directory ?? 'the workbench folder'}, `
          + `as you start it yourself: your own ${name} settings decide what it may do, and the session is in your ${cli === 'claude' ? 'claude.ai' : 'Codex'} history.`
          + (c?.executable ? `\n${c.executable}` : '')}>{opening === cli ? 'Opening...' : name}</button>; })}
      <span className="spacer" />
      <button className="missing" onClick={whatIsMissing} title="What's missing?: what this run still needs before it can start, and what to do about each - worked out by the workbench from the configuration as it is, in a window of its own. Free: no agent, no simulation.">What's missing?</button>
    </div>
    <p className="hint agent-headline">Each button opens the CLI in a terminal window of its own, in this folder, as you start it yourself: your settings, your account, your history.</p>
    <details className="agent-help"><summary>What to ask it</summary>
      <p className="hint">Describe what you need in words, for example: "The run shown in the workbench is stuck on the gain spec: look at its designs and
        suggest what to change", or "Draft the Specs rows for this task from these requirements". The agent works in this folder with what your own settings
        allow: it can read the runs, the documentation and the code. Claude Code reads the project's rules (CLAUDE.md) by itself; tell Codex to read
        CLAUDE.md first. The workbench sends it nothing and does not wait for it.</p></details>
    {found?.clis?.filter((c: Json) => !c.available).map((c: Json) => <p key={c.cli} className="hint">{c.note}</p>)}
    {said && <p className={`agent-said ${said.level}`} role="status">{said.text}
      {said.command && <> <code>{said.command}</code> <button className="text-link" onClick={() => copy(said.command)}>Copy</button></>}</p>}
    {missing.blocked && <p className="error" role="alert">{BLOCKED}</p>}
    {missing.popup && missing.root && createPortal(<section className="panel missing-window" aria-labelledby="missing-title">
      <h2 id="missing-title">What's missing before the run can start</h2>
      {checking && !check ? <p className="hint">Working it out...</p>
        : check?.error ? <p className="error">{check.error}</p>
        : report && <>
          <p className={`verdict ${report.ready ? 'ok' : 'warn'}`}>{report.ready ? 'Nothing blocks a start.'
            : `Not ready yet: ${blocking} item${blocking === 1 ? '' : 's'} block${blocking === 1 ? 's' : ''} a start. Next: ${report.next.title}.`}</p>
          <Checklist items={report.items} />
          <p className="hint">{report.note} Worked out at {check.at}{checking ? ' (working it out again...)' : ''}, from the configuration on the page:
            press "What's missing?" in the Agent tab again after a change.</p></>}
    </section>, missing.root)}
  </div>);
}
