import { SizingThread } from './SizingThread';
import { Fragment, ReactNode, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { agentSettingsSaved, agentSettingsShared, api, ApiError, Json, saveJson, short } from '../api';
import { usePopupWindow } from './popupWindow';
import { DiffView } from './Editors';
import { COPY_SETUP_PENDING, COPY_SETUP_WRITTEN } from './TaskSave';

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
  targets: ['equation', 'constraint', 'lower', 'upper', 'target', 'unit', 'hard', 'active'], measurements: ['analysis', 'result_source', 'source_name', 'unit'] };
const CUSTOM = '__custom__';          // value of the "Custom..." entry of the agent-model list; never sent to the backend
// Where the model list came from: the Codex app's own file (the account's models), or the table kept by hand.
const listSource = (catalog: Json) => catalog.origin === 'codex_app'
  ? `List from the Codex app (your account's models, fetched ${catalog.fetched_at ? new Date(catalog.fetched_at).toLocaleString([], { hour12: false }) : 'at an unknown time'}).`
  : `List checked by hand on ${catalog.verified}${catalog.cache_note ? `; ${catalog.cache_note}` : ''}.`;
const noteGroups = (m: Json) => NOTE_GROUPS.map(g => ({ ...g, items: (Array.isArray(m?.extra?.[g.key]) ? m.extra[g.key] : []) as Json[] })).filter(g => g.items.length > 0);
const WHO: Record<string, string> = { user: 'You', system: 'Workbench', checklist: 'Workbench - run readiness', error: 'Error', manual_import: 'Imported result' };
const MARK: Record<string, [string, string]> = { done: ['\u2714', 'ok'], missing: ['\u2718', 'error'], warning: ['!', 'warn'], unknown: ['?', 'hint'],
  not_applicable: ['\u2013', 'hint'], at_start: ['\u25B6', 'hint'] };
const ASK_READINESS = 'What is still missing before this RL run can start? List it in order and fix what you can.';
const ASK_RUN = 'What happened in this run, and what should I change next? Say what the numbers show, then suggest changes, each tied to a number of the run.';
const ASK_SETTINGS = 'Review the settings of this run - run configuration, RL network, RL training, output - and suggest what to change, each with its source.';
// What a live request has shown so far (api.proposeLive; the backend's agents/live.py says what each event means).
type Live = { model: string | null; thinking: string; steps: string[]; reply: string; writing: string | null; last: string | null; answerAt: number | null };
const NO_LIVE: Live = { model: null, thinking: '', steps: [], reply: '', writing: null, last: null, answerAt: null };
const WRITING: Record<string, string> = { reasoning: 'the reply', patch: 'the proposed rows', checklist: 'the checklist',
  suggestions: 'the suggestions', encoder_ideas: 'the encoder ideas', warnings: 'the warnings', unresolved: 'the open questions' };
