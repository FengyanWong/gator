import { Fragment, ReactNode, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, ApiError, bytes, copy, downloadPackage, Json, num, saveJson } from '../api';
import { usePolling } from '../store';
import { DiffView } from './Editors';

const TABLES = ['evaluations', 'parameters', 'metrics', 'simulator_jobs', 'learner_updates', 'transitions', 'states'];

// What a reply lists besides its text. These are shown in the side window next to the message box, not in the chat.
const NOTE_GROUPS: { key: string; title: string; css: string; text: (item: Json) => string }[] = [
  { key: 'errors', title: 'Errors', css: 'issue error', text: e => `${e.path || '(configuration)'}: ${e.message}` },
  { key: 'problems', title: 'Problems', css: 'issue error', text: String },
  { key: 'unresolved', title: 'Unresolved', css: 'issue unresolved', text: String },
  { key: 'warnings', title: 'Warnings', css: 'warn', text: String },
];
const CUSTOM = '__custom__';          // value of the "Custom..." entry of the agent-model list; never sent to the backend
const noteGroups = (m: Json) => NOTE_GROUPS.map(g => ({ ...g, items: (Array.isArray(m?.extra?.[g.key]) ? m.extra[g.key] : []) as Json[] })).filter(g => g.items.length > 0);
const WHO: Record<string, string> = { user: 'You', system: 'Workbench', checklist: 'Workbench - run readiness', error: 'Error', manual_import: 'Imported result' };
const MARK: Record<string, [string, string]> = { done: ['\u2714', 'ok'], missing: ['\u2718', 'error'], warning: ['!', 'warn'], unknown: ['?', 'hint'],
  not_applicable: ['\u2013', 'hint'], at_start: ['\u25B6', 'hint'] };
const ASK_READINESS = 'What is still missing before this RL run can start? List it in order and fix what you can.';

// One start checklist, from the backend (title/detail) or from an agent reply (item/basis). Same marks for both.
function Checklist({ items }: { items: Json[] }) {
  return <ul className="checklist">{items.map((c, i) => { const [mark, css] = MARK[c.status] ?? MARK.unknown; return <li key={i} className={`check-${c.status}`}>
    <span className={`check-mark ${css}`}>{mark}</span><b>{c.title ?? c.item}</b>{c.status !== 'done' && c.status !== 'not_applicable' && <span className="check-who">{c.who === 'agent' ? 'agent can draft it' : 'yours'}</span>}
    <span className="check-detail"> {c.detail ?? c.basis}</span>{c.action && c.status !== 'done' && <div className="check-action">{c.action}</div>}</li>; })}</ul>;
}
const who = (role: string) => WHO[role] ?? `Agent (${role})`;

// Agents answer in light Markdown. Only `code`, **bold**, bullet / numbered lists and paragraphs are shown as such,
// and only as React text nodes - a reply is data and is never parsed as HTML.
const inline = (text: string): ReactNode[] => text.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/).map((part, i) =>
  part.length > 2 && part.startsWith('`') && part.endsWith('`') ? <code key={i}>{part.slice(1, -1)}</code>
    : part.length > 4 && part.startsWith('**') && part.endsWith('**') ? <b key={i}>{part.slice(2, -2)}</b> : <Fragment key={i}>{part}</Fragment>);
function RichText({ text }: { text: string }) {
  const blocks: { list: 'ul' | 'ol' | null; lines: string[] }[] = [];
  for (const line of String(text ?? '').split('\n')) {
    const item = /^\s*(?:[-*•]|(\d+)[.)])\s+(.*)$/.exec(line);
    const list = item ? (item[1] ? 'ol' : 'ul') : null;
    const last = blocks[blocks.length - 1];
    if (!line.trim()) blocks.push({ list: null, lines: [] });                       // a blank line ends the paragraph
    else if (last && last.list === list && (list || last.lines.length)) last.lines.push(item ? item[2] : line);
    else blocks.push({ list, lines: [item ? item[2] : line] });
  }
  return <>{blocks.filter(b => b.lines.length).map((b, i) => b.list === 'ul' ? <ul key={i}>{b.lines.map((l, j) => <li key={j}>{inline(l)}</li>)}</ul>
    : b.list === 'ol' ? <ol key={i}>{b.lines.map((l, j) => <li key={j}>{inline(l)}</li>)}</ol>
      : <p key={i}>{b.lines.map((l, j) => <Fragment key={j}>{j > 0 && <br />}{inline(l)}</Fragment>)}</p>)}</>;
}

