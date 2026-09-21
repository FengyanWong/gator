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
// What identifies a selected row at a glance, per table (a row has twenty-odd fields; the editors show them all).
const ROW_KEY: Record<string, string> = { parameters: 'variable_id', targets: 'metric_id', measurements: 'measurement_id' };
const ROW_FACTS: Record<string, string[]> = { parameters: ['instance_path', 'parameter_name', 'lower', 'upper', 'unit', 'initial_value', 'binding_group'],
  targets: ['constraint', 'lower', 'upper', 'target', 'unit', 'measurement_id', 'hard', 'active'], measurements: ['analysis', 'result_source', 'source_name', 'unit'] };
const brief = (v: unknown) => typeof v !== 'number' ? String(num(v)) : v !== 0 && (Math.abs(v) < 1e-3 || Math.abs(v) >= 1e6) ? v.toExponential(3).replace(/\.?0+e/, 'e') : String(+v.toPrecision(6));   // 1e-6 and 0.9, not 0.00000100000 and 0.900000
const CUSTOM = '__custom__';          // value of the "Custom..." entry of the agent-model list; never sent to the backend
const noteGroups = (m: Json) => NOTE_GROUPS.map(g => ({ ...g, items: (Array.isArray(m?.extra?.[g.key]) ? m.extra[g.key] : []) as Json[] })).filter(g => g.items.length > 0);
const WHO: Record<string, string> = { user: 'You', system: 'Workbench', checklist: 'Workbench - run readiness', error: 'Error', manual_import: 'Imported result' };
const MARK: Record<string, [string, string]> = { done: ['\u2714', 'ok'], missing: ['\u2718', 'error'], warning: ['!', 'warn'], unknown: ['?', 'hint'],
  not_applicable: ['\u2013', 'hint'], at_start: ['\u25B6', 'hint'] };
const ASK_READINESS = 'What is still missing before this RL run can start? List it in order and fix what you can.';
const ASK_SETTINGS = 'Review the settings of this run - run configuration, RL network, RL training, output - and suggest what to change, each with its source.';
const WEB_TIMEOUT_SECONDS = 900;      // = agents/settings_review.py: reading publications takes minutes
const getIn = (config: Json, path: string) => path.split('.').reduce((node: Json, part) => node?.[part], config) ?? null;
const setIn = (config: Json, path: string, value: Json): Json => { const [head, ...rest] = path.split('.');
  return { ...config, [head]: rest.length ? setIn(config?.[head] ?? {}, rest.join('.'), value) : value }; };

