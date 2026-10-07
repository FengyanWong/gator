import { useState } from 'react';
import { createPortal } from 'react-dom';
import { api, Json, plainError } from '../api';
import { BLOCKED, usePopupWindow } from './popupWindow';

/** The Agent window (record 7.253; the user: "make the agent tab pop out window only (no tab view)", then "make it still a
 *  tab style but not button style"): "Agent...", first in the bottom panel's tab line and drawn as a tab, opens it - there is
 *  no tab view behind it any more (until 2026-10-07 the same line was the first bottom tab's content, record 7.226). The
 *  window holds two buttons that open Claude Code or Codex in a
 *  terminal window of its own, in the workbench's folder, started as the user starts it: their own settings decide what it
 *  may do, and the session is in their claude.ai or Codex history (backend agent_cli.py). What an agent should do - draft
 *  rows, read a run, help a design whose optimization is stuck - is asked there, in words: the workbench sends it nothing.
 *  "What's missing?" fills the lower part of the same window with the backend's free checklist of what a run still needs,
 *  worked out when it is pressed and never by itself. Opening the window reads which CLIs are installed (free); the page
 *  itself asks the backend nothing about agents. */

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

export function AgentWindowTab({ config }: { config: Json }) {
  const [found, setFound] = useState<Json>(null);         // GET /api/agent/clis: the folder and the two CLIs (free), read when the window opens
  const [said, setSaid] = useState<Json>(null);           // what the last CLI press came to: { level, text, command? }
  const [opening, setOpening] = useState<string | null>(null);
  const [check, setCheck] = useState<Json>(null);         // { report?, error?, at } of the last "What's missing?"
  const [checking, setChecking] = useState(false);
  const agent = usePopupWindow('gator-agent', { title: 'GATOR - agent', features: 'popup,width=780,height=760', rootId: 'agent-root' });

  // Opened inside the click (the pop-up rule). A window opened anew starts clean; one already open comes to the front. Either
  // way the CLIs are looked for again, so one installed since shows.
  const openWindow = () => {
    const wasOpen = !!agent.popup && !agent.popup.closed;
    agent.open();
    if (!wasOpen) { setSaid(null); setCheck(null); setFound(null); }
    api.agentClis().then(setFound).catch(e => setSaid({ level: 'error', text: plainError(e) }));
  };
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
  // Filled when the backend answers; a second press works the list out again from the configuration as it is now.
  const whatIsMissing = () => {
    setChecking(true);
    api.agentReadiness(config).then(report => setCheck({ report, at: clock() }))
      .catch(e => setCheck({ error: plainError(e), at: clock() })).finally(() => setChecking(false));
  };
  // The click happens in the agent window, so ITS clipboard is the one a browser lets this gesture write to.
  const copyCommand = (text: string) => (agent.popup ?? window).navigator.clipboard?.writeText(text);
  const cliOf = (cli: string): Json => (found?.clis ?? []).find((c: Json) => c.cli === cli);
  const directory = found?.directory ?? 'the workbench folder';
  const report = check?.report;
  const blocking = (report?.items ?? []).filter((i: Json) => i.status === 'missing' && i.id !== 'start').length;

  const view = agent.popup && agent.root && (<section className="panel agent-window" aria-labelledby="agent-title">
    <h2 id="agent-title">Agent: Claude Code or Codex</h2>
    <div className="agent-row">
      <span className="hint">In {directory}:</span>
      {CLIS.map(({ cli, name }) => { const c = cliOf(cli); return <button key={cli} className="agent-cli" disabled={!!opening || (!!found && !c?.available)}
        onClick={() => open(cli, name)} title={c && !c.available ? c.note : `Opens ${name} in a terminal window of its own, in ${directory}, `
          + `as you start it yourself: your own ${name} settings decide what it may do, and the session is in your ${cli === 'claude' ? 'claude.ai' : 'Codex'} history.`
          + (c?.executable ? `\n${c.executable}` : '')}>{opening === cli ? 'Opening...' : name}</button>; })}
      <span className="spacer" />
      <button className="missing" onClick={whatIsMissing} title="What's missing?: what this run still needs before it can start, and what to do about each - worked out by the workbench from the configuration as it is, shown below. Free: no agent, no simulation.">What's missing?</button>
    </div>
    <p className="hint agent-headline">Each button opens the CLI in a terminal window of its own, in this folder, as you start it yourself: your settings, your account, your history.</p>
    <details className="agent-help"><summary>What to ask it</summary>
      <p className="hint">Describe what you need in words, for example: "The run shown in the workbench is stuck on the gain spec: look at its designs and
        suggest what to change", or "Draft the Specs rows for this task from these requirements". The agent works in this folder with what your own settings
        allow: it can read the runs, the documentation and the code. Claude Code reads the project's rules (CLAUDE.md) by itself; tell Codex to read
        CLAUDE.md first. The workbench sends it nothing and does not wait for it.</p></details>
    {found?.clis?.filter((c: Json) => !c.available).map((c: Json) => <p key={c.cli} className="hint">{c.note}</p>)}
    {said && <p className={`agent-said ${said.level}`} role="status">{said.text}
      {said.command && <> <code>{said.command}</code> <button className="text-link" onClick={() => copyCommand(said.command)}>Copy</button></>}</p>}
    {(checking || check) && <section className="missing-list" aria-labelledby="missing-title">
      <h3 id="missing-title">What's missing before the run can start</h3>
      {checking && !check ? <p className="hint">Working it out...</p>
        : check?.error ? <p className="error">{check.error}</p>
        : report && <>
          <p className={`verdict ${report.ready ? 'ok' : 'warn'}`}>{report.ready ? 'Nothing blocks a start.'
            : `Not ready yet: ${blocking} item${blocking === 1 ? '' : 's'} block${blocking === 1 ? 's' : ''} a start. Next: ${report.next.title}.`}</p>
          <Checklist items={report.items} />
          <p className="hint">{report.note} Worked out at {check.at}{checking ? ' (working it out again...)' : ''}, from the configuration on the page:
            press "What's missing?" again after a change.</p></>}
    </section>}
  </section>);

  return (<>
    {agent.blocked && <span className="error run-list-blocked" role="alert">{BLOCKED}</span>}
    {/* Drawn as a tab (the strip's tab rules), never `active`: it shows nothing in the panel; `open` underlines it while its window is open. */}
    <button className={`agent-tab${agent.popup ? ' open' : ''}`} onClick={openWindow}
      title={agent.popup ? 'The agent window is open: press to bring it to the front.'
        : 'Opens the agent window: Claude Code or Codex in a terminal window of its own, in the workbench\'s folder, as you start it yourself - and "What\'s missing?", the free checklist of what the run still needs.'}>Agent...</button>
    {view && createPortal(view, agent.root!)}
  </>);
}
