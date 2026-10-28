// The header's Connection button and the connection window it opens (record 7.32; in the header since record 7.182):
// choose or add a connection, connect it, load the bridge in the CIW, test it, and set GATOR's folders.
import { useAsyncAction } from '../store';
import { Fragment, useEffect, useRef, useState } from 'react';
import { usePopupWindow } from './popupWindow';
import { Blocked, PopupPortal } from './popupParts';
import { CONNECTION_WINDOW } from '../contract';
import { ConnectionAt, OPEN_CONNECTION } from '../openAt';
import { api, Json, plainError } from '../api';
import { connectionProfilesChanged, connectionProfilesShared } from '../shared';
import { ConnectionFolders } from './ConnectionFolders';
import { Icon } from './Icons';
import { CONNECTION_STATE as STATE_LABEL, layerWords, stamp, timeOrDateTime as testedAt } from '../format';

const NAME = /^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$/;
const SUGGESTED_NAME: Record<string, string> = { virtuoso_ssh: 'lab', virtuoso_local: 'virtuoso-local', ngspice_local: 'ngspice-local', ngspice_ssh: 'ngspice-ssh' };
/** A CIW line breaks only after a "/": the box broke a long setup path mid-word ("virtuoso_bri" over "dge_s2/..."), which
 *  read like one of its real line breaks (branch record SIF-79). The <wbr>s carry no text, so Copy and a selection keep the line. */
const breakAfterSlash = (text: string) => text.split(/(?<=\/)/).map((part, i) => <Fragment key={i}>{i > 0 && <wbr />}{part}</Fragment>);


/** The connection block of the left column: ONE button (user request 2026-09-21). Pressing it opens the connection
 *  window - a browser window of its own, drawn through a portal, so the state below lives here and nothing has to be
 *  synchronised between two windows (popupWindow.ts).
 *
 *  What it connects to is the profile's KIND: Virtuoso over SSH, Virtuoso on this machine, ngspice on this machine,
 *  ngspice over SSH. The steps and their wording follow the kind; the backend names the kinds, this file only words them.
 *
 *  Unchanged rules (section 2.1, user request 2026-09-20): a TEST only observes; a tunnel or a local bridge is set up by
 *  its explicit button alone; nothing is ever stopped or restarted; nothing is checked on a timer, when the window opens
 *  or when a connection is chosen (that reads the backend's LAST result once). ONE exception since 2026-09-24 (user
 *  request, status record 7.80): when the page opens it tests the connection in use once - the same test as the button. */
