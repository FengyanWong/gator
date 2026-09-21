import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { api, Json } from '../api';

const STATE_LABEL: Record<string, string> = {
  ok: 'OK', failed: 'FAILED', not_ready: 'NOT READY', not_applicable: 'n/a', not_checked: 'not checked', busy: 'BUSY', unknown: 'UNKNOWN',
};
const NAME = /^[A-Za-z0-9][A-Za-z0-9_.\-]{0,63}$/;
const SUGGESTED_NAME: Record<string, string> = { virtuoso_ssh: 'lab', virtuoso_local: 'virtuoso-local', ngspice_local: 'ngspice-local', ngspice_ssh: 'ngspice-ssh' };

/** A fixed clock time instead of a running "N s ago": nothing re-renders this on a timer, so an age would freeze. */
const testedAt = (iso: string) => {
  const at = new Date(iso);
  return at.toDateString() === new Date().toDateString() ? at.toLocaleTimeString() : at.toLocaleString();
};

/** The connection block of the left column: ONE button (user request 2026-09-21). Pressing it opens the connection
 *  window - a browser window of its own, drawn through a portal, so the state below lives here and nothing has to be
 *  synchronised between two windows (the mechanism of the detached Agent conversation).
 *
 *  What it connects to is the profile's KIND: Virtuoso over SSH, Virtuoso on this machine, ngspice on this machine,
 *  ngspice over SSH. The steps and their wording follow the kind; the backend names the kinds, this file only words them.
 *
 *  Unchanged rules (section 2.1, user request 2026-09-20): a TEST only observes; a tunnel or a local bridge is set up by
 *  its explicit button alone; nothing is ever stopped or restarted; and nothing is checked on page load, on a timer or
 *  when the window opens - page load reads the profiles and the backend's LAST result once, a probe runs only on a press. */