// Stays mounted while another bottom tab is shown (`hidden`): unmounting would drop the chat, a pending
// request's indicator and the proposal it returns, while the backend keeps working on that request.
export function AgentTab({ config, setConfig, request, clearRequest, hidden }:
  { config: Json; setConfig: (c: Json) => void; request: { kind: string; selection: Json[]; prompt?: string } | null; clearRequest: () => void; hidden?: boolean }) {
  const [settings, setSettings] = useState<Json>(null);
  const [diagnostics, setDiagnostics] = useState<Json>(null);
  const [prompt, setPrompt] = useState('');
  const [kind, setKind] = useState('draft_config');
  const [selection, setSelection] = useState<Json[]>([]);
  const [log, setLog] = useState<Json[]>([]);
  const [proposal, setProposal] = useState<Json>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [waited, setWaited] = useState(0);          // whole seconds the pending request has been out
  const chat = useRef<HTMLDivElement>(null);
  const [focus, setFocus] = useState<number | null>(null);    // chat line whose notes the side window shows; null = the latest reply
  const [customModel, setCustomModel] = useState(false);      // "Custom..." chosen: a model name outside the list is being typed
  const [popup, setPopup] = useState<Window | null>(null);    // while set, the conversation is shown in its own browser window
  const [manual, setManual] = useState('');
  const [circuitDiff, setCircuitDiff] = useState<Json>(null);
  // Prompt-driven circuit modification: proposal -> structured diff -> confirmation -> WORKING COPY -> reload.
  const circuitChange = async (confirmed: boolean) => {
    try {
      const result = await api.modifyCircuit({ circuit: config.circuit, changes: proposal.circuit_changes, confirmed, output_root: config.output?.output_root ?? null });
      setCircuitDiff(result);
      if (result.applied) say('system', `Working copy written: ${result.working_copy}. The original (${result.original_untouched}) is untouched. ${result.note}`);
    } catch (e) { fail(e); }
  };
  const isReply = (m: Json) => m.role !== 'user' && m.role !== 'system' && m.role !== 'checklist';
  const say = (role: string, text: string, extra?: Json) => {
    setLog(l => [...l, { role, text, extra, at: new Date().toLocaleTimeString([], { hour12: false }) }]);
    if (isReply({ role })) setFocus(null);          // a new reply takes the side window back from an older line
  };

  // Detaching moves only the DOM: the component (chat, pending request, proposal, settings) stays where it is and is
  // drawn through a portal into a window of its own, so nothing has to be synchronised between two windows.
  const detach = () => {
    const opened = window.open('', 'gator-agent-conversation', 'popup,width=1180,height=900');
    if (!opened) { say('error', 'The browser blocked the new window. Allow pop-ups for this page, then detach again.'); return; }
    const doc = opened.document;
    doc.title = 'GATOR - agent conversation';
    doc.head.querySelectorAll('link, style').forEach(node => node.remove());          // a window of that name may be reused
    document.querySelectorAll<HTMLElement>('link[rel="stylesheet"], style').forEach(node => {
      const copy = node.cloneNode(true) as HTMLElement;
      if (node instanceof HTMLLinkElement) (copy as HTMLLinkElement).href = node.href;   // absolute: the new window is about:blank
      doc.head.appendChild(copy);
    });
    doc.body.innerHTML = '<div id="agent-root"></div>';
    setPopup(opened);
  };
  const attach = () => { popup?.close(); setPopup(null); };
  useEffect(() => {
    if (!popup) return;
    const back = () => setPopup(null);                     // the window was closed with its own close button
    const close = () => popup.close();                     // the workbench page is leaving: do not leave a dead window behind
    popup.addEventListener('pagehide', back);
    window.addEventListener('pagehide', close);
    return () => { popup.removeEventListener('pagehide', back); window.removeEventListener('pagehide', close); };
  }, [popup]);

  useEffect(() => { api.agentSettings().then(setSettings).catch(e => say('error', e.message)); }, []);
  // A panel may hand over a written-out request (the Virtuoso source does). It only fills the box: never sent by itself,
  // and text the user is already typing is kept.
  useEffect(() => { if (request) { setKind(request.kind); setSelection(request.selection); if (request.prompt) setPrompt(current => current || request.prompt!); clearRequest(); } }, [request]);
  useEffect(() => {
    if (!busy) return;
    const started = Date.now();
    setWaited(0);
    const timer = setInterval(() => setWaited(Math.round((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, [busy]);
  useEffect(() => { if (chat.current) chat.current.scrollTop = chat.current.scrollHeight; }, [log, busy, hidden, popup]);
  const body = () => ({ kind, prompt, config, selection });
  // Only an ApiError is an answer from the backend; anything else means no answer arrived at all.
  // A bare "Not Found" / "Method Not Allowed" comes from the web framework, not from an endpoint: the running server has
  // no such route. The page is served from disk and is always current, the server only after a restart - say that.
  const olderServer = (e: any) => e instanceof ApiError && (e.status === 404 || e.status === 405) && typeof e.detail === 'string';
  const fail = (e: any) => say('error', olderServer(e)
    ? 'The workbench server that is running is older than this page and does not have this function yet. Restart it (Ctrl+C in its terminal, then start `serve` again) and press the button again. Nothing was sent to an agent.'
    : e instanceof ApiError
      ? `${e.detail?.code ?? 'error'}: ${e.message}${e.detail?.configuration_unchanged ? ' (your configuration is unchanged)' : ''}`
      : `No answer from the backend (${e?.message ?? e}). Check that the workbench server is still running.`, e?.detail);

  const propose = async (ask?: { text: string; kind: string }) => {
    const text = (ask?.text ?? prompt).trim();
    if (!text || busy) return;
    if (settings?.provider === 'disabled') { say('system', 'Not sent: the provider is "disabled". Choose claude_code or codex on the left, or use "Export task description".'); return; }
    const request_id = crypto.randomUUID().replace(/-/g, '');
    const started = Date.now(), sent_with = using;          // what THIS request runs on, whatever is chosen later
    setBusy(request_id); say('user', text); if (!ask) setPrompt('');
    try { const p = await api.propose({ ...body(), kind: ask?.kind ?? kind, prompt: text, request_id }); setProposal(p); say(p.origin, p.reasoning || '(no reasoning given)', { ...p, sent_with }); }
    catch (e: any) {
      if (e.detail?.code === 'cancelled') say('system', `Cancelled by you after ${Math.round((Date.now() - started) / 1000)} s. The request had been sent and the agent was still working on it; nothing was changed.`);
      else fail(e);
      if (!ask) setPrompt(current => current || text);          // hand the text back for a retry unless something new was typed
    } finally { setBusy(null); }
  };
  // Free: the backend works it out from the live configuration. No model is called and nothing is probed.
  const whatIsMissing = () => api.agentReadiness(config).then(r => say('checklist', r.ready ? 'Nothing blocks a start.'
    : `Not ready yet. Next: ${r.next.title} - ${r.next.detail}`, r)).catch(fail);
  const cancel = () => busy && api.cancelAgent(busy).then(r => {
    if (!r.cancelled) say('system', 'Nothing to cancel: the backend has no running agent process for this request (it may have just finished).');
  }).catch(fail);
  const approveAndApply = async () => {
    try {
      await api.approve({ proposal_id: proposal.proposal_id, proposal_hash: proposal.proposal_hash, config });
      const applied = await api.apply({ proposal_id: proposal.proposal_id, config });
      setConfig(applied.config); setProposal(null); say('system', applied.note);
    } catch (e) { fail(e); setProposal(null); }
  };
  // Model / effort lists of the selected provider (served by the backend; absent until it is restarted with them).
  const catalog: Json = settings?.catalog?.[settings?.provider];
  const listed: Json = catalog?.models.find((m: Json) => m.id === settings?.model);
  const isCustom = customModel || (!!settings?.model && !listed);
  const efforts: string[] = listed ? listed.efforts : catalog?.efforts ?? [];
  const effortIgnored = !!listed && listed.efforts.length === 0;
  const cliDefault: Json = catalog?.cli_default;
  const defaultEffort = settings?.model ? cliDefault?.efforts_by_model?.[settings.model] : cliDefault?.effort;
  // What the next request will run on. A value the CLI picks itself is the one read from the user's CLI settings and is labelled as such.
  const modelShown = settings?.model ?? (cliDefault?.model ? `${cliDefault.model} (CLI default)` : 'CLI default');
  const effortShown = effortIgnored ? 'not used by this model' : settings?.effort ?? (defaultEffort ? `${defaultEffort} (CLI default)` : 'CLI default');
  const using = !settings || settings.provider === 'disabled' ? null : `${modelShown}, effort ${effortShown}`;
  const save = (patch: Json) => {
    const next = { ...settings, ...patch };
    setSettings(next);
    return api.saveAgentSettings({ provider: next.provider, model: next.model ?? null, effort: next.effort ?? null, timeout_seconds: next.timeout_seconds,
      permission_mode: next.permission_mode, allowed_tools: next.allowed_tools, max_turns: next.max_turns, stream: next.stream })
      .catch(fail).then(() => api.agentSettings().then(setSettings).catch(fail));          // always show what is actually saved
  };
  const latest = log.reduce((found, m, i) => (isReply(m) ? i : found), -1);
  const shown = focus ?? latest;
  const shownGroups = shown >= 0 ? noteGroups(log[shown]) : [];
  const view = (
    <div className={`agent${popup ? ' detached' : ''}`} style={hidden && !popup ? { display: 'none' } : undefined}>
      <div className="agent-side">
        <button className="detach" onClick={popup ? attach : detach} title={popup ? 'Close this window and show the conversation in the workbench again' : 'Show the conversation in a window of its own, with more room. Nothing is lost or restarted.'}>
          {popup ? 'Bring back into the workbench' : 'Detach into its own window'}</button>
        {/* The two CLIs share neither models nor effort levels, so a provider change starts both from the CLI default. */}
        <label>Provider<select value={settings?.provider ?? 'disabled'} onChange={e => { setCustomModel(false); save({ provider: e.target.value, model: null, effort: null }); }}>
          {(settings?.availability ?? []).map((a: Json) => <option key={a.provider} value={a.provider}>{a.provider}{a.available ? '' : ' (CLI not found)'}</option>)}</select></label>
        {settings && settings.provider !== 'disabled' && <>
          <label title="Agent model. Independent of the RL model/checkpoint.">Agent model
            {catalog && <select value={isCustom ? CUSTOM : settings.model ?? ''} onChange={e => {
              const id = e.target.value; setCustomModel(id === CUSTOM);
              if (id === CUSTOM) { setSettings({ ...settings, model: null }); return; }      // empty box; saved when it loses focus
              const entry = catalog.models.find((m: Json) => m.id === id);
              save({ model: id || null, effort: !entry || entry.efforts.includes(settings.effort) ? settings.effort : null });
            }}>
              <option value="">CLI default{cliDefault?.model ? ` (${cliDefault.model})` : ''}</option>
              {catalog.models.map((m: Json) => <option key={m.id} value={m.id}>{m.label}</option>)}
              <option value={CUSTOM}>Custom...</option></select>}
            {(isCustom || !catalog) && <input autoFocus={customModel} value={settings.model ?? ''} placeholder={catalog ? 'exact model name' : 'CLI default'}
              onChange={e => setSettings({ ...settings, model: e.target.value || null })} onBlur={() => { if (!settings.model) setCustomModel(false); save({}); }} />}</label>
          {catalog && <label className={effortIgnored ? 'disabled' : ''} title="How hard the agent thinks. Independent of any RL setting.">Effort
            <select disabled={effortIgnored} value={effortIgnored ? '' : settings.effort ?? ''} onChange={e => save({ effort: e.target.value || null })}>
              <option value="">{effortIgnored ? 'ignored by this model' : `CLI default${defaultEffort ? ` (${defaultEffort})` : ''}`}</option>
              {efforts.map(level => <option key={level}>{level}</option>)}</select></label>}
          <p className="hint">{catalog
            ? <>{listed?.note ?? (isCustom ? 'A name outside the list is passed to the CLI as typed.' : catalog.default_note)} {catalog.caveat} List checked {catalog.verified}; showing it calls no model.</>
            : 'Restart the workbench server to get the model and effort lists.'}</p></>}
        <button onClick={() => api.agentDiagnostics().then(setDiagnostics).catch(fail)}>Diagnostics</button>
        {diagnostics && <details open><summary>Backend environment</summary><pre className="small">{JSON.stringify({ providers: diagnostics.providers, skills: diagnostics.skills.summary, nested: diagnostics.environment.nested_session_note, cwd: diagnostics.environment.cwd }, null, 1)}</pre></details>}
        <p className="hint">Agents prepare proposals only. Applying a configuration, writing a circuit and running a real simulation each need their own authorization. Every manual workflow works without an agent.</p>
      </div>
      <div className="agent-main">
        <div className="agent-using"><span>{using ? <>Next request: <b>{settings.provider}</b>, model <b>{modelShown}</b>, effort <b>{effortShown}</b></>
          : 'No agent is selected (provider: disabled). Choose one on the left, or use "Export task description".'}</span>
          <button className="missing" onClick={whatIsMissing} title="Worked out by the workbench itself from the current configuration: free, no agent request.">What's missing to start?</button></div>
        <div className="chat" ref={chat}>
          {log.length === 0 && !busy && <p className="hint chat-empty">"What's missing to start?" lists what this run still needs - free, no agent. Or ask below for a draft of the parameters, targets or measurements. The agent only proposes: you review a diff before anything changes.</p>}
          {log.map((m, i) => { const groups = noteGroups(m); return <div key={i} className={`msg ${isReply(m) && m.role !== 'error' ? 'reply' : m.role}${focus === i ? ' focused' : ''}`}>
            <div className="who">{who(m.role)}{m.extra?.sent_with && <span className="when">{m.extra.sent_with}</span>} <span className="when">{m.at}</span></div>
            <div className="text">{m.role === 'user' ? m.text : <RichText text={m.text} />}</div>
            {m.role === 'checklist' && <><Checklist items={m.extra.items} />
              <div className="row">{m.extra.items.some((c: Json) => c.status === 'missing' && c.who === 'agent') && <button disabled={!!busy || !using} onClick={() => propose({ text: ASK_READINESS, kind: 'readiness' })}
                title={using ? `One agent request (${using}). It sees this checklist and proposes the rows it can; you review the diff.` : 'Select a provider first.'}>Ask the agent to fix what it can</button>}
                <span className="hint">{m.extra.note}</span></div></>}
            {isReply(m) && m.extra?.checklist?.length > 0 && <Checklist items={m.extra.checklist} />}
            {groups.length > 0 && <button className="notes-link" title="Show these in the side window" onClick={() => setFocus(i === latest ? null : i)}>{groups.map(g => `${g.items.length} ${g.title.toLowerCase()}`).join(', ')}</button>}</div>; })}
          {busy && <div className="msg pending"><div className="who">{who(settings?.provider ?? 'agent')}</div>
            <div className="text">Sent. Waiting for the agent's reply... <b>{waited} s</b></div>
            <div className="hint">The answer arrives in one piece, so nothing shows until it is complete; the request is stopped after {settings?.timeout_seconds ?? 300} s.</div></div>}</div>
        {/* Left: the proposal under review and the message box. Right: the side window, as tall as both. */}
        <div className="compose"><div className="compose-main">
        {proposal && <div className="confirm"><h4>Proposal from {proposal.origin} - review the diff</h4><DiffView diff={proposal.diff} />
          {proposal.circuit_changes?.length > 0 && <div><h4>Proposed circuit changes ({proposal.circuit_changes.length})</h4>
            <table className="grid small"><tbody>{proposal.circuit_changes.map((c: Json, i: number) => <tr key={i}><td>{c.instance_path}.{c.parameter_name}</td><td>{num(c.new_value)} {c.unit}</td><td>{c.reason}</td></tr>)}</tbody></table>
            {circuitDiff?.diff && <table className="grid small"><thead><tr><th>Parameter</th><th>Before</th><th>After (canonical)</th></tr></thead><tbody>
              {circuitDiff.diff.map((d: Json, i: number) => <tr key={i}><td>{d.instance_path}.{d.parameter_name}</td><td>{num(d.before)} ({d.before_expression})</td><td>{num(d.after)}</td></tr>)}</tbody></table>}
            <button onClick={() => circuitChange(false)}>Preview circuit diff</button>
            <button disabled={!circuitDiff?.diff || circuitDiff.applied} onClick={() => (popup ?? window).confirm('Write a WORKING COPY of the netlist with these changes? The original is never overwritten, and no native schematic is generated.') && circuitChange(true)}>Confirm: write working copy</button>
          </div>}
          <button disabled={!proposal.diff.length} onClick={approveAndApply}>Approve and apply to the configuration</button>
          <button onClick={() => api.reject(proposal.proposal_id).then(() => setProposal(null))}>Reject</button>
          <span className="hint"> The approval is bound to this exact proposal, configuration and circuit; any later change invalidates it.</span></div>}
        {/* Enter sends, Shift+Enter breaks the line. An Enter that confirms an IME candidate (isComposing / 229) must not send. */}
        <textarea value={prompt} onChange={e => setPrompt(e.target.value)} rows={3}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey && !e.nativeEvent.isComposing && e.keyCode !== 229) { e.preventDefault(); propose(); } }}
          placeholder="Describe what you need. State where each requirement comes from; the agent may not invent requirements. Enter sends, Shift+Enter starts a new line." />
        <div className="row">
          <select title="What the agent may change" value={kind} onChange={e => setKind(e.target.value)}>{['draft_config', 'parameters', 'targets', 'measurements', 'modify_fields', 'circuit_modification', 'readiness'].map(k => <option key={k}>{k}</option>)}</select>
          {kind === 'modify_fields' && <span className="hint">{selection.length} selected row(s)</span>}
          <button disabled={!prompt.trim() || !!busy || settings?.provider === 'disabled'} onClick={() => propose()} title="Enter in the text box does the same">{busy ? `Waiting for the agent... ${waited} s` : 'Ask agent for a proposal'}</button>
          {busy && <button onClick={cancel}>Cancel request</button>}
          <button disabled={!prompt.trim()} onClick={() => api.exportTask(body()).then(t => saveJson('agent_task.json', t)).catch(fail)}>Export task description</button>
        </div>
        <details><summary>Import a structured result (manual workflow)</summary>
          <textarea value={manual} onChange={e => setManual(e.target.value)} rows={3} placeholder="Paste the JSON object returned by any assistant" />
          <button disabled={!manual.trim() || !prompt.trim()} onClick={() => { try { api.importResult({ ...body(), result: JSON.parse(manual) }).then(p => { setProposal(p); say(p.origin, p.reasoning, p); }).catch(fail); } catch (e: any) { say('error', 'Not valid JSON: ' + e.message); } }}>Validate and show diff</button></details>
        </div>
        {/* Side window: what a reply lists besides its text. The inner box is absolutely placed so a long list scrolls instead of stretching the row. */}
        <aside className="notes"><div className="notes-scroll">
          <div className="notes-head">Warnings, unresolved, errors{shown >= 0 && <> - {who(log[shown].role)} {log[shown].at}</>}
            {focus !== null && <button className="notes-link" onClick={() => setFocus(null)}>back to the latest reply</button>}</div>
          {shown < 0 ? <p className="hint">What a reply lists besides its text appears here instead of in the chat.</p>
            : shownGroups.length === 0 ? <p className="hint">Nothing listed for this reply.</p>
            : shownGroups.map(g => <div key={g.key}><div className={`notes-title ${g.css}`}>{g.title} ({g.items.length})</div>
              <ul>{g.items.map((item, j) => <li key={j} className={g.css}>{g.text(item)}</li>)}</ul></div>)}
        </div></aside></div>
      </div>
    </div>
  );
  const root = popup?.document.getElementById('agent-root');
  if (!popup || !root) return view;
  return (<>
    {createPortal(view, root)}
    <div className="agent-away" style={hidden ? { display: 'none' } : undefined}>
      <p>The agent conversation is open in a window of its own. It keeps working while you use the other tabs here.</p>
      <div className="row"><button onClick={() => popup.focus()}>Show that window</button><button onClick={attach}>Bring it back here</button></div>
    </div></>);
}

export function StatusTab({ status, onCommand, onContinue }: { status: Json; onCommand: (c: string) => void; onContinue: () => void }) {
  if (!status) return <p className="hint">No run selected.</p>;
  const b = status.budget, best = status.best_design, first = status.first_feasible, conn = status.connection;
  return (<div className="status-grid">
    {status.manifest?.mock && <p className="mock">{status.manifest.mock_notice}</p>}
    <table className="grid small"><tbody>
      <tr><td>State</td><td><b>{status.state}</b>{status.stop_reason ? ` (${status.stop_reason})` : ''}{status.worker_alive ? ' - worker alive' : ''}</td></tr>
      <tr><td>Mode / model</td><td>{status.mode} {status.manifest?.source_model?.run_id ? `from ${status.manifest.source_model.run_id.slice(0, 12)} / ${status.manifest.source_model.checkpoint_id}` : '(no weights loaded)'}</td></tr>
      <tr><td>Budget</td><td>{b ? `${b.charged} charged / ${b.max_evaluations}  (in flight ${b.in_flight}, completed ${b.completed}, failed ${b.failed}, remaining ${b.remaining})` : '-'}</td></tr>
      <tr><td>Spectre launches</td><td>{b ? `${b.launches}${b.max_launches ? ' / ' + b.max_launches : ''}  (retries ${b.retries}, cache hits ${b.cache_hits})` : '-'}</td></tr>
      <tr><td>Active workers</td><td>{(status.active_workers ?? []).map((w: Json) => `#${w.worker_id}: ${w.phase} attempt ${w.attempt}`).join('; ') || 'none'} (concurrency {status.concurrency})</td></tr>
      <tr><td>Learner updates</td><td>{status.learner_updates}</td></tr>
      <tr><td>First feasibility</td><td>{first ? `at ${first.first_feasible_eval_count} evaluations charged (dispatch #${first.dispatch_index}, ${first.completed_count} completed, ${first.in_flight_count} in flight, ${first.spectre_launches} launches)` : 'not yet (null)'}</td></tr>
      <tr><td>Best design</td><td>{best ? `${best.feasible ? 'FEASIBLE' : 'infeasible'}  ${Object.entries(best.metrics).map(([k, v]) => `${k}=${num(v)}`).join(' ')}  violation ${num(best.violation)}` : 'none'}</td></tr>
      <tr><td>Connection</td><td><span className={`badge state-${conn?.overall}`}>{conn?.overall}</span>{conn?.age_seconds != null && ` ${Math.round(conn.age_seconds)} s old`}</td></tr>
      <tr><td>Persistence</td><td className={status.persistence?.failed ? 'error' : ''}>{status.persistence ? `commit ${status.persistence.last_commit_seq}, flushed ${status.persistence.flushed_seq}, ${bytes(status.persistence.bytes_written)} table data; last save ${status.persistence.last_successful_save ?? '-'}` : '-'} {status.persistence?.failed ?? ''}</td></tr>
      <tr><td>Last checkpoint</td><td>{status.last_checkpoint_utc ?? '-'}</td></tr>
      <tr><td>Run directory</td><td className="path" onClick={() => copy(status.run_dir)}>{status.run_dir}</td></tr>
      {status.error && <tr><td>Error</td><td className="error">{status.error}</td></tr>}
    </tbody></table>
    <div className="row">
      <button disabled={!status.worker_alive} onClick={() => onCommand('pause')}>Pause and save</button>
      <button disabled={!status.worker_alive} onClick={() => onCommand('stop')}>Stop and save</button>
      <button disabled={!status.worker_alive} onClick={() => onCommand('cancel')} title="Forced: unfinished evaluations are recorded as cancelled and stay charged.">Force cancel</button>
      <button disabled={status.worker_alive || !['paused', 'stopped', 'interrupted'].includes(status.state)} onClick={onContinue}>Continue</button>
    </div>
  </div>);
}

export function DataTab({ runDir }: { runDir: string | null }) {
  const [table, setTable] = useState('evaluations');
  const [data, setData] = useState<Json>(null);
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => { if (runDir) api.table(runDir, table).then(setData).catch(e => setNote(e.message)); else setData(null); }, [runDir, table]);
  if (!runDir) return <p className="hint">No run selected.</p>;
  return (<div>
    <div className="row"><select value={table} onChange={e => setTable(e.target.value)}>{TABLES.map(t => <option key={t}>{t}</option>)}</select>
      <button onClick={() => api.table(runDir, table).then(setData)}>Refresh</button>
      <button onClick={() => api.exportCsv(runDir, table).then(r => setNote(`CSV written: ${r.path}`)).catch(e => setNote(e.message))}>Export detailed CSV</button>
      <button onClick={() => api.exportAggregates(runDir).then(r => setNote(`Aggregates: ${r.experiment_dir}/aggregates`)).catch(e => setNote(e.message))}>Export research CSVs</button>
      <span className="hint">{data ? `${data.total_rows} rows (snapshot at commit ${data.cutoff_commit_seq}); last ${data.rows.length} shown` : ''} {note}</span></div>
    {data && <div className="scroll"><table className="grid small"><thead><tr>{data.columns.map((c: string) => <th key={c}>{c}</th>)}</tr></thead>
      <tbody>{data.rows.map((r: Json, i: number) => <tr key={i}>{data.columns.map((c: string) => <td key={c}>{typeof r[c] === 'object' && r[c] !== null ? JSON.stringify(r[c]) : num(r[c])}</td>)}</tr>)}</tbody></table></div>}
  </div>);
}

export function FilesTab({ runDir }: { runDir: string | null }) {
  const [files, setFiles] = useState<Json>(null);
  const refresh = () => runDir && api.files(runDir).then(setFiles);
  useEffect(() => { refresh(); }, [runDir]);
  if (!runDir) return <p className="hint">No run selected.</p>;
  return (<div><div className="row"><button onClick={refresh}>Refresh</button><button onClick={() => downloadPackage(runDir)}>Download data-only package (.zip)</button>
    <button onClick={() => copy(runDir)}>Copy run path</button><span className="hint">{files && `${files.files.length} files, ${bytes(files.total_bytes)}`} "Open local folder" is not offered: no desktop integration is available from a browser.</span></div>
    <div className="scroll"><table className="grid small"><thead><tr><th>File</th><th>Size</th><th>Modified (UTC)</th><th></th></tr></thead>
      <tbody>{files?.files.map((f: Json) => <tr key={f.path}><td>{f.path}</td><td>{bytes(f.bytes)}</td><td>{f.modified_utc.slice(0, 19)}</td><td><a href={api.downloadUrl(runDir, f.path)}>download</a></td></tr>)}</tbody></table></div></div>);
}

export function LogsTab({ runDir, alive }: { runDir: string | null; alive: boolean }) {
  const [kind, setKind] = useState('events');
  const { value } = usePolling(() => api.logs(runDir!, kind), alive ? 2000 : 60000, !!runDir, [runDir, kind]);
  if (!runDir) return <p className="hint">No run selected.</p>;
  return (<div><div className="row"><select value={kind} onChange={e => setKind(e.target.value)}><option>events</option><option>errors</option></select></div>
    <div className="scroll log">{(value?.entries ?? []).slice().reverse().map((e: Json, i: number) => <div key={i} className={kind === 'errors' ? 'error' : ''}>
      <b>{(e.time_utc ?? '').slice(11, 19)} {e.event ?? e.error}</b> {JSON.stringify(Object.fromEntries(Object.entries(e).filter(([k]) => !['time_utc', 'event', 'error', 'run_id', 'traceback'].includes(k))))}</div>)}</div></div>);
}