// Suggestions of a settings review. Nothing is applied by the agent or the backend: "Apply" is the user's own edit of that
// setting, the same as typing the value into its panel, and the page's static validation follows it as usual.
function Suggestions({ extra, config, setConfig }: { extra: Json; config: Json; setConfig: (c: Json) => void }) {
  const rows: Json[] = extra.suggestions ?? [];
  const open = rows.filter(s => s.applicable && getIn(config, s.path) !== s.value);
  return <div className="suggestions">
    {rows.length > 0 && <table className="grid small"><thead><tr><th>Setting</th><th>Now</th><th>Suggested</th><th>Why, and where it comes from</th><th></th></tr></thead><tbody>
      {rows.map((s, i) => { const live = getIn(config, s.path), applied = live === s.value, now = live ?? s.now;      // a setting the page never touched shows the backend's default
        return <tr key={i} className={applied ? 'applied' : ''}>
        <td><span className="hint">{s.panel}</span><br /><b>{s.path.split('.').pop()}</b></td><td>{brief(now)}</td><td><b>{brief(s.value)}</b></td>
        <td>{s.reason} <span className="hint">Source: {s.source || 'none given'}</span>{s.url && <> <a href={s.url} target="_blank" rel="noreferrer">open</a></>}
          {s.quote && <div className="quote">"{s.quote}"</div>}{s.problem && !applied && <div className="error">{s.problem}</div>}{s.alone && !applied && <div className="warn">{s.alone}</div>}</td>
        <td>{applied ? <span className="ok">applied</span> : <button disabled={!s.applicable} onClick={() => setConfig(setIn(config, s.path, s.value))}>Apply</button>}</td></tr>; })}</tbody></table>}
    {rows.length > 0 && <div className="row"><button disabled={!open.length || !extra.suggestions_together?.ok} onClick={() => setConfig(open.reduce((c, s) => setIn(c, s.path, s.value), config))}
      title={extra.suggestions_together?.ok ? 'Sets every legal suggestion at once.' : `Together they would not be valid: ${extra.suggestions_together?.problem ?? ''}`}>Apply all ({open.length})</button>
      <span className="hint">Each row was tried on a copy of your configuration by the workbench. Applying is your own edit of that setting; nothing else changes.</span></div>}
    {extra.refused_suggestions?.length > 0 && <p className="hint">Left out - not something an agent may suggest: {extra.refused_suggestions.join('; ')}</p>}
    {extra.encoder_ideas?.length > 0 && <div className="ideas"><b>Encoders that do not exist here yet</b>
      <ul>{extra.encoder_ideas.map((e: Json, i: number) => <li key={i}><b>{e.name}</b> <span className="hint">{e.source}</span>{e.url && <> <a href={e.url} target="_blank" rel="noreferrer">open</a></>}<br />{e.why} <span className="hint">What it takes: {e.what_it_takes}</span></li>)}</ul>
      <p className="hint">The agent cannot add an encoder. It is a change of the optimizer's code, and that changes the fingerprint every saved model and the recorded audits are checked against - a decision for you, carried out in a development session.</p></div>}
  </div>;
}
const ASK_MINIMAL = 'Make this run able to start with as few changes as possible. Keep every valid row as it is, and mark every value I did not give you as PROVISIONAL.';
const provisional = (p: Json) => String(p.value?.basis ?? p.basis ?? '').trim().toUpperCase().startsWith('PROVISIONAL');

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
export function AgentTab({ config, setConfig, request, clearRequest, hidden, tabSlot, onDetached }:
  { config: Json; setConfig: (c: Json) => void; request: { kind: string; selection: Json[]; prompt?: string } | null; clearRequest: () => void; hidden?: boolean;
    tabSlot?: HTMLElement | null; onDetached?: (detached: boolean) => void }) {
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
  const [online, setOnline] = useState(false);               // settings review: THIS request may read publication sites (never saved)
  const [busyOnline, setBusyOnline] = useState(false);
  const [showSelection, setShowSelection] = useState(false);  // modify_fields: the rows the request may change, listed on demand
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
  useEffect(() => { onDetached?.(!!popup); }, [popup]);
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
  const body = () => ({ kind, prompt, config, selection, web: kind === 'settings_review' && online });
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
    const web = (ask?.kind ?? kind) === 'settings_review' && online && settings?.provider === 'claude_code';
    setBusy(request_id); setBusyOnline(web); say('user', text); if (!ask) setPrompt('');
    try { const p = await api.propose({ ...body(), kind: ask?.kind ?? kind, web, prompt: text, request_id }); if (p.kind !== 'settings_review') setProposal(p);   // a settings review patches nothing: no diff to approve, and an open proposal stays
      say(p.origin, p.reasoning || '(no reasoning given)', { ...p, sent_with }); }
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
        {/* Detaching is the small control on the "Agent" tab. This window has no tab strip, so the way back is here. */}
        {popup && <button className="detach" onClick={attach} title="Close this window and show the conversation in the workbench again">Bring back into the workbench</button>}
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
          {/* The review button closes the line at its right end; its option stands in front of it. */}
          <span className="agent-actions">
            <label className="check" title="For the next settings review only. The agent may search the web and open publication sites (arXiv, IEEE Xplore, ACM, OpenReview, GitHub...) and nothing else. It is told the kind of circuit and your settings, nothing of the design itself. Slower (minutes) and heavier on usage. Claude Code provider only.">
              <input type="checkbox" checked={online && settings?.provider === 'claude_code'} disabled={settings?.provider !== 'claude_code'} onChange={e => setOnline(e.target.checked)} />check publications online</label>
            <button disabled={!!busy || !using} onClick={() => propose({ text: ASK_SETTINGS, kind: 'settings_review' })}
              title={using ? `One agent request (${using}). It looks at the run configuration, the RL network, the RL training settings and the output settings - not at your circuit - and suggests values, each with its source. You apply them one by one.` : 'Select a provider first.'}>Review settings</button></span></div>
        <div className="chat" ref={chat}>
          {log.length === 0 && !busy && <p className="hint chat-empty">"What's missing to start?" lists what this run still needs - free, no agent. Or ask below for a draft of the Parameters, Specs or Probes tab. The agent only proposes: you review a diff before anything changes.</p>}
          {log.map((m, i) => { const groups = noteGroups(m); return <div key={i} className={`msg ${isReply(m) && m.role !== 'error' ? 'reply' : m.role}${focus === i ? ' focused' : ''}`}>
            <div className="who">{who(m.role)}{m.extra?.sent_with && <span className="when">{m.extra.sent_with}</span>} <span className="when">{m.at}</span></div>
            <div className="text">{m.role === 'user' ? m.text : <RichText text={m.text} />}</div>
            {m.role === 'checklist' && <><Checklist items={m.extra.items} />
              <div className="row">{m.extra.items.some((c: Json) => c.status === 'missing' && c.who === 'agent') && <>
                <button className="primary" disabled={!!busy || !using} onClick={() => propose({ text: ASK_MINIMAL, kind: 'minimal_start' })}
                  title={using ? `One agent request (${using}). The smallest change of the three tables after which the run can start: valid rows stay untouched (the backend enforces it), and a value you did not give is taken only from the circuit or the recorded baseline and marked PROVISIONAL. You review the diff.` : 'Select a provider first.'}>Make it startable with the fewest changes</button>
                <button disabled={!!busy || !using} onClick={() => propose({ text: ASK_READINESS, kind: 'readiness' })}
                  title={using ? `One agent request (${using}). It assumes nothing: it writes only the rows you gave every number for, and asks for the rest.` : 'Select a provider first.'}>Fix only what needs no assumption</button></>}
                <span className="hint">{m.extra.note}</span></div></>}
            {isReply(m) && m.extra?.checklist?.length > 0 && <Checklist items={m.extra.checklist} />}
            {isReply(m) && m.extra?.kind === 'settings_review' && <Suggestions extra={m.extra} config={config} setConfig={setConfig} />}
            {groups.length > 0 && <button className="notes-link" title="Show these in the side window" onClick={() => setFocus(i === latest ? null : i)}>{groups.map(g => `${g.items.length} ${g.title.toLowerCase()}`).join(', ')}</button>}</div>; })}
          {busy && <div className="msg pending"><div className="who">{who(settings?.provider ?? 'agent')}</div>
            <div className="text">{busyOnline ? 'Sent. The agent is searching and reading publications online - this takes minutes...' : "Sent. Waiting for the agent's reply..."} <b>{waited} s</b></div>
            <div className="hint">The answer arrives in one piece, so nothing shows until it is complete; the request is stopped after {busyOnline ? Math.max(settings?.timeout_seconds ?? 300, WEB_TIMEOUT_SECONDS) : settings?.timeout_seconds ?? 300} s.</div></div>}</div>
        {/* Left: the proposal under review and the message box. Right: the side window, as tall as both. */}
        <div className="compose"><div className="compose-main">
        {proposal && <div className="confirm"><h4>Proposal from {proposal.origin} - review the diff</h4><DiffView diff={proposal.diff} />
          {proposal.patch?.some(provisional) && <div className="provisional"><b>Provisional values - placeholders, not your requirements:</b>
            <ul>{proposal.patch.filter(provisional).map((p: Json, i: number) => <li key={i}><code>{p.section}/{p.key}</code> {String(p.value?.basis ?? p.basis)}</li>)}</ul></div>}
          {proposal.readiness_after && <p className={`verdict ${proposal.readiness_after.ready ? 'ok' : 'warn'}`} title={proposal.readiness_after.note}>
            {proposal.readiness_after.ready ? 'After you approve: nothing blocks a start.'
              : <>After you approve, still missing: {proposal.readiness_after.remaining.map((r: Json) => `${r.title} (${r.who === 'agent' ? 'agent can draft it' : 'yours'})`).join(', ') || 'see the blocking issues'}.</>}
            <span className="hint"> {proposal.readiness_after.changed_rows} row(s) changed{proposal.readiness_after.resolved.length > 0 && `; resolves ${proposal.readiness_after.resolved.join(', ')}`}. Checked by the workbench, not by the agent.</span></p>}
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
          placeholder="Describe what you need. State where each requirement comes from; the agent may not invent requirements." />
        <div className="row">
          <select title="What the agent may change" value={kind} onChange={e => setKind(e.target.value)}>{['draft_config', 'parameters', 'targets', 'measurements', 'modify_fields', 'circuit_modification', 'readiness', 'minimal_start', 'settings_review'].map(k => <option key={k}>{k}</option>)}</select>
          {kind === 'modify_fields' && <button className="notes-link" aria-expanded={showSelection} onClick={() => setShowSelection(open => !open)}
            title="The rows this request may change. They are chosen in the editors with 'Modify selected with agent...'.">{selection.length} selected row(s)</button>}
          {busy && <button onClick={cancel}>Cancel request</button>}
          <button disabled={!prompt.trim()} onClick={() => api.exportTask(body()).then(t => saveJson('agent_task.json', t)).catch(fail)}>Export task description</button>
          <button className="missing" onClick={whatIsMissing} title="Worked out by the workbench itself from the current configuration: free, no agent request.">What's missing to start?</button>
        </div>
        {kind === 'modify_fields' && showSelection && <div className="selection-info" ref={el => el?.scrollIntoView({ block: 'nearest' })}>{selection.length === 0
          ? <p className="hint">No row is selected. Tick rows in one of the editors above and press "Modify selected with agent...".</p>
          : <ul>{selection.map((s: Json, i: number) => { const row = (config[s.section] ?? []).find((r: Json) => r[ROW_KEY[s.section]] === s.key); return <li key={i}>
              <b>{s.key}</b> <span className="hint">({s.section})</span>{' '}
              {row ? (ROW_FACTS[s.section] ?? []).filter(f => row[f] !== null && row[f] !== undefined && row[f] !== '').map(f => `${f} ${brief(row[f])}`).join(', ') : <span className="error">no longer in the table</span>}
              <span className="hint"> - may change: {s.fields?.length ? s.fields.join(', ') : 'the whole row'}</span></li>; })}</ul>}</div>}
        <details><summary>Import a structured result (manual workflow)</summary>
          <textarea value={manual} onChange={e => setManual(e.target.value)} rows={3} placeholder="Paste the JSON object returned by any assistant" />
          <button disabled={!manual.trim() || !prompt.trim()} onClick={() => { try { api.importResult({ ...body(), result: JSON.parse(manual) }).then(p => { setProposal(p); say(p.origin, p.reasoning, p); }).catch(fail); } catch (e: any) { say('error', 'Not valid JSON: ' + e.message); } }}>Validate and show diff</button></details>
        </div>
        {/* Side window: what a reply lists besides its text. The inner box is absolutely placed so a long list scrolls instead of stretching the row. */}
        <aside className="notes"><div className="notes-scroll">
          <div className="notes-head">Warnings, unresolved, errors{shown >= 0 && <> - {who(log[shown].role)} {log[shown].at}</>}
            {focus !== null && <button className="notes-link" onClick={() => setFocus(null)}>back to the latest reply</button>}</div>
          {shown < 0 ? null
            : shownGroups.length === 0 ? <p className="hint">Nothing listed for this reply.</p>
            : shownGroups.map(g => <div key={g.key}><div className={`notes-title ${g.css}`}>{g.title} ({g.items.length})</div>
              <ul>{g.items.map((item, j) => <li key={j} className={g.css}>{g.text(item)}</li>)}</ul></div>)}
        </div></aside></div>
      </div>
    </div>
  );
  // The control on the tab, drawn into the slot the tab strip offers (App.tsx): pop out / bring back, like a browser tab's own button.
  const label = popup ? 'Bring the conversation back into this tab' : 'Detach: show the conversation in a window of its own, with more room. Nothing is lost or restarted.';
  const tabControl = tabSlot && createPortal(
    <button className="tab-detach" aria-label={label} title={label} onClick={popup ? attach : detach}>
      <svg viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M11 9.5V13H3V5h3.5" />{popup ? <path d="M13 3 8 8M8 4.5V8h3.5" /> : <path d="M9 3h4v4M13 3 7.5 8.5" />}</svg></button>, tabSlot);
  const root = popup?.document.getElementById('agent-root');
  if (!popup || !root) return <>{tabControl}{view}</>;
  return (<>
    {tabControl}
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
      <tr><td>Last checkpoint</td><td>{status.last_checkpoint_utc ?? '-'}
        {status.manual_save && <span className={status.manual_save.state === 'saved' ? 'ok' : 'warn'}> - Save now: {status.manual_save.state === 'saved'
          ? `saved at ${status.manual_save.evaluations} evaluations (${status.manual_save.checkpoint_id})`
          : 'requested, waiting for the simulation in flight to finish'}</span>}</td></tr>
      <tr><td>Run directory</td><td className="path" onClick={() => copy(status.run_dir)}>{status.run_dir}</td></tr>
      {status.error && <tr><td>Error</td><td className="error">{status.error}</td></tr>}
    </tbody></table>
    <div className="row">
      <button disabled={!status.worker_alive || ['pausing', 'stopping'].includes(status.state) || status.manual_save?.state === 'waiting'} onClick={() => onCommand('checkpoint')}
        title="Save the model now without pausing. The simulation in flight finishes first, the model is written as a new save point, and the run goes on by itself.">Save now</button>
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