export function ConnectionButton({ profileId, setProfileId }: { profileId: string | null; setProfileId: (id: string | null) => void }) {
  const [profiles, setProfiles] = useState<Json>(null);
  const [setup, setSetup] = useState<Json>(null);
  const [status, setStatus] = useState<Json>(null);
  const [connected, setConnected] = useState<Json>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [popup, setPopup] = useState<Window | null>(null);      // while set, the connection window is open
  const [blocked, setBlocked] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState<Json>({ kind: 'virtuoso_ssh', name: '', ssh_host: '', bridge_profile: '' });
  const [created, setCreated] = useState<Json>(null);

  const loadSetup = () => api.connectionSetup().then(setSetup).catch(e => setError(e.message));          // locates and names; contacts nothing
  const loadProfiles = () => api.connectionProfiles().then(p => {
    setProfiles(p); if (!profileId && p.active) setProfileId(p.active);
    if (p.profiles.length === 0) { setAdding(true); loadSetup(); }
  }).catch(e => setError(e.message));
  useEffect(() => { loadProfiles(); }, []);
  useEffect(() => {
    setConnected(null);
    if (!profileId) { setStatus(null); return; }
    // Profile change / page load: show the last result the backend remembers. This READS the cache and probes nothing.
    // A check runs only on a button press below (user request 2026-09-20): no automatic check, no timer.
    let live = true;
    api.connectionStatus(profileId).then(s => { if (live) setStatus(s); }).catch(e => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [profileId]);

  // ---- the window ------------------------------------------------------------------------------------------------
  const openWindow = () => {
    if (popup && !popup.closed) { popup.focus(); return; }
    const opened = window.open('', 'gator-connection', 'popup,width=660,height=920');
    if (!opened) { setBlocked('The browser blocked the new window. Allow pop-ups for this page, then press the button again.'); return; }
    const doc = opened.document;
    doc.title = 'GATOR - connection';
    doc.head.querySelectorAll('link, style').forEach(node => node.remove());          // a window of that name may be reused
    document.querySelectorAll<HTMLElement>('link[rel="stylesheet"], style').forEach(node => {
      const copy = node.cloneNode(true) as HTMLElement;
      if (node instanceof HTMLLinkElement) (copy as HTMLLinkElement).href = node.href;   // absolute: the new window is about:blank
      doc.head.appendChild(copy);
    });
    doc.body.innerHTML = '<div id="connection-root"></div>';
    setBlocked(null); setPopup(opened);
  };
  useEffect(() => {
    if (!popup) return;
    const closed = () => setPopup(null);                   // the window was closed with its own close button
    const leave = () => popup.close();                     // the workbench page is leaving: do not leave a dead window behind
    popup.addEventListener('pagehide', closed);
    window.addEventListener('pagehide', leave);
    return () => { popup.removeEventListener('pagehide', closed); window.removeEventListener('pagehide', leave); };
  }, [popup]);

  // ---- actions: every one of them is a button press ----------------------------------------------------------------
  const run = async (name: string, action: () => Promise<void>) => {
    setBusy(name); setError(null);
    try { await action(); } catch (e: any) { setError(e.message); } finally { setBusy(null); }
  };
  const connect = () => run('connect', async () => { const answer = await api.connectionConnect(profileId!); setConnected(answer.connect); setStatus(answer.status); });
  const check = (scope: string) => run(scope, async () => { setStatus(await api.connectionCheck(profileId!, scope)); });
  // The click happens in the connection window, so ITS clipboard is the one a browser lets this gesture write to.
  const copyText = (key: string, text: string) => { (popup ?? window).navigator.clipboard?.writeText(text); setCopied(key); setTimeout(() => setCopied(c => (c === key ? null : c)), 1500); };

  const entry: Json = profiles?.profiles.find((p: Json) => p.profile_id === profileId) ?? null;
  const family: string = entry?.family ?? 'virtuoso';
  // What the last test found out beats the declared kind: a profile written before kinds existed may still be local.
  const transport: string = (status?.profile_id === profileId && status?.transport) || entry?.transport || 'ssh';
  const local = transport === 'local';
  const overall = status?.overall ?? 'unknown';
  const summary = status?.summary;
  const ciw = connected?.details?.ciw ?? status?.ciw ?? null;
  const linkUp = local ? !!ciw : status?.layers?.some((l: Json) => l.layer === 'tunnel' && l.state === 'ok');

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
    setProfiles(made.profiles); setProfileId(made.profile_id); setCreated(made); setAdding(false);
    setDraft((d: Json) => ({ ...d, name: '', bridge_profile: '' }));
  });

  const launcher = (
    <section className="panel connection-launcher">
      <button className="connection-button" onClick={openWindow}
        title={popup ? 'The connection window is open: press to bring it to the front.' : 'Opens the connection window: choose or add a connection (Virtuoso or ngspice, on this machine or over SSH), connect and test it. Opening it checks nothing.'}>
        <span className="connection-button-name">Connection</span>
        <span className="connection-button-what">{profileId ? `${profileId}${entry?.kind_label ? ` - ${entry.kind_label}` : ''}` : profiles && profiles.profiles.length === 0 ? 'none set up yet' : 'none selected'}{popup ? ' (window open)' : ''}</span>
        {profileId && <span className={`badge state-${overall}`} title={status?.checked_utc ? `Last test: ${testedAt(status.checked_utc)}` : 'Never tested'}>{STATE_LABEL[overall] ?? overall}</span>}
      </button>
      {blocked && <p className="error">{blocked}</p>}
    </section>
  );

  const details = open && status && (
    <table className="grid small">
      <thead><tr><th>Layer</th><th>State</th><th>Reason</th></tr></thead>
      <tbody>
        {status.layers.map((l: Json) => (
          <tr key={l.layer} title={l.diagnostic ?? ''}>
            <td>{l.layer}</td><td><span className={`badge state-${l.state}`}>{STATE_LABEL[l.state] ?? l.state}</span></td>
            <td>{l.reason_code ?? ''}{l.diagnostic && <div className="hint">{l.diagnostic}</div>}
              {l.details?.next_step && <div className="hint">Next step: {l.details.next_step}</div>}
              {l.details?.note && <div className="hint">{l.details.note}</div>}</td>
          </tr>))}
      </tbody>
      <tfoot><tr><td colSpan={3} className="hint">Last test took {status.duration_seconds ?? '-'} s. {family === 'ngspice'
        ? 'A test installs, starts and changes nothing. Its one simulation is the built-in three-element test circuit, never one of yours.'
        : 'A test observes and never starts, restarts or stops the tunnel, the daemon or Virtuoso. It is not the costed baseline simulation.'}
        {status.run_active && ` A run is active; last successful bridge interaction: ${status.last_successful_bridge_interaction_utc ?? 'none yet'}.`}</td></tr></tfoot>
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
        <button disabled={!profileId || !!busy} onClick={connect}
          title={local ? 'Does what `virtuoso-bridge start` does for a Virtuoso on this machine: places the bridge setup file and reports the line to load in the CIW. No SSH, no tunnel. It starts nothing if the bridge env file names another machine. Nothing is ever stopped or restarted.'
            : 'Starts the SSH tunnel of this profile, exactly like `virtuoso-bridge start`. A tunnel that is already running is left untouched. Nothing is ever stopped or restarted.'}>
          {local ? (busy === 'connect' ? 'Setting up...' : linkUp ? 'Set up local bridge (already done)' : 'Set up local bridge')
            : (busy === 'connect' ? 'Connecting... (can take a minute)' : linkUp ? 'Connect SSH (already up)' : 'Connect SSH')}</button>
      </div>
      {connected && <p className={connected.ok ? 'ok' : 'error'}>
        {connected.ok ? (local ? (connected.action === 'already_running' ? 'The local bridge was already set up - left untouched.' : `Local bridge set up (${connected.duration_seconds} s).`)
          : (connected.action === 'already_running' ? 'SSH tunnel was already running - left untouched.' : `SSH tunnel started (${connected.duration_seconds} s).`))
          : `${local ? 'Set-up' : 'Connect'} failed: ${connected.reason_code}${connected.diagnostic ? ` - ${connected.diagnostic}` : ''}`}
        {connected.details?.next_step && <span className="hint"> Next step: {connected.details.next_step}</span>}</p>}
    </div>

    <div className="step">
      <div className="step-head"><span className="step-no">2</span> Load the bridge in the Virtuoso CIW</div>
      {ciw ? (
        <div>
          <p className="hint">Paste this line into the CIW input line of your running Virtuoso, press Enter, then test below.</p>
          <div className="command"><code>{ciw.load}</code><button onClick={() => copyText('load', ciw.load)}>{copied === 'load' ? 'Copied' : 'Copy'}</button></div>
          <details><summary className="hint">CIW says "already running", or other trouble</summary>
            <p className="hint">Replace a running daemon (two lines):</p>
            <div className="command"><code>{ciw.replace_running_daemon.join('\n')}</code>
              <button onClick={() => copyText('replace', ciw.replace_running_daemon.join('\n'))}>{copied === 'replace' ? 'Copied' : 'Copy'}</button></div>
            <ul className="steps-list">{ciw.notes.map((n: string) => <li key={n} className="hint">{n}</li>)}</ul>
          </details>
        </div>
      ) : <p className="hint">{local ? 'The command appears here once the bridge is set up (step 1): the bridge reports the setup file it placed on this machine.'
        : 'The command appears here once the SSH tunnel is up (step 1): the bridge reports the setup file it placed on the Virtuoso host.'}</p>}
    </div>

    <div className="step">
      <div className="step-head"><span className="step-no">3</span> Test the connection</div>
      <div className="row">
        <button disabled={!profileId || !!busy} onClick={() => check('interactive')} title="Read-only and zero-cost: one trivial SKILL round trip. No simulation, no budget, no data rows. It never starts anything.">
          {busy === 'interactive' ? 'Testing...' : 'Test connection'}</button>
        <button disabled={!profileId || !!busy} onClick={() => check('full')} title="Adds Spectre and a license SNAPSHOT (can be slow)">{busy === 'full' ? 'Testing...' : '+ Spectre / license'}</button>
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
        <button disabled={!profileId || !!busy} onClick={() => check('interactive')} title="Runs only when pressed. It installs, starts and changes nothing.">
          {busy === 'interactive' ? 'Testing...' : 'Test connection'}</button>
        <button onClick={() => setOpen(o => !o)}>{open ? 'Hide' : 'Details'}</button>
      </div>
      {result}
    </div>
    <div className="note"><p><b>What an ngspice connection can do today: be tested.</b> Running circuits on ngspice is not built yet, so real runs
      still need a Virtuoso connection, and reading a Virtuoso library needs one too. Mock runs, netlist import and everything offline need no connection at all.</p></div>
  </>);

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
          <label>Name of the new connection
            <input value={name} onChange={e => setDraft((d: Json) => ({ ...d, name: e.target.value }))} /></label>
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
    <div className="connection-window">
      <h2>Connection</h2>
      {profiles && profiles.profiles.length === 0
        ? <p className="hint">No connection is set up yet ({profiles.connection_file}). Netlist import, manual editing, JSON import/export, data export and mock runs work without one.</p>
        : <div className="row">
          <label>Connection
            <select value={profileId ?? ''} onChange={e => setProfileId(e.target.value || null)}>
              <option value="">(none)</option>
              {profiles?.profiles.map((p: Json) => <option key={p.profile_id} value={p.profile_id}>{p.profile_id}{p.kind_label ? ` - ${p.kind_label}` : ''}</option>)}
            </select>
          </label>
          <button onClick={startAdding}>{adding ? 'Close "Add a connection"' : 'Add a connection...'}</button>
        </div>}
      {profileId && profiles && profiles.profiles.length > 0 && !entry && <p className="warn">This configuration names the connection "{profileId}", which is not set up on
        this backend. Choose one of the connections above, or add one.</p>}
      {created && <p className="ok">Connection "{created.profile_id}" was added{created.backup ? ` (the previous file was kept as ${created.backup})` : ''}. {created.note}</p>}
      {addForm}
      {entry && <>
        <div className="row">
          <span className={`badge state-${overall}`} title="Overall state of the last test">{STATE_LABEL[overall] ?? overall}</span>
          <span className="hint">{status?.checked_utc ? `tested at ${testedAt(status.checked_utc)}${status.stale ? ' - too old to trust, shown as unknown' : ''}` : 'never tested'}</span>
        </div>
        {/* An older backend names no kinds: the line is left out and the steps read as Virtuoso over SSH, which is all it knows. */}
        {entry.kind_label && <p className="hint connection-kind"><b>{entry.kind_label}.</b> {profiles?.kinds?.find((k: Json) => k.kind === entry.kind)?.summary
          ?? 'Press "Test connection" to see what has to be corrected in the connection file.'}
          {entry.kind && !entry.kind_declared && ' (This connection was written before kinds existed; it is treated as Virtuoso over SSH unless a test finds Virtuoso on this machine.)'}</p>}
        {family === 'ngspice' ? ngspiceSteps : virtuosoSteps}
      </>}
      {error && <p className="error">{error}</p>}
      {details}
    </div>
  );
  const root = popup?.document.getElementById('connection-root');
  return <>{launcher}{popup && root && createPortal(view, root)}</>;
}