export function ConnectionButton({ profileId, setProfileId }: { profileId: string | null; setProfileId: (id: string | null, record?: boolean) => void }) {
  const [profiles, setProfiles] = useState<Json>(null);
  const [setup, setSetup] = useState<Json>(null);
  const [statuses, setStatuses] = useState<Record<string, Json>>({});
  const [connections, setConnections] = useState<Record<string, Json>>({});
  const [detailsOpen, setDetailsOpen] = useState<Record<string, boolean>>({});
  const [sessionErrors, setSessionErrors] = useState<Record<string, string | null>>({});
  const [error, setError] = useState<string | null>(null);
  const [copiedKey, setCopied] = useState<string | null>(null);
  const groups: Json[] = profiles?.groups ?? profiles?.profiles.map((p: Json) => ({ ...p, session_profile_ids: [p.profile_id] })) ?? [];
  const group: Json = groups.find((g: Json) => g.session_profile_ids.includes(profileId)) ?? null;
  const sessions: Json[] = (group?.session_profile_ids ?? []).map((id: string) => profiles.profiles.find((p: Json) => p.profile_id === id)).filter(Boolean);
  const multipleSessions = sessions.length > 1;
  // The configuration names one session of the connection by its own name (`lab2`, as queues do): everything goes there.
  // Naming the connection (`lab`) lets the backend send the work to whichever session is free (record 7.351).
  const pinned = multipleSessions && profileId !== group?.profile_id;
  const pinnedLabel = pinned ? `Virtuoso ${sessions.findIndex(s => s.profile_id === profileId) + 1}` : '';

  // While `popup` is set, the connection window is open (one pop-up window for the whole page: `popupWindow.ts`).
  const { popup, root, blocked, open: openWindow } = usePopupWindow('gator-connection',
    { title: CONNECTION_WINDOW, features: `popup,width=${multipleSessions ? 1100 : 660},height=920`, rootId: 'connection-root' });
  // A message in another window that sends the user here carries a button to this window (branch record SIF-108, openAt.ts):
  // the window opens from the window that holds that click, as this button opens it from the page. Opening it checks nothing.
  const opener = useRef(openWindow);
  opener.current = openWindow;
  useEffect(() => {
    const show = (event: Event) => { opener.current((event as CustomEvent<ConnectionAt>).detail?.from); };
    window.addEventListener(OPEN_CONNECTION, show);
    return () => window.removeEventListener(OPEN_CONNECTION, show);
  }, []);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState<Json>({ kind: 'virtuoso_ssh', name: '', ssh_host: '', bridge_profile: '' });
  const [created, setCreated] = useState<Json>(null);
  const [folders, setFolders] = useState(false);                // the Folders section (record 7.168)
  // The folders typed there and not saved, by folder: here, outside the window, so that its close keeps them (branch record SIF-87).
  const [typedFolders, setTypedFolders] = useState<Record<string, string>>({});

  // Every error here is said as the rest of the page says it (plainError): a backend that did not answer showed the
  // browser's "Failed to fetch" under the button (branch record SIF-55).
  const loadSetup = () => api.connectionSetup().then(setSetup).catch(e => setError(plainError(e)));          // locates and names; contacts nothing
  // The connection file's active profile fills an empty choice by itself: not an Undo step (nobody chose it).
  const loadProfiles = () => connectionProfilesShared().then(p => {
    setProfiles(p); if (!profileId && p.active) setProfileId(p.active, false);
    if (p.profiles.length === 0) { setAdding(true); loadSetup(); }
  }).catch(e => setError(plainError(e)));
  useEffect(() => { loadProfiles(); }, []);

  // Each session keeps its own result and action state, including while its sibling is connecting.
  const { busy, run } = useAsyncAction(e => setError(plainError(e)), () => setError(null));
  const [busyFor, setBusyFor] = useState<Record<string, string>>({});
  const revisions = useRef<Record<string, number>>({});
  const nextRevision = (id: string) => (revisions.current[id] = (revisions.current[id] ?? 0) + 1);
  const runFor = async (id: string, name: string, action: (revision: number) => Promise<void>) => {
    const revision = nextRevision(id);
    setBusyFor(b => ({ ...b, [id]: name }));
    setSessionErrors(e => ({ ...e, [id]: null }));
    try { await action(revision); }
    catch (e) { if (revisions.current[id] === revision) setSessionErrors(errors => ({ ...errors, [id]: plainError(e) })); }
    finally { setBusyFor(b => { const rest = { ...b }; delete rest[id]; return rest; }); }
  };
  // A status is shown only when it is not older than the one shown: a cached read that comes back after a test must not put
  // the result from before that test back (record 7.351). `checked_utc` is the backend's own time of the test; an answer
  // without one (never tested) is older than any test.
  const showStatus = (id: string, answer: Json) => setStatuses(s => {
    const shown = s[id];
    const older = !!shown?.checked_utc && (!answer?.checked_utc || answer.checked_utc < shown.checked_utc);
    return older ? s : { ...s, [id]: answer };
  });
  const connectSession = (id: string) => runFor(id, 'connect', async revision => {
    const answer = await api.connectionConnect(id);
    if (revisions.current[id] !== revision) return;
    setConnections(c => ({ ...c, [id]: answer.connect }));
    showStatus(id, answer.status);
  });
  const checkSession = (id: string, scope: string) => runFor(id, scope, async revision => {
    const answer = await api.connectionCheck(id, scope);
    if (revisions.current[id] !== revision) return;
    showStatus(id, answer);
    // A failed Connect line goes once a later test passes; a successful one keeps its CIW lines.
    if (answer?.overall === 'ok') setConnections(c => (c[id] && !c[id].ok ? Object.fromEntries(Object.entries(c).filter(([k]) => k !== id)) : c));
  });
  // The existing page-open test belongs only to the configured session. Siblings get cached results; reading the
  // group or opening this window never starts a tunnel or probes the other Virtuoso.
  const testedOnOpen = useRef(false);
  useEffect(() => {
    if (!profileId || !profiles) return;
    let live = true;
    for (const session of sessions) {
      const id = session.profile_id;
      if (!testedOnOpen.current && id === profileId) {
        testedOnOpen.current = true;
        checkSession(id, 'interactive');
      } else {
        // A cached read never makes a test or Connect still on its way stale (it used to, record 7.351): it takes no
        // revision of its own, and `showStatus` keeps whichever result is newer.
        const revision = revisions.current[id] ?? 0;
        api.connectionStatus(id).then(answer => {
          if (live) showStatus(id, answer);
        }).catch(e => { if (live && (revisions.current[id] ?? 0) === revision) setSessionErrors(errors => ({ ...errors, [id]: plainError(e) })); });
      }
    }
    return () => { live = false; };
  }, [profileId, profiles]);
  // The click happens in the connection window, so ITS clipboard is the one a browser lets this gesture write to.
  // "Copied" only when it was: a refused or missing clipboard used to say "Copied" all the same.
  const copyText = (key: string, text: string) => (popup ?? window).navigator.clipboard?.writeText(text)
    .then(() => { setCopied(key); setTimeout(() => setCopied(c => (c === key ? null : c)), 1500); }, () => undefined);

  const entry: Json = profiles?.profiles.find((p: Json) => p.profile_id === profileId) ?? null;
  const status = profileId ? statuses[profileId] : null;
  const mine = sessions.some(s => ['interactive', 'full'].includes(busyFor[s.profile_id])) ? 'interactive' : null;
  // What the work started here can use: the named session's own state; for a connection whose work goes to whichever
  // session is free, how many sessions passed their last test - or, when none did, its own session's state (record 7.351).
  const okSessions = sessions.filter(s => statuses[s.profile_id]?.overall === 'ok').length;
  const overall = multipleSessions && !pinned
    ? (okSessions > 0 ? 'ok' : statuses[group.profile_id]?.overall ?? 'unknown')
    : status?.overall ?? 'unknown';
  const overallText = multipleSessions && !pinned && okSessions > 0 && okSessions < sessions.length
    ? `${okSessions} of ${sessions.length} OK` : STATE_LABEL[overall] ?? overall;

  // ---- add a connection --------------------------------------------------------------------------------------------
  const taken = (name: string) => !!profiles?.profiles.some((p: Json) => p.profile_id === name);
  const freeName = (kind: string) => { const base = SUGGESTED_NAME[kind] ?? 'connection'; let name = base; for (let i = 2; taken(name); i++) name = `${base}-${i}`; return name; };
  const kindSetup: Json = setup?.kinds?.find((k: Json) => k.kind === draft.kind) ?? null;
  const name = draft.name || freeName(draft.kind);
  const nameProblem = !NAME.test(name) ? 'Letters, digits, "_", "." and "-" only; it starts with a letter or digit.' : taken(name) ? 'A connection with this name already exists.' : null;
  const host = draft.ssh_host || kindSetup?.ssh_hosts?.[0] || '';
  const canCreate = !!kindSetup?.can_create && !nameProblem && !busy && (draft.kind !== 'ngspice_ssh' || !!host);
  const startAdding = () => { setAdding(a => !a); setCreated(null); if (!setup) loadSetup(); };
  const create = () => run('profile', async () => {
    const body: Json = { profile_id: name, kind: draft.kind };
    if (draft.kind === 'ngspice_ssh') body.ssh_host = host;
    if (kindSetup?.family === 'virtuoso' && draft.bridge_profile.trim()) body.bridge_profile = draft.bridge_profile.trim();
    const made = await api.connectionCreateProfile(body);
    connectionProfilesChanged(made.profiles); setProfiles(made.profiles); setProfileId(made.profile_id); setCreated(made); setAdding(false);
    setDraft((d: Json) => ({ ...d, name: '', bridge_profile: '' }));
  });

  // No connection (branch record SIF-136): the pill reads "Connection" and, where a connection's state stands, why there is
  // none - "not set up" (the connection file has none) or "none chosen" (this configuration names none). It read "none set up
  // yet" or "none selected" with the word "Connection" for screen readers only, and the header cut that to "none s...". The
  // word stands in for the hidden name (a screen reader would hear it twice); the state word never gives way (roadster.css).
  const none = profileId ? null : profiles && profiles.profiles.length === 0 ? 'not set up' : 'none chosen';
  const launcher = (
    <section className="panel connection-launcher">
      <button className="connection-button" onClick={openWindow}
        title={popup ? 'The connection window is open: press to bring it to the front.' : 'Opens the connection window: choose or add a connection (Virtuoso or ngspice, on this machine or over SSH), connect and test it. Opening it checks nothing.'}>
        {!none && <span className="connection-button-name">Connection</span>}
        <span className={`connection-button-what${none ? ' bare' : ''}`}>{none ? 'Connection' : `${pinned ? `${profileId} (${pinnedLabel} only)` : group?.profile_id ?? profileId}${entry?.kind_label ? ` - ${entry.kind_label}` : ''}${multipleSessions && !pinned ? ` (${sessions.length} sessions)` : ''}`}{popup ? ' (window open)' : ''}</span>
        {none ? <span className="badge state-unknown" title={none === 'not set up'
            ? 'No connection is set up yet: press to add one. Manual editing, JSON import/export, data export and mock runs work without one.'
            : 'This configuration names no connection: press to choose or add one. Manual editing, JSON import/export, data export and mock runs work without one.'}>{none}</span>
          : mine !== null
          ? <span className="badge state-not_checked" title="The connection is being tested">testing...</span>
          : <span className={`badge state-${overall}`} title={multipleSessions && !pinned ? 'Sessions that passed their last test: runs go to whichever session is free. Each session is in Connection.' : status?.checked_utc ? `Last test: ${testedAt(status.checked_utc)}` : 'Never tested'}>{overallText}</span>}
      </button>
      {blocked && <Blocked />}
      {/* The note floats over the row under the header (record 7.182), so a click closes it: it stayed until a later action
          in the window went well (branch record SIF-55). The next failure shows it again. Its own class carries the hand
          cursor: the pop-up-blocked note above is a paragraph here too, and a click does nothing to it. */}
      {!popup && (error || (profileId && sessionErrors[profileId])) && <p className="error connection-note" title="Click to close"
        onClick={() => { setError(null); if (profileId) setSessionErrors(errors => ({ ...errors, [profileId]: null })); }}>{error ?? sessionErrors[profileId as string]}</p>}
    </section>
  );

  const renderSession = (entry: Json, index: number) => {
    const id: string = entry.profile_id;
    const profileId = id;
    const status = statuses[id];
    const connected = connections[id];
    const mine = busyFor[id] ?? null;
    const open = detailsOpen[id] ?? false;
    const setOpen = (change: (open: boolean) => boolean) => setDetailsOpen(s => ({ ...s, [id]: change(s[id] ?? false) }));
    const connect = () => connectSession(id);
    const check = (scope: string) => checkSession(id, scope);
    const copied = copiedKey?.startsWith(`${id}:`) ? copiedKey.slice(id.length + 1) : null;
    const family: string = entry.family ?? 'virtuoso';
    const transport: string = status?.transport || entry.transport || 'ssh';
    const local = transport === 'local';
    const overall = status?.overall ?? 'unknown';
    const summary = status?.summary;
    const ciw = connected?.details?.ciw ?? status?.ciw ?? null;
    const loadCommand = ciw ? `setShellEnvVar("RB_NONCE_CACHE_MAX" "32768")\n${ciw.load}` : '';
    const replaceCommand = ciw ? `setShellEnvVar("RB_NONCE_CACHE_MAX" "32768")\n${ciw.replace_running_daemon.join('\n')}` : '';
    // The CIW lines' Copy is the copy icon, as Output files' Copy run path (branch record SIF-114): its word for screen readers
    // and at the start of its tooltip. The 1.5 s "Copied" of a copy that went through is the check mark: the word changes, the
    // tooltip stays the action's, as Save now's does while it saves.
    const copyButton = (part: 'load' | 'replace', text: string) => (
      <button onClick={() => copyText(`${id}:${part}`, text)} title="Copy: These lines to the clipboard, to paste into the Virtuoso CIW.">
        <Icon name={copied === part ? 'check' : 'copy'} label={copied === part ? 'Copied' : 'Copy'} /></button>);
    const linkUp = local ? !!ciw : status?.layers?.some((l: Json) => l.layer === 'tunnel' && l.state === 'ok');
    // Each part and reason in words, its key in the tooltip: the table listed "session_readiness | UNKNOWN | never_checked"
    // (branch record SIF-55). The state badges keep the words the button's pill shows.
    const details = open && status && (
      <table className="grid small">
        <thead><tr><th>Layer</th><th>State</th><th>Reason</th></tr></thead>
        <tbody>
          {status.layers.map((l: Json) => (
            <tr key={l.layer} title={l.diagnostic ?? ''}>
              <td title={l.layer}>{layerWords(l.layer)}</td><td><span className={`badge state-${l.state}`}>{STATE_LABEL[l.state] ?? l.state}</span></td>
              <td>{l.reason_code && <span title={l.reason_code}>{l.reason_code.replace(/_/g, ' ')}</span>}{l.diagnostic && <div className="hint">{l.diagnostic}</div>}
                {l.details?.next_step && <div className="hint">Next step: {l.details.next_step}</div>}
                {l.details?.note && <div className="hint">{l.details.note}</div>}</td>
            </tr>))}
        </tbody>
        <tfoot><tr><td colSpan={3} className="hint">Last test took {status.duration_seconds ?? '-'} s. {family === 'ngspice'
          ? 'A test installs, starts and changes nothing. Its one simulation is the built-in three-element test circuit, never one of yours.'
          : 'A test observes and never starts, restarts or stops the tunnel, the daemon or Virtuoso. It is not the costed baseline simulation.'}
          {/* in local time, the backend's UTC in the tooltip (branch record SIF-55: it printed "2026-10-21T08:14:02.512+00:00") */}
          {status.run_active && <span title={status.last_successful_bridge_interaction_utc ? `UTC: ${status.last_successful_bridge_interaction_utc}` : undefined}>
            {` A run is active; last successful bridge interaction: ${stamp(status.last_successful_bridge_interaction_utc) ?? status.last_successful_bridge_interaction_utc ?? 'none yet'}.`}</span>}</td></tr></tfoot>
      </table>
    );
    const result = summary && <div className={`status-line level-${summary.level}`}>
      <strong>{summary.headline}</strong>
      {summary.next_step && <div className="hint">Next step: {summary.next_step}</div>}
    </div>;

    const virtuosoSteps = (<>
      <div className="step">
        <div className="step-head"><span className="step-no">1</span> {local ? 'Set up the bridge on this machine' : 'Connect to the target over SSH'}</div>
        {local && <p className="hint">Virtuoso runs on the same machine as the workbench backend, so there is no SSH and no tunnel: this step only places the bridge setup file and tells you the line to load.</p>}
        <div className="row">
          <button disabled={!profileId || !!mine} onClick={connect}
            title={local ? 'Does what `virtuoso-bridge start` does for a Virtuoso on this machine: places the bridge setup file and reports the line to load in the CIW. No SSH, no tunnel. It starts nothing if the bridge env file names another machine. Nothing is ever stopped or restarted.'
              : 'Starts the SSH tunnel of this profile, exactly like `virtuoso-bridge start`. A tunnel that is already running is left untouched. Nothing is ever stopped or restarted.'}>
            {local ? (mine === 'connect' ? 'Setting up...' : linkUp ? 'Set up local bridge (already done)' : 'Set up local bridge')
              : (mine === 'connect' ? 'Connecting... (can take a minute)' : linkUp ? 'Connect SSH (already up)' : 'Connect SSH')}</button>
        </div>
        {/* A failure reads in words, its code in the tooltip: it read "Connect failed: ssh_failed - TimeoutError: ..." (branch
            record SIF-55). The reason stays in front of the bridge's diagnostic, which alone can be as bare as "installed 1.2.3". */}
        {connected && <p className={connected.ok ? 'ok' : 'error'} title={connected.ok ? undefined : connected.reason_code ?? undefined}>
          {connected.ok ? (local ? (connected.action === 'already_running' ? 'The local bridge was already set up - left untouched.' : `Local bridge set up (${connected.duration_seconds} s).`)
            : (connected.action === 'already_running' ? 'SSH tunnel was already running - left untouched.' : `SSH tunnel started (${connected.duration_seconds} s).`))
            : `${local ? 'Set-up' : 'Connect'} failed: ${String(connected.reason_code ?? 'no reason given').replace(/_/g, ' ')}${connected.diagnostic ? ` - ${connected.diagnostic}` : ''}`}
          {connected.details?.next_step && <span className="hint"> Next step: {connected.details.next_step}</span>}</p>}
      </div>

      <div className="step">
        <div className="step-head"><span className="step-no">2</span> Load the bridge in the Virtuoso CIW</div>
        {ciw ? (
          <div>
            <p className="hint">Paste these lines into {multipleSessions ? `Virtuoso ${index + 1}'s` : 'your Virtuoso’s'} CIW, in order, then test this session below.</p>
            <div className="command"><code>{breakAfterSlash(loadCommand)}</code>{copyButton('load', loadCommand)}</div>
            <details><summary className="hint">CIW says "already running", or other trouble</summary>
              <p className="hint">Reload the bridge in this session:</p>
              <div className="command"><code>{breakAfterSlash(replaceCommand)}</code>{copyButton('replace', replaceCommand)}</div>
              <ul className="steps-list">{ciw.notes.map((n: string) => <li key={n} className="hint">{n}</li>)}</ul>
            </details>
          </div>
        ) : <p className="hint">{local ? 'The command appears here once the bridge is set up (step 1): the bridge reports the setup file it placed on this machine.'
          : 'The command appears here once the SSH tunnel is up (step 1): the bridge reports the setup file it placed on the Virtuoso host.'}</p>}
      </div>

      <div className="step">
        <div className="step-head"><span className="step-no">3</span> Test the connection</div>
        <div className="row">
          <button disabled={!profileId || !!mine} onClick={() => check('interactive')} title="Read-only and zero-cost: one trivial SKILL round trip. No simulation, no budget, no data rows. It never starts anything.">
            {mine === 'interactive' ? 'Testing...' : 'Test connection'}</button>
          {/* Named as the longer test it is: "+ Spectre / license" read like adding something (branch record SIF-79). */}
          <button disabled={!profileId || !!mine} onClick={() => check('full')}
            title="Test connection, then also finds Spectre on the simulator host and asks the license server once for free seats (a snapshot: it takes no seat). No simulation, no budget. Can be slow.">
            {mine === 'full' ? 'Testing...' : 'Full test (Spectre, license)'}</button>
          <button onClick={() => setOpen(o => !o)}>{open ? 'Hide' : 'Details'}</button>
        </div>
        {result}
      </div>
    </>);

    const ngspiceSteps = (<>
      <div className="step">
        <div className="step-head"><span className="step-no">1</span> {local ? 'Test ngspice on this machine' : 'Test ngspice over SSH'}</div>
        <p className="hint">Finds the ngspice program, reads its version and solves one built-in three-element test circuit. None of your circuits, no budget, no license.
          {!local && ' SSH runs in batch mode: it needs key-based login to the machine and cannot ask for a password.'} There is nothing to connect or to load first.</p>
        <div className="row">
          <button disabled={!profileId || !!mine} onClick={() => check('interactive')} title="Runs only when pressed. It installs, starts and changes nothing.">
            {mine === 'interactive' ? 'Testing...' : 'Test connection'}</button>
          <button onClick={() => setOpen(o => !o)}>{open ? 'Hide' : 'Details'}</button>
        </div>
        {result}
      </div>
      <div className="note"><p><b>What an ngspice connection runs: the ngspice netlist tasks</b> (Tasks window, "From an ngspice netlist..."). Every evaluation of such
        a task is one <code>ngspice -b</code> run {local ? 'on this machine' : 'on that machine, through ssh (the deck goes in on stdin; paths in it are that machine\'s)'};
        the test above is what a run checks first. Virtuoso cells and the verified GPDK045 tasks still need a Virtuoso connection; mock runs and
        everything offline need no connection at all.</p></div>
    </>);

    // A card names its session as one: "lab" read as the connection's name too, which takes its first session's (branch record SIF-79).
    return <section className="connection-session" key={id} data-session-profile={id} aria-label={multipleSessions ? `Virtuoso ${index + 1}` : 'Connection session'}>
      {multipleSessions && <h3>Virtuoso {index + 1} <span className="hint" title={id === group?.profile_id
        ? `This session's own name in the connection file. The connection is named after its first session: "${id}" in the list above sends the work to whichever session is free.`
        : `This session's own name in the connection file: a configuration or a queue that names ${id} sends its work to Virtuoso ${index + 1} only.`}>(session {id})</span></h3>}
      <div className="row">
        <span className={`badge state-${overall}`} title="Overall state of the last test">{STATE_LABEL[overall] ?? overall}</span>
        <span className="hint">{status?.checked_utc ? `tested at ${testedAt(status.checked_utc)}${status.stale ? ' - too old to trust, shown as unknown' : ''}` : 'never tested'}</span>
      </div>
      {/* A kind the connection file does not name is said on hover, in what it means for the user: the card said "(This
          connection was written before kinds existed; ...)" in two more lines, so its steps started lower than its sibling's
          (branch record SIF-79). */}
      {entry.kind_label && <p className="hint connection-kind"><b title={entry.kind && !entry.kind_declared
        ? 'The connection file does not say where Virtuoso runs, so this connection is taken as Virtuoso over SSH until a test finds Virtuoso on this machine. Nothing to do.'
        : undefined}>{entry.kind_label}.</b> {profiles?.kinds?.find((k: Json) => k.kind === entry.kind)?.summary
        ?? 'Press "Test connection" to see what has to be corrected in the connection file.'}</p>}
      {family === 'ngspice' ? ngspiceSteps : virtuosoSteps}
      {sessionErrors[id] && <p className="error">{sessionErrors[id]}</p>}
      {details}
    </section>;
  };

  const addForm = adding && (
    <div className="step connection-add">
      <div className="step-head">Add a connection</div>
      {!setup ? <p className="hint">Looking at what is installed on the backend machine...</p>
        : !setup.kinds ? <p className="warn">The workbench server that is running is older than this page and cannot add connections of a chosen kind yet. Restart it
          (Ctrl+C in its terminal, then start `serve` again) and press "Add a connection..." again.</p> : <>
        <label>What to connect to
          <select value={draft.kind} onChange={e => setDraft((d: Json) => ({ ...d, kind: e.target.value, name: '', ssh_host: '' }))}>
            {setup.kinds.map((k: Json) => <option key={k.kind} value={k.kind}>{k.label}</option>)}</select></label>
        {kindSetup && <>
          <p className="hint">{kindSetup.summary}</p>
          <ul className="steps-list">
            {kindSetup.checks.map((c: Json) => <li key={c.text} className={c.ok ? 'ok' : 'error'}>{c.ok ? 'found' : 'missing'}: {c.text}</li>)}
            {kindSetup.problems.map((p: Json) => <li key={p.reason_code} className="hint">{p.message}</li>)}
          </ul>
          {draft.kind === 'ngspice_ssh' && kindSetup.ssh_hosts.length > 0 && <label title="Only machines that ~/.ssh/config of the backend user already names can be chosen here. The address, user, port and key stay in that file.">Machine (a Host name from ~/.ssh/config)
            <select value={host} onChange={e => setDraft((d: Json) => ({ ...d, ssh_host: e.target.value }))}>{kindSetup.ssh_hosts.map((h: string) => <option key={h}>{h}</option>)}</select></label>}
          {kindSetup.family === 'virtuoso' && <label title="Only needed when the bridge env file holds several machines as named profiles (VB_REMOTE_HOST_<name>). Empty = the bridge's default profile.">Bridge profile (optional)
            <input value={draft.bridge_profile} placeholder="empty = the bridge's default" onChange={e => setDraft((d: Json) => ({ ...d, bridge_profile: e.target.value }))} /></label>}
          {/* Enter in the name is Create connection, as the ngspice window's path box reads its file on Enter (branch record
              SIF-109): it did nothing. Only here, the last box before the button: an Enter in Bridge profile, typed first,
              would add the connection under the suggested name. */}
          <label>Name of the new connection
            <input value={name} onChange={e => setDraft((d: Json) => ({ ...d, name: e.target.value }))}
              onKeyDown={e => { if (e.key === 'Enter' && canCreate) { e.preventDefault(); create(); } }} /></label>
          {nameProblem && <p className="error">{nameProblem}</p>}
          <p className="hint">{kindSetup.note}</p>
        </>}
        <div className="row">
          <button disabled={!canCreate} onClick={create}
            title="Adds this connection to the connection file on the backend machine. Connections that already exist are never changed; the previous file is kept as a copy. The browser sends only names - never an address, a path or a command.">
            {busy === 'profile' ? 'Creating...' : 'Create connection'}</button>
          <button disabled={!!busy} onClick={loadSetup} title="Look again, e.g. after installing ngspice or adding a Host to ~/.ssh/config">Refresh</button>
          {profiles?.profiles.length > 0 && <button onClick={() => setAdding(false)}>Cancel</button>}
        </div>
      </>}
    </div>
  );

  const view = (
    <div className={`connection-window${multipleSessions ? ' connection-multi' : ''}`}>
      <h2>Connection</h2>
      {profiles && profiles.profiles.length === 0
        ? <p className="hint">No connection is set up yet ({profiles.connection_file}). Manual editing, JSON import/export, data export and mock runs work without one.</p>
        : <div className="row">
          <label>Connection
            <select value={profileId ?? ''} onChange={e => setProfileId(e.target.value || null)}>
              <option value="">(none)</option>
              {groups.map((p: Json) => <option key={p.profile_id} value={p.profile_id}>{p.profile_id}{p.kind_label ? ` - ${p.kind_label}` : ''}{p.session_profile_ids.length > 1 ? ` (${p.session_profile_ids.length} sessions: whichever is free)` : ''}</option>)}
              {pinned && <option value={profileId as string}>{profileId} - {pinnedLabel} only</option>}
            </select>
          </label>
          <button onClick={startAdding}>{adding ? 'Close "Add a connection"' : 'Add a connection...'}</button>
        </div>}
      {profileId && profiles && profiles.profiles.length > 0 && !entry && <p className="warn">This configuration names the connection "{profileId}", which is not set up on
        this backend. Choose one of the connections above, or add one.</p>}
      {created && <p className="ok">Connection "{created.profile_id}" was added{created.backup ? ` (the previous file was kept as ${created.backup})` : ''}. {created.note}</p>}
      {addForm}
      {/* One noun for one thing: it said "Each Virtuoso window", then "each session", beside cards headed "Virtuoso 1" and
          "Virtuoso 2" (branch record SIF-79). */}
      {multipleSessions && <p className="hint">This connection has {sessions.length} sessions, {sessions.map((_, i) => `Virtuoso ${i + 1}`).join(', ').replace(/, (?=[^,]*$)/, ' and ')} below,
        each a Virtuoso with its own bridge: connect each one and paste its lines into that Virtuoso's CIW.</p>}
      {multipleSessions && (pinned
        ? <p className="warn">This configuration names {pinnedLabel} by its own name ({profileId}): runs, Check now and Save as go there, even
          while it is busy. Choose "{group.profile_id}" above to send them to whichever session is free.</p>
        : <p className="hint">Runs (Start, Baseline simulation, Calibration, Continue), Check now and Save as go to whichever session is free:
          first the one that holds the task's cell open for editing, then the one whose last test passed. The run's message says which.</p>)}
      <div className={multipleSessions ? 'connection-sessions-grid' : undefined}>{sessions.map(renderSession)}</div>
      {error && <p className="error">{error}</p>}
      {/* A section of its own, headed like the steps above (record 7.170, user: "separate the folders section with other section
          with similar style"): a folder sign where a step has its number - setting the folders is no step of connecting. It
          stays outside the chosen-connection part: "Add a connection" uses the bridge checkout folder. */}
      <div className="step folders-step">
        <div className="step-head"><span className="step-no step-sign"><Icon name="folder" /></span> Folders</div>
        {/* Which folders, said under the head: it read "Folders" over "Folders..." and only the button's tooltip said what they
            were (branch record SIF-79). The opened section then starts with how a folder's value works, not with this again. */}
        <p className="hint">Where GATOR keeps its files outside the repository: lock and crash journals, simulator scratch and the virtuoso-bridge
          checkout on this machine; initial-condition files and Maestro netlists on the simulator host.</p>
        <div className="row">
          <button onClick={() => setFolders(f => !f)}
            title="Shows each folder at its value in use, or as you typed it and have not saved yet; only Save folders writes a change. Opening it changes nothing.">
            {folders ? 'Close "Folders"' : 'Folders...'}</button>
        </div>
        {folders && <ConnectionFolders typed={typedFolders} setTyped={setTypedFolders} />}
      </div>
    </div>
  );
  return <>{launcher}<PopupPortal popup={popup} root={root}>{view}</PopupPortal></>;
}
