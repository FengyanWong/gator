import { useEffect, useState } from 'react';
import { api, ApiError, Json } from '../api';

const SIDES: [string, string][] = [
  ['local', 'On this machine (the workbench backend)'],
  ['simulator', 'On the simulator host (~ = the home of the user Virtuoso runs as)'],
];

/** The folders of the connection module, in the connection window (record 7.168; user: "the project might be used by
 *  others. Add directory settings for necessary files in the connection module with current setting as default"). Each
 *  folder starts at the value GATOR used before. Nothing is kept until "Save folders" is pressed: the backend checks every
 *  changed folder - one on this machine that GATOR writes into is made and written once - writes nothing unless all
 *  pass, and keeps the previous connection file as a copy. A folder that an environment variable of the backend decides
 *  is shown and cannot be changed here. */
export function ConnectionFolders() {
  const [shown, setShown] = useState<Json>(null);
  const [values, setValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; folder?: string } | null>(null);
  const [saved, setSaved] = useState<Json>(null);
  const take = (answer: Json) => {
    setShown(answer);
    setValues(Object.fromEntries(answer.fields.map((f: Json) => [f.key, f.set_by_environment ? f.value : f.saved ?? f.default])));
  };
  // A server started before record 7.168 has no such route: said in words, like "Add a connection" does for an old server.
  useEffect(() => {
    api.connectionDirectories().then(take, e => setError({ message: e instanceof ApiError && e.status === 404
      ? 'The workbench server that is running is older than this page and has no folder settings yet. Restart it (Ctrl+C in its terminal, then start `serve` again) and press "Folders..." again.'
      : e.message }));
  }, []);
  if (!shown) return (
    <div className="connection-add connection-folders">
      {error ? <p className="error">{error.message}</p> : <p className="hint">Reading the folders...</p>}</div>);

  const editable = (f: Json) => !f.set_by_environment;
  const changed: Json[] = shown.fields.filter((f: Json) => editable(f) && values[f.key].trim() !== (f.saved ?? f.default));
  const label = (key: string) => shown.fields.find((f: Json) => f.key === key)?.label ?? key;
  const save = async () => {
    setBusy(true); setError(null); setSaved(null);
    try {
      const answer = await api.saveConnectionDirectories(Object.fromEntries(changed.map(f => [f.key, values[f.key].trim() || null])));
      take(answer); setSaved(answer);
    } catch (e) {
      setError({ message: (e as Error).message, folder: e instanceof ApiError ? e.detail?.folder : undefined });
    } finally {
      setBusy(false);
    }
  };
  const atDefaults = shown.fields.every((f: Json) => !editable(f) || values[f.key] === f.default);
  return (
    <div className="connection-add connection-folders">
      <p className="hint">Where GATOR keeps the files of the simulator connection outside the repository. Each folder starts at the value GATOR
        has always used; a changed one is kept in the connection file ({shown.connection_file}) and takes effect when the folder is next used.</p>
      {SIDES.map(([side, title]) => <div key={side}>
        <p><b>{title}</b></p>
        {shown.fields.filter((f: Json) => f.side === side).map((f: Json) => (
          <div key={f.key} className="folder-field" data-folder={f.key}>
            {/* The folder's comment - what it holds, when a change takes effect - is its name's tooltip, with no text under
                it (record 7.170, user: "if comments can be seen floating over name then delete the comment text underneath
                it"). Under it stays only what is the case now: the environment decides it, or the typed value is not the
                default. */}
            <label title={`${f.used_for} Takes effect: ${f.takes_effect}.`}>{f.label}
              <input value={values[f.key] ?? ''} placeholder={f.default} disabled={!editable(f) || busy} spellCheck={false}
                aria-invalid={error?.folder === f.key || undefined}
                onChange={e => { const typed = e.target.value; setSaved(null); setValues(v => ({ ...v, [f.key]: typed })); }} /></label>
            {f.set_by_environment ? <p className="hint">Set by {f.set_by_environment} in the backend's environment{f.saved ? ` (the connection file says ${f.saved})` : ''}.</p>
              : (values[f.key] ?? '').trim() !== f.default && <p className="hint">Default: {f.default}.</p>}
            {f.problem && <p className="warn">{f.problem}</p>}
          </div>))}
      </div>)}
      <div className="row">
        <button disabled={busy || changed.length === 0} onClick={save}
          title="Checks every changed folder, then writes the folders into the connection file; the previous file is kept as a copy. The connections are not changed.">
          {busy ? 'Saving...' : 'Save folders'}</button>
        <button disabled={busy || changed.length === 0} onClick={() => { take(shown); setError(null); }}>Undo changes</button>
        <button disabled={busy || atDefaults} title="Puts every folder back to its default in the fields above; press Save folders to keep that."
          onClick={() => setValues(v => ({ ...v, ...Object.fromEntries(shown.fields.filter(editable).map((f: Json) => [f.key, f.default])) }))}>Use defaults</button>
      </div>
      {error && <p className="error">{error.message}</p>}
      {saved && <p className="ok">{saved.saved ? `Saved: ${saved.changed.map(label).join(', ')}.${saved.backup ? ` The previous file was kept as ${saved.backup}.` : ''}`
        : 'Nothing changed.'}</p>}
      <p className="hint">{shown.note}</p>
    </div>
  );
}
