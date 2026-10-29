"""Model lifecycle and cancellable background jobs, separate from all optimizer runs."""
from __future__ import annotations

from contextlib import suppress
import codecs
import copy
import json
import os
from pathlib import Path
import threading
from uuid import uuid4

from ..paths import local_settings_dir
from ..security import redact
from .catalog import CATALOG
from .install import download, install_runtime, verify_file
from .profile import DEFAULT_LOCAL_MODEL
from .proposals import INSTRUCTIONS, advisory_context, circuit_fingerprint, decode_reply, fingerprint, validate_proposal
from .runtime import Cancelled, Runtime, asset_root, compatibility, hardware, local_path, prompt_text


class Manager:
    def __init__(self, root=None):
        self.root = Path(root) if root else local_settings_dir() / 'local-agent'
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.owner = (self.root / 'owner.lock').open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.owner.seek(0)
                if not self.owner.read(1):
                    self.owner.write(b'0'); self.owner.flush()
                self.owner.seek(0)
                msvcrt.locking(self.owner.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.owner.close()
            raise ValueError('Another backend owns this Agent storage. Use that backend or a separate settings directory.')
        self.state = json.loads((self.root / 'models.json').read_text()) if (self.root / 'models.json').is_file() else {}
        self.jobs, self.active, self.deployed = {}, None, None
        self.runtime = None
        self.closed = False

    def _save(self):
        destination = self.root / 'models.json'
        temporary = destination.with_suffix('.tmp')
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(self.state, stream, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(destination)

    def _runtime(self):
        if self.runtime:
            return self.runtime
        given = os.environ.get('GATOR_AGENT_RUNTIME')
        choices = ([local_path(given)] if given else []) + [asset_root() / 'bin' / 'llama-completion.exe'] + \
            list((self.root / 'runtime-b11669').rglob('llama-completion.exe'))
        for choice in choices:
            if choice.is_file():
                candidate = Runtime(choice)
                candidate.verify()
                self.runtime = candidate
                return candidate
        return None

    def _path(self, model):
        record = self.state.get(model.id, {})
        if not record.get('installed'):
            return None
        path = local_path(record['path'])
        if record.get('storage') == 'managed' and path != (self.root / 'models' / model.filename).resolve():
            raise ValueError('Managed model record is outside the model store.')
        if not path.is_file() or path.stat().st_size != model.size:
            return None
        return path

    def preflight(self, model_id):
        model = CATALOG[model_id]
        host = hardware(self.root)
        errors, ready = [], False
        try:
            ready = self._runtime() is not None
        except Exception as exc:
            errors.append(str(exc))
        source = asset_root() / 'models' / model.filename
        reusable = source.is_file() and source.stat().st_size == model.size
        result = compatibility(model, host, installed=self._path(model) is not None, reusable=reusable, runtime_ready=ready)
        result['errors'].extend(errors)
        result['compatible'] = not result['errors']
        return dict(result, host=host, runtime_ready=ready, local_asset_available=reusable)

    def status(self):
        with self.lock:
            return dict(models=[dict(m.public(), installed=self._path(m) is not None,
                                     storage=self.state.get(m.id, {}).get('storage'), deployed=self.deployed == m.id,
                                     error=self.state.get(m.id, {}).get('error')) for m in CATALOG.values()],
                        active_job=self.active, deployed=self.deployed,
                        default_model=DEFAULT_LOCAL_MODEL, mode='Loads per reply; GPU released after each answer')

    def _start(self, model_id, kind, work):
        with self.lock:
            if self.closed or self.active:
                raise ValueError('An Agent operation is already active. Cancel it or wait for completion.')
            # Drop old in-memory results, never truncate an answer. Owned logs remain local until explicitly removed.
            while len(self.jobs) >= 20:
                del self.jobs[next(iter(self.jobs))]
            job_id = uuid4().hex
            job = dict(id=job_id, model_id=model_id, kind=kind, state='running', phase='Starting',
                       bytes=0, total=None, error=None, cancel=threading.Event(), result=None,
                       folder=self.root / 'jobs' / job_id)
            self.jobs[job_id], self.active = job, job_id
            def progress(phase, read=0, total=None):
                with self.lock:
                    job.update(phase=phase, bytes=read, total=total)
            def run():
                try:
                    result = work(job, progress)
                    if kind == 'chat' and job['cancel'].is_set():
                        raise Cancelled()
                    with self.lock:
                        job.update(state='completed', phase='Completed', result=result)
                except Cancelled:
                    with self.lock:
                        job.update(state='cancelled', phase='Cancelled')
                except Exception as exc:
                    with self.lock:
                        if kind == 'chat' and self.deployed == model_id:
                            self.deployed = None
                        error = redact(f'{type(exc).__name__}: {exc}', 3000)
                        job.update(state='failed', phase='Failed', error=error)
                        self.state.setdefault(model_id, {})['error'] = error
                        with suppress(Exception):
                            self._save()
                finally:
                    with self.lock:
                        if kind == 'deploy' and job['state'] != 'completed' and self.deployed == model_id:
                            self.deployed = None
                        self.active = None
            job['thread'] = threading.Thread(target=run, name='gator-local-agent-' + kind, daemon=True)
            job['thread'].start()
            return dict(job_id=job_id)

    def install(self, model_id, *, local_only=False):
        model = CATALOG[model_id]
        def work(job, progress):
            if self._path(model):
                raise ValueError('This model is already installed.')
            source = asset_root() / 'models' / model.filename
            if local_only and not source.is_file():
                raise ValueError('The default local 74B asset is not present. Choose Install to download it.')
            check = self.preflight(model_id)
            if not check['compatible']:
                raise ValueError(' '.join(check['errors']))
            runtime = self._runtime()
            if runtime is None:
                runtime = install_runtime(self.root, job['cancel'], progress)
                self.runtime = runtime
            if source.is_file():
                verify_file(source, model.size, model.sha256, job['cancel'], progress)
                path, storage = source, 'external'
            else:
                path, storage = self.root / 'models' / model.filename, 'managed'
                download(model.url, path, model.size, model.sha256, job['cancel'], progress)
            if job['cancel'].is_set():
                if storage == 'managed':
                    path.unlink(missing_ok=True)
                raise Cancelled()
            with self.lock:
                previous = copy.deepcopy(self.state.get(model_id))
                self.state[model_id] = dict(installed=True, storage=storage, path=str(path.resolve()), error=None)
                try:
                    self._save()
                except Exception:
                    if previous is None:
                        self.state.pop(model_id, None)
                    else:
                        self.state[model_id] = previous
                    if storage == 'managed':
                        path.unlink(missing_ok=True)
                    raise
            return dict(installed=True, storage=storage)
        return self._start(model_id, 'install', work)

    def bootstrap(self):
        with self.lock:
            if DEFAULT_LOCAL_MODEL and not self.state.get('default_profile_seen') and not self.active:
                self.state['default_profile_seen'] = True
                self._save()
                if not self._path(CATALOG[DEFAULT_LOCAL_MODEL]):
                    return self.install(DEFAULT_LOCAL_MODEL, local_only=True)

    def deploy(self, model_id):
        model = CATALOG[model_id]
        def work(job, progress):
            path = self._path(model)
            if path is None:
                raise ValueError('Install this model first.')
            if self.deployed is not None:
                raise ValueError('Undeploy the current model first.')
            check = self.preflight(model_id)
            if not check['compatible']:
                raise ValueError(' '.join(check['errors']))
            runtime = self._runtime()
            if runtime is None:
                raise ValueError('The installed runtime is missing; install the model again to repair it.')
            verify_file(path, model.size, model.sha256, job['cancel'], progress)
            progress('Verifying actual model load and uncapped inference')
            answer = runtime.generate(model, path, prompt_text(model, [('user', 'Reply with the single word Ready.')]),
                                      job['folder'], job['cancel'], check['gpu_index'])
            if not answer:
                raise ValueError('The deployment probe produced no answer.')
            with self.lock:
                if job['cancel'].is_set():
                    raise Cancelled()
                self.deployed = model_id
                self.state[model_id]['error'] = None
                self._save()
            return dict(deployed=True, probe=answer, mode='Loads per reply')
        return self._start(model_id, 'deploy', work)

    def cancel(self, job_id):
        with self.lock:
            job = self.jobs[job_id]
            if job['state'] == 'running':
                job['cancel'].set()
                job['phase'] = 'Cancelling'
            return dict(state=job['state'])

    def undeploy(self, model_id):
        with self.lock:
            if self.active:
                active = self.jobs[self.active]
                if active['model_id'] == model_id and active['kind'] in ('chat', 'deploy'):
                    self.cancel(self.active)
                else:
                    raise ValueError('Wait for or cancel the current installation first.')
            if self.deployed == model_id:
                self.deployed = None
            return dict(deployed=False, cancelling=self.active is not None)

    def delete(self, model_id):
        with self.lock:
            if self.active or self.deployed == model_id:
                raise ValueError('Undeploy and wait for cancellation to finish before deleting a model.')
            model = CATALOG[model_id]
            record = self.state.get(model_id, {})
            # Delete only the exact owned file. External benchmark assets are never deleted.
            if record.get('storage') == 'managed':
                owned = self.root / 'models' / model.filename
                if owned.is_symlink() or not owned.resolve().is_relative_to(self.root.resolve()):
                    raise ValueError('Refusing to delete a model outside the owned store.')
                owned.unlink(missing_ok=True)
            self.state.pop(model_id, None)
            self._save()
            return dict(installed=False, external_file_preserved=record.get('storage') == 'external')

    def chat(self, model_id, config, messages, context):
        model = CATALOG[model_id]
        baseline = copy.deepcopy(config)
        digest = fingerprint(baseline)
        safe_context = advisory_context(baseline)
        def work(job, progress):
            if self.deployed != model_id:
                raise ValueError('Deploy this model before sending a message.')
            check = self.preflight(model_id)
            if not check['compatible']:
                raise ValueError(' '.join(check['errors']))
            evidence = None
            with suppress(Exception):
                _, loaded, _ = context.load_config(baseline)
                evidence = circuit_fingerprint(loaded)
            # Keep the newest conversation exchanges; the UI explicitly reports this rolling input window.
            kept, count = [], len(safe_context) + len(INSTRUCTIONS)
            for message in reversed(messages):
                if kept and count + len(message['content']) > 14000:
                    break
                kept.insert(0, (message['role'], message['content']))
                count += len(message['content'])
            omitted = len(messages) - len(kept)
            prompt = prompt_text(model, [('user', INSTRUCTIONS + safe_context)] + kept)
            progress('Generating locally · no answer-token limit')
            answer = self._runtime().generate(model, self._path(model), prompt, job['folder'], job['cancel'], check['gpu_index'])
            result = decode_reply(answer)
            result.update(omitted_messages=omitted, config_fingerprint=digest)
            if result['proposal'] is not None:
                try:
                    reviewed = validate_proposal(baseline, result['proposal'], context)
                    if reviewed['validation_fingerprint'] != evidence:
                        raise ValueError('Circuit evidence changed or was unavailable while generating this suggestion. Ask again.')
                    result['preview'] = reviewed
                except Exception as exc:
                    result['proposal_error'] = redact(str(exc), 3000)
            # Snapshot is server-owned; the model cannot choose which revision a suggestion belongs to.
            job['baseline'], job['fingerprint'] = baseline, digest
            return result
        return self._start(model_id, 'chat', work)

    def job(self, job_id, offset=0):
        with self.lock:
            job = self.jobs[job_id]
            output = job['folder'] / 'inference' / 'stdout.txt'
            chunk, next_offset = '', offset
            if output.is_file():
                with output.open('rb') as stream:
                    stream.seek(offset)
                    data = stream.read(65536)
                    # A partial UTF-8 character stays for the next poll.
                    decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
                    chunk = decoder.decode(data, final=job['state'] != 'running')
                    next_offset += len(data) - len(decoder.getstate()[0])
            return {**{k: job[k] for k in ('id', 'model_id', 'kind', 'state', 'phase', 'bytes', 'total', 'error', 'result')},
                    'output': chunk, 'offset': next_offset}

    def review(self, job_id, current, context):
        with self.lock:
            job = self.jobs[job_id]
            if job['state'] != 'completed' or not job.get('result', {}).get('proposal') or job['result'].get('proposal_error'):
                raise ValueError('There is no valid completed proposal to apply.')
            if fingerprint(current) != job.get('fingerprint'):
                raise ValueError('This suggestion is stale: the configuration or schema changed. Ask again.')
            # Re-read circuit/PDK evidence and current schema immediately before application.
            reviewed = validate_proposal(current, job['result']['proposal'], context)
            if reviewed['validation_fingerprint'] != job['result']['preview']['validation_fingerprint']:
                raise ValueError('This suggestion is stale: circuit evidence changed. Ask again.')
            return reviewed

    def close(self):
        with self.lock:
            self.closed = True
            active = self.jobs.get(self.active)
            if active:
                active['cancel'].set()
        if active:
            active['thread'].join(timeout=25)
        self.deployed = None
        self.owner.close()