const heard = (live: Live, e: Json): Live => {
  const next = { ...live, last: e.type === 'model' ? live.last : e.type };
  if (e.type === 'model') next.model = e.model;
  else if (e.type === 'thinking') next.thinking += e.text ?? '';
  else if (e.type === 'step') next.steps = [...live.steps, e.text];
  else if (e.type === 'say') next.steps = e.new || !live.steps.length ? [...live.steps, e.text ?? ''] : [...live.steps.slice(0, -1), live.steps[live.steps.length - 1] + (e.text ?? '')];
  else if (e.type === 'writing') { next.writing = e.field; next.answerAt ??= Date.now(); }      // the thinking is over: the answer is being written
  else if (e.type === 'reply') next.reply += e.text ?? '';
  else if (e.type === 'restart') { next.reply = ''; next.writing = null; }
  return next;
};
const seconds = (ms: number) => { const s = Math.max(0, Math.round(ms / 1000)); return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`; };
const getIn =(config: Json, path: string) => path.split('.').reduce((node: Json, part) => node?.[part], config) ?? null;
const setIn = (config: Json, path: string, value: Json): Json => { const [head, ...rest] = path.split('.');
  return { ...config, [head]: rest.length ? setIn(config?.[head] ?? {}, rest.join('.'), value) : value }; };
// A suggested value may empty a setting that is one with it (the two checkpoint intervals: every N evaluations OR every
// S seconds). The backend names those in `clears` and tried the suggestion that way.
const applyRow = (config: Json, s: Json): Json => (s.clears ?? []).reduce((c: Json, path: string) => setIn(c, path, null), setIn(config, s.path, s.value));
// A source link the agent wrote becomes a link only when it is a web address. React 18 does not block `javascript:` in a
// production build, and an agent that reads web pages ("check publications online") could be steered into writing one:
// it would run with the page's full access to this API. Anything else shows no link (the source's name stays).
const webLink = (url: unknown): string | null => typeof url === 'string' && /^https?:\/\//i.test(url) ? url : null;

// Suggestions of a settings review. Nothing is applied by the agent or the backend: "Apply" is the user's own edit of that
// setting, the same as typing the value into its panel, and the page's static validation follows it as usual.
function Suggestions({ extra, config, setConfig }: { extra: Json; config: Json; setConfig: (c: Json) => void }) {
  const rows: Json[] = extra.suggestions ?? [];
  const open = rows.filter(s => s.applicable && getIn(config, s.path) !== s.value);
  return <div className="suggestions">
    {rows.length > 0 && <table className="grid small"><thead><tr><th>Setting</th><th>Now</th><th>Suggested</th><th>Why, and where it comes from</th><th></th></tr></thead><tbody>
      {rows.map((s, i) => { const live = getIn(config, s.path), applied = live === s.value, now = live ?? s.now;      // a setting the page never touched shows the backend's default
        return <tr key={i} className={applied ? 'applied' : ''}>
        <td><span className="hint">{s.panel}</span><br /><b>{s.path.split('.').pop()}</b></td><td>{short(now)}</td><td><b>{short(s.value)}</b></td>
        <td>{s.reason} <span className="hint">Source: {s.source || 'none given'}</span>{webLink(s.url) && <> <a href={webLink(s.url)!} target="_blank" rel="noreferrer">open</a></>}
          {s.quote && <div className="quote">"{s.quote}"</div>}{s.problem && !applied && <div className="error">{s.problem}</div>}{s.alone && !applied && <div className="warn">{s.alone}</div>}
          {s.clears?.length > 0 && !applied && <div className="hint">Applying it also empties {s.clears.map((path: string) => path.split('.').pop()).join(', ')}: only one of the two can be set.</div>}</td>
        <td>{applied ? <span className="ok">applied</span> : <button disabled={!s.applicable} onClick={() => setConfig(applyRow(config, s))}>Apply</button>}</td></tr>; })}</tbody></table>}
    {rows.length > 0 && <div className="row"><button disabled={!open.length || !extra.suggestions_together?.ok} onClick={() => setConfig(open.reduce((c, s) => applyRow(c, s), config))}
      title={extra.suggestions_together?.ok ? 'Sets every legal suggestion at once.' : `Together they would not be valid: ${extra.suggestions_together?.problem ?? ''}`}>Apply all ({open.length})</button>
      <span className="hint">Each row was tried on a copy of your configuration by the workbench. Applying is your own edit of that setting; nothing else changes.</span></div>}
    {extra.refused_suggestions?.length > 0 && <p className="hint">Left out - not something an agent may suggest: {extra.refused_suggestions.join('; ')}</p>}
    {extra.encoder_ideas?.length > 0 && <div className="ideas"><b>Encoders that do not exist here yet</b>
      <ul>{extra.encoder_ideas.map((e: Json, i: number) => <li key={i}><b>{e.name}</b> <span className="hint">{e.source}</span>{webLink(e.url) && <> <a href={webLink(e.url)!} target="_blank" rel="noreferrer">open</a></>}<br />{e.why} <span className="hint">What it takes: {e.what_it_takes}</span></li>)}</ul>
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

// What a live answer showed besides its text, kept in the chat folded into one line: the thinking summary, and for a
// request stopped with "Cancel request" the part of the reply that had arrived.
function Thought({ extra }: { extra: Json }) {
  if (!extra?.thinking && !extra?.partial_reply) return null;
  return <>{extra.thinking && <details className="thought"><summary>Thinking{extra.thinking_seconds ? ` - ${seconds(extra.thinking_seconds * 1000)}` : ''}</summary>
      <div className="thought-text"><RichText text={extra.thinking} /></div></details>}
    {extra.partial_reply && <details className="thought"><summary>Reply so far</summary><div className="thought-text"><RichText text={extra.partial_reply} /></div></details>}</>;
}

// Stays mounted while another bottom tab is shown (`hidden`): unmounting would drop the chat, a pending
// request's indicator and the proposal it returns, while the backend keeps working on that request.
export function AgentTab({ config, setConfig, request, clearRequest, hidden, tabSlot, onDetached, runDir, runActive = false }:
  { config: Json; setConfig: (c: Json) => void; request: { kind: string; selection: Json[]; prompt?: string } | null; clearRequest: () => void; hidden?: boolean;
    tabSlot?: HTMLElement | null; onDetached?: (detached: boolean) => void; runDir?: string | null; runActive?: boolean }) {
  const [settings, setSettings] = useState<Json>(null);
  const [diagnostics, setDiagnostics] = useState<Json>(null);
  const [prompt, setPrompt] = useState('');
  const [kind, setKind] = useState('draft_config');
  const [selection, setSelection] = useState<Json[]>([]);
  const [log, setLog] = useState<Json[]>([]);
  const [proposal, setProposal] = useState<Json>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [waited, setWaited] = useState(0);          // whole seconds the pending request has been out
  const [live, setLive] = useState<Live>(NO_LIVE);  // what the pending request has shown so far (thinking, steps, reply)
  const liveNow = useRef<Live>(NO_LIVE);            // the same, updated on every event; drawn at most every 150 ms
  const liveDraw = useRef<number | null>(null);
  const thinkingBox = useRef<HTMLDivElement>(null);
  const stick = useRef({ chat: true, thinking: true });       // follow new text only while the reader is at the bottom
  const chat = useRef<HTMLDivElement>(null);
  const [focus, setFocus] = useState<number | null>(null);    // chat line whose notes the side window shows; null = the latest reply
  const [customModel, setCustomModel] = useState(false);      // "Custom..." chosen: a model name outside the list is being typed
  const [online, setOnline] = useState(false);               // settings review: THIS request may read publication sites (never saved)
  const [busyOnline, setBusyOnline] = useState(false);
  const [showSelection, setShowSelection] = useState(false);  // modify_fields: the rows the request may change, listed on demand
  // While `popup` is set, the conversation is shown in its own browser window (popupWindow.ts, as the other windows are).
  const conversation = usePopupWindow('gator-agent-conversation', { title: 'GATOR - agent conversation', features: 'popup,width=1180,height=900', rootId: 'agent-root' });
  const popup = conversation.popup;
  const [sizingHint, setSizingHint] = useState('');           // the run's AI thread: a hint being typed survives detaching
  useEffect(() => setSizingHint(''), [runDir]);
  const latestConfig = useRef(config);                        // the configuration as it is NOW, for an approval that ends later
  latestConfig.current = config;
  const selectionBox = useRef<HTMLDivElement>(null);
  const [importing, setImporting] = useState(false);          // "Validate and show diff" is on its way
  // The list of selected rows comes into view when it is opened - not again at every redraw (each keystroke, each status
  // poll scrolled the proposal back to it).
  useEffect(() => { if (kind === 'modify_fields' && showSelection) selectionBox.current?.scrollIntoView({ block: 'nearest' }); }, [showSelection, kind]);
  const [manual, setManual] = useState('');
  const isReply = (m: Json) => m.role !== 'user' && m.role !== 'system' && m.role !== 'checklist';
  const say = (role: string, text: string, extra?: Json) => {
    setLog(l => [...l, { role, text, extra, at: new Date().toLocaleTimeString([], { hour12: false }) }]);
    if (isReply({ role })) setFocus(null);          // a new reply takes the side window back from an older line
  };

  // Detaching moves only the DOM: the component (chat, pending request, proposal, settings) stays where it is and is
  // drawn through a portal into a window of its own, so nothing has to be synchronised between two windows.
  const detach = () => { if (!conversation.open()) say('error', 'The browser blocked the new window. Allow pop-ups for this page, then detach again.'); };
  const attach = conversation.close;
  useEffect(() => { onDetached?.(!!popup); }, [popup]);

  // Read once for the page and shared with the AI sizing settings (api.ts), which follow what is saved here.
  useEffect(() => { agentSettingsShared().then(setSettings).catch(e => say('error', e.message)); }, []);
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
  // A live answer grows: follow it, unless the reader has scrolled up to read something (then it stays where they are).
  useEffect(() => {
    if (thinkingBox.current && stick.current.thinking) thinkingBox.current.scrollTop = thinkingBox.current.scrollHeight;
    if (chat.current && stick.current.chat) chat.current.scrollTop = chat.current.scrollHeight;
  }, [live]);
  const atBottom = (el: HTMLElement) => el.scrollHeight - el.scrollTop - el.clientHeight < 30;
  const onProgress = (e: Json) => {
    liveNow.current = heard(liveNow.current, e);
    if (liveDraw.current === null) liveDraw.current = window.setTimeout(() => { liveDraw.current = null; setLive(liveNow.current); }, 150);
  };
  // What a live request leaves in the chat besides its answer: the thinking summary, folded into one line.
  const thought = (l: Live, started: number) => l.thinking.trim() ? { thinking: l.thinking.trim(), thinking_seconds: Math.round(((l.answerAt ?? Date.now()) - started) / 1000) } : {};
  const runLabel = (runDir ?? '').split(/[\\/]/).filter(Boolean).pop() ?? '';       // the run folder's own name (RunTabs.tsx has a `runName` helper)
  const body = () => ({ kind, prompt, config, selection, web: kind === 'settings_review' && online, run_dir: kind === 'run_review' ? runDir ?? null : null });
  // Only an ApiError is an answer from the backend; anything else means no answer arrived at all.
  // A bare "Not Found" / "Method Not Allowed" comes from the web framework, not from an endpoint: the running server has
  // no such route. The page is served from disk and is always current, the server only after a restart - say that.
  const olderServer = (e: any) => e instanceof ApiError && (e.status === 404 || e.status === 405) && typeof e.detail === 'string';
  const fail = (e: any, keep?: Json) => say('error', olderServer(e)
    ? 'The workbench server that is running is older than this page and does not have this function yet. Restart it (Ctrl+C in its terminal, then start `serve` again) and press the button again. Nothing was sent to an agent.'
    : e instanceof ApiError
      ? `${e.detail?.code ?? 'error'}: ${e.message}${e.detail?.configuration_unchanged ? ' (your configuration is unchanged)' : ''}`
      : `No answer from the backend (${e?.message ?? e}). Check that the workbench server is still running.`,
    keep?.thinking ? { ...(e?.detail && typeof e.detail === 'object' ? e.detail : {}), ...keep } : e?.detail);

  const propose = async (ask?: { text: string; kind: string }) => {
    const text = (ask?.text ?? prompt).trim();
    if (!text || busy) return;
    if (settings?.provider === 'disabled') { say('system', 'Not sent: the provider is "disabled". Choose claude_code or codex on the left, or use "Export task description".'); return; }
    const request_id = crypto.randomUUID().replace(/-/g, '');
    const started = Date.now(), sent_with = using;          // what THIS request runs on, whatever is chosen later
    const web = (ask?.kind ?? kind) === 'settings_review' && online && settings?.provider === 'claude_code';
    liveNow.current = NO_LIVE; setLive(NO_LIVE); stick.current = { chat: true, thinking: true };
    setBusy(request_id); setBusyOnline(web); say('user', text); if (!ask) setPrompt('');
    try { const p = await api.proposeLive({ ...body(), kind: ask?.kind ?? kind, web, run_dir: (ask?.kind ?? kind) === 'run_review' ? runDir ?? null : null, prompt: text, request_id }, onProgress);
      if (p.kind !== 'settings_review' && !(p.kind === 'run_review' && !p.diff?.length)) setProposal(p);   // nothing to approve: no box, and an open proposal stays
      say(p.origin, p.reasoning || '(no reasoning given)', { ...p, sent_with, ran_on: liveNow.current.model, ...thought(liveNow.current, started) }); }   // ran_on: the model the CLI named
    catch (e: any) {
      const shown = liveNow.current;                            // what had arrived: kept in the chat, folded
      if (e.detail?.code === 'cancelled') say('system', `Cancelled by you after ${Math.round((Date.now() - started) / 1000)} s. The request had been sent and the agent was still working on it; nothing was changed.`,
        { ...thought(shown, started), ...(shown.reply.trim() ? { partial_reply: shown.reply.trim() } : {}) });
      else fail(e, thought(shown, started));
      if (!ask) setPrompt(current => current || text);          // hand the text back for a retry unless something new was typed
    } finally {
      if (liveDraw.current !== null) { clearTimeout(liveDraw.current); liveDraw.current = null; }
      liveNow.current = NO_LIVE; setLive(NO_LIVE); setBusy(null);
    }
  };
  // Free: the backend works it out from the live configuration. No model is called and nothing is probed.
  const whatIsMissing = () => api.agentReadiness(config).then(r => say('checklist', r.ready ? 'Nothing blocks a start.'
    : `Not ready yet. Next: ${r.next.title} - ${r.next.detail}`, r)).catch(fail);
  const cancel = () => busy && api.cancelAgent(busy).then(r => {
    if (!r.cancelled) say('system', 'Nothing to cancel: the backend has no running agent process for this request (it may have just finished).');
  }).catch(fail);
  // `approving`: the approval and its write are on their way - a second press used to get 409 "Proposal is applied" while
  // the first write carried on. Reject waits too.
  const [approving, setApproving] = useState(false);
  // The write of a Virtuoso setup takes seconds: an edit made meanwhile is replaced by the approved configuration - said,
  // with the way back - and only THIS proposal's box closes (a newer one that arrived meanwhile stays for its review).
  const approveAndApply = async () => {
    const id = proposal.proposal_id, sent = config;
    const done = () => setProposal((p: Json) => (p?.proposal_id === id ? null : p));
    setApproving(true);
    try {
      await api.approve({ proposal_id: id, proposal_hash: proposal.proposal_hash, config: sent });
      const applied = await api.apply({ proposal_id: id, config: sent });
      const edited = JSON.stringify(latestConfig.current) !== JSON.stringify(sent);
      setConfig(applied.config); done(); say('system', applied.note);
      if (edited) say('system', 'The configuration was edited while the proposal was being applied: the approved configuration replaced those edits. Undo brings them back (and takes the proposal out again).');
      if (applied.virtuoso?.differences?.length) say('system', `What the working copy reads back differently: ${applied.virtuoso.differences.join('; ')}`);
      if (applied.virtuoso?.written) window.dispatchEvent(new CustomEvent(COPY_SETUP_WRITTEN,
        { detail: Object.keys(proposal.setup ?? {}).filter(part => proposal.setup[part] != null) }));
      // Not written (Virtuoso out of reach): the approved setup waits for the next Save task, which writes the copy.
      else if (applied.virtuoso && proposal.setup) window.dispatchEvent(new CustomEvent(COPY_SETUP_PENDING,
        { detail: Object.fromEntries(Object.entries(proposal.setup).filter(([, value]) => value != null)) }));
    } catch (e) { fail(e); done(); } finally { setApproving(false); }
  };
  // A backend restarted since the proposal came knows it no more (404): said in the chat, and the box closes all the same.
  const reject = () => { const id = proposal.proposal_id;
    api.reject(id).catch(e => fail(e)).finally(() => setProposal((p: Json) => (p?.proposal_id === id ? null : p))); };
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
    return api.saveAgentSettings({ provider: next.provider, model: next.model ?? null, effort: next.effort ?? null,        // no time limit: "Cancel request" stops a request
      permission_mode: next.permission_mode, allowed_tools: next.allowed_tools, max_turns: next.max_turns, stream: next.stream })
      .catch(fail).then(() => api.agentSettings().then(s => { setSettings(s); agentSettingsSaved(s); }).catch(fail));   // always show what is actually saved - here and in the AI sizing settings
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
            ? <>{listed?.note ?? (isCustom ? 'A name outside the list is passed to the CLI as typed.' : catalog.default_note)} {catalog.caveat} {listSource(catalog)} Showing it calls no model.
              {/* The Codex app refreshes its file by itself; this reads it again without reloading the page. */}
              {settings.provider === 'codex' && <> <button className="text-link" title="Read the Codex app's model list again (a local file; no model is called)"
                onClick={() => api.agentSettings().then(s => { setSettings(s); agentSettingsSaved(s); }).catch(fail)}>Re-read list</button></>}</>
            : 'Restart the workbench server to get the model and effort lists.'}</p></>}
        <button onClick={() => api.agentDiagnostics().then(setDiagnostics).catch(fail)}>Diagnostics</button>
        {diagnostics && <details open><summary>Backend environment</summary><pre className="small">{JSON.stringify({ providers: diagnostics.providers, skills: diagnostics.skills.summary, nested: diagnostics.environment.nested_session_note, cwd: diagnostics.environment.cwd }, null, 1)}</pre></details>}
        <p className="hint">Agents prepare proposals only. Applying a configuration, writing a circuit and running a real simulation each need their own authorization. Every manual workflow works without an agent.</p>
      </div>
      <div className="agent-main">
        <SizingThread runDir={runDir} active={runActive} visible={!hidden || !!popup} hint={sizingHint} setHint={setSizingHint} />
        <div className="agent-using"><span>{using ? <>Next request: <b>{settings.provider}</b>, model <b>{modelShown}</b>, effort <b>{effortShown}</b></>
          : 'No agent is selected (provider: disabled). Choose one on the left, or use "Export task description".'}</span>
          {/* The review button closes the line at its right end; its option stands in front of it. */}
          <span className="agent-actions">
            <label className="check" title="For the next settings review only. The agent may search the web and open publication sites (arXiv, IEEE Xplore, ACM, OpenReview, GitHub...) and nothing else. It is told the kind of circuit and your settings, nothing of the design itself. Slower (minutes) and heavier on usage. Claude Code provider only.">
              <input type="checkbox" checked={online && settings?.provider === 'claude_code'} disabled={settings?.provider !== 'claude_code'} onChange={e => setOnline(e.target.checked)} />check publications online</label>
            <button disabled={!!busy || !using} onClick={() => propose({ text: ASK_SETTINGS, kind: 'settings_review' })}
              title={using ? `One agent request (${using}). It looks at the run configuration, the RL network, the RL training settings and the output settings - not at your circuit - and suggests values, each with its source. You apply them one by one.` : 'Select a provider first.'}>Review settings</button></span></div>
        <div className="chat" ref={chat} onScroll={e => { stick.current.chat = atBottom(e.currentTarget); }}>
          {log.length === 0 && !busy && <p className="hint chat-empty">"What's missing?" lists what this run still needs - free, no agent. Or ask below for a draft of the Parameters, Probes or Specs tab. The agent only proposes: you review a diff before anything changes.</p>}
          {log.map((m, i) => { const groups = noteGroups(m); return <div key={i} className={`msg ${isReply(m) && m.role !== 'error' ? 'reply' : m.role}${focus === i ? ' focused' : ''}`}>
            <div className="who">{who(m.role)}{m.extra?.sent_with && <span className="when">{m.extra.sent_with}{m.extra.ran_on && ` - ran on ${m.extra.ran_on}`}</span>} <span className="when">{m.at}</span></div>
            {m.role !== 'system' && <Thought extra={m.extra} />}
            <div className="text">{m.role === 'user' ? m.text : <RichText text={m.text} />}</div>
            {m.role === 'system' && <Thought extra={m.extra} />}
            {m.role === 'checklist' && <><Checklist items={m.extra.items} />
              <div className="row">{m.extra.items.some((c: Json) => c.status === 'missing' && c.who === 'agent') && <>
                <button className="primary" disabled={!!busy || !using} onClick={() => propose({ text: ASK_MINIMAL, kind: 'minimal_start' })}
                  title={using ? `One agent request (${using}). The smallest change of the three tables after which the run can start: valid rows stay untouched (the backend enforces it), and a value you did not give is taken only from the circuit or the recorded baseline and marked PROVISIONAL. You review the diff.` : 'Select a provider first.'}>Make it startable with the fewest changes</button>
                <button disabled={!!busy || !using} onClick={() => propose({ text: ASK_READINESS, kind: 'readiness' })}
                  title={using ? `One agent request (${using}). It assumes nothing: it writes only the rows you gave every number for, and asks for the rest.` : 'Select a provider first.'}>Fix only what needs no assumption</button></>}
                <span className="hint">{m.extra.note}</span></div></>}
            {isReply(m) && m.extra?.checklist?.length > 0 && <Checklist items={m.extra.checklist} />}
            {/* What the agent did in Virtuoso itself (kind virtuoso_work): one folded line, the refused calls named. */}
            {isReply(m) && m.extra?.tool_calls?.length > 0 && <details className="thought"><summary>
              {m.extra.tool_calls.length} step(s) in Virtuoso{m.extra.virtuoso_copy_written ? ' - the working copy was written' : ''}</summary>
              <div className="thought-text"><ul>{m.extra.tool_calls.map((c: Json, j: number) => <li key={j}>
                {c.tool}{c.ok ? '' : ` - refused: ${c.error}`}</li>)}</ul></div></details>}
            {isReply(m) && (m.extra?.kind === 'settings_review' || m.extra?.kind === 'run_review') && <Suggestions extra={m.extra} config={config} setConfig={setConfig} />}
            {groups.length > 0 && <button className="notes-link" title="Show these in the side window" onClick={() => setFocus(i === latest ? null : i)}>{groups.map(g => `${g.items.length} ${g.title.toLowerCase()}`).join(', ')}</button>}</div>; })}
          {/* The pending answer, drawn while it is written: the thinking summary (scrolls by itself), steps such as a web
              search, then the reply text. On completion it is replaced by the reply, the thinking folded into one line. */}
          {busy && <div className="msg pending"><div className="who">{who(settings?.provider ?? 'agent')}{live.model && <span className="when">{live.model}</span>}</div>
            {live.thinking.trim() && <div className="thinking-live" ref={thinkingBox} onScroll={e => { stick.current.thinking = atBottom(e.currentTarget); }}>
              <div className="thinking-head">Thinking</div><RichText text={live.thinking} /></div>}
            {live.steps.filter(s => s.trim()).length > 0 && <ul className="live-steps">{live.steps.filter(s => s.trim()).map((s, i) => <li key={i}>{s}</li>)}</ul>}
            {live.reply && <div className="text live-reply"><RichText text={live.reply} /></div>}
            <div className="text live-status">{!live.last ? (busyOnline ? 'Sent. The agent is searching and reading publications online - this takes minutes...' : "Sent. Waiting for the agent's reply...")
              : live.last === 'thinking' ? 'Thinking...' : live.last === 'step' ? 'Looking things up...' : live.last === 'say' ? 'Working...'
              : live.last === 'restart' ? 'Writing the answer again...' : `Writing ${WRITING[live.writing ?? ''] ?? 'the answer'}...`} <b>{waited} s</b></div>
            <div className="hint">No time limit. "Cancel request" below stops it; what has arrived stays in the chat.</div></div>}</div>
        {/* Left: the proposal under review and the message box. Right: the side window, as tall as both. */}
        <div className="compose"><div className="compose-main">
        {proposal && <div className="confirm"><h4>Proposal from {proposal.origin} - review the diff</h4><DiffView diff={proposal.diff} />
          {proposal.patch?.some(provisional) && <div className="provisional"><b>Provisional values - placeholders, not your requirements:</b>
            <ul>{proposal.patch.filter(provisional).map((p: Json, i: number) => <li key={i}><code>{p.section}/{p.key}</code> {String(p.value?.basis ?? p.basis)}</li>)}</ul></div>}
          {proposal.readiness_after && <p className={`verdict ${proposal.readiness_after.ready ? 'ok' : 'warn'}`} title={proposal.readiness_after.note}>
            {proposal.readiness_after.ready ? 'After you approve: nothing blocks a start.'
              : <>After you approve, still missing: {proposal.readiness_after.remaining.map((r: Json) => `${r.title} (${r.who === 'agent' ? 'agent can draft it' : 'yours'})`).join(', ') || 'see the blocking issues'}.</>}
            <span className="hint"> {proposal.readiness_after.changed_rows} row(s) changed{proposal.readiness_after.resolved.length > 0 && `; resolves ${proposal.readiness_after.resolved.join(', ')}`}. Checked by the workbench, not by the agent.</span></p>}
          {proposal.setup && <div className="setup-proposal"><h4>Maestro setup of the working copy{proposal.virtuoso_copy ? ` ${proposal.virtuoso_copy.library}/${proposal.virtuoso_copy.testbench}` : ''}</h4>
            <table className="grid small"><tbody>
              {Object.entries(proposal.setup.analyses ?? {}).map(([name, options]: [string, any]) => <tr key={`a-${name}`}><td>analysis {name}</td>
                <td>{Object.entries(options).map(([k, v]) => `${k}=${v}`).join('  ')}</td></tr>)}
              {Object.entries(proposal.setup.initial_conditions ?? {}).map(([net, value]: [string, any]) => <tr key={`i-${net}`}>
                <td>start voltage on {net}</td><td>{String(value)}</td></tr>)}
              {Object.entries(proposal.setup.variables ?? {}).map(([name, value]: [string, any]) => <tr key={`v-${name}`}><td>variable {name}</td><td>{String(value)}</td></tr>)}
              {(proposal.setup.bindings ?? []).map((b: Json) => <tr key={`b-${b.cell}-${b.instance}-${b.parameter}`}><td>{b.instance}.{b.parameter} in {b.cell}</td><td>= {b.variable}</td></tr>)}
            </tbody></table>
            <p className="hint">Approving fills the editors and writes this, with the outputs and specs of the rows, into the working copy - the cell
              you read as your copy - then reads it back. {Object.keys(proposal.setup.analyses ?? {}).length ? '' : 'The analyses the copy has stay as they are.'}</p></div>}
          <button disabled={!proposal.diff.length || approving} onClick={approveAndApply}>{approving ? 'Applying...'
            : proposal.kind === 'virtuoso_setup' ? 'Approve, apply and write the copy' : 'Approve and apply to the configuration'}</button>
          <button disabled={approving} onClick={reject}>Reject</button>
          <span className="hint"> The approval is bound to this exact proposal, configuration and circuit; any later change invalidates it.</span></div>}
        {/* Enter sends, Shift+Enter breaks the line. An Enter that confirms an IME candidate (isComposing / 229) must not send. */}
        <textarea value={prompt} onChange={e => setPrompt(e.target.value)} rows={3}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey && !e.nativeEvent.isComposing && e.keyCode !== 229) { e.preventDefault(); propose(); } }}
          placeholder="Describe what you need. State where each requirement comes from; the agent may not invent requirements." />
        <div className="row">
          <select title="What the agent may change. virtuoso_work also lets it READ from Virtuoso and write the Maestro setup of this task's working copy itself - never your own cells, never device sizes, never a simulation."
            value={kind} onChange={e => setKind(e.target.value)}>{['draft_config', 'parameters', 'targets', 'measurements', 'modify_fields', 'readiness', 'minimal_start', 'settings_review', 'run_review', 'virtuoso_setup', 'virtuoso_work'].map(k => <option key={k}>{k}</option>)}</select>
          {kind === 'modify_fields' && <button className="notes-link" aria-expanded={showSelection} onClick={() => setShowSelection(open => !open)}
            title="The rows this request may change. They are chosen in the editors with 'Modify selected with agent...'.">{selection.length} selected row(s)</button>}
          {busy && <button onClick={cancel}>Cancel request</button>}
          <button disabled={!prompt.trim()} onClick={() => api.exportTask(body()).then(t => saveJson('agent_task.json', t)).catch(fail)}>Export task description</button>
          <button className="missing" onClick={whatIsMissing} title="Worked out by the workbench itself from the current configuration: free, no agent request.">What's missing?</button>
          <button disabled={!!busy || !using || !runDir} onClick={() => propose({ text: `${ASK_RUN} (run ${runLabel})`, kind: 'run_review' })}
            title={!runDir ? 'Choose a run with "Runs..." first.' : using ? `One agent request (${using}). The workbench condenses what run ${runLabel} produced - outcome, budget, each target against the best design, where the search went, failures - and the agent explains it and suggests what to change. It reads no file.` : 'Select a provider first.'}>Review results</button>
        </div>
        {kind === 'modify_fields' && showSelection && <div className="selection-info" ref={selectionBox}>{selection.length === 0
          ? <p className="hint">No row is selected. Tick rows in one of the editors above and press "Modify selected with agent...".</p>
          : <ul>{selection.map((s: Json, i: number) => { const row = (config[s.section] ?? []).find((r: Json) => r[ROW_KEY[s.section]] === s.key); return <li key={i}>
              <b>{s.key}</b> <span className="hint">({s.section})</span>{' '}
              {row ? (ROW_FACTS[s.section] ?? []).filter(f => row[f] !== null && row[f] !== undefined && row[f] !== '').map(f => `${f} ${short(row[f])}`).join(', ') : <span className="error">no longer in the table</span>}
              <span className="hint"> - may change: {s.fields?.length ? s.fields.join(', ') : 'the whole row'}</span></li>; })}</ul>}</div>}
        <details><summary>Import a structured result (manual workflow)</summary>
          <textarea value={manual} onChange={e => setManual(e.target.value)} rows={3} placeholder="Paste the JSON object returned by any assistant" />
          {/* As a live reply: a review with nothing to approve opens no box (it used to open an empty one that only Reject closed). */}
          <button disabled={!manual.trim() || !prompt.trim() || importing} onClick={() => {
            let result: Json;
            try { result = JSON.parse(manual); } catch (e: any) { say('error', 'Not valid JSON: ' + e.message); return; }
            setImporting(true);
            api.importResult({ ...body(), result }).then(p => { if (p.kind !== 'settings_review' && !(p.kind === 'run_review' && !p.diff?.length)) setProposal(p); say(p.origin, p.reasoning, p); })
              .catch(fail).finally(() => setImporting(false)); }}>{importing ? 'Validating...' : 'Validate and show diff'}</button></details>
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
  const root = conversation.root;
  if (!popup || !root) return <>{tabControl}{view}</>;
  return (<>
    {tabControl}
    {createPortal(view, root)}
    <div className="agent-away" style={hidden ? { display: 'none' } : undefined}>
      <p>The agent conversation is open in a window of its own. It keeps working while you use the other tabs here. The arrow on
        the Agent tab, or closing that window, brings it back.</p>
      {/* "Bring it back here" went on 2026-09-29: the arrow button on the Agent tab does the same, and so does closing the window. */}
      <div className="row"><button onClick={() => popup.focus()}>Show that window</button></div>
    </div></>);
}
