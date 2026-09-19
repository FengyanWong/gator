"""Owned Spectre scratch on the existing Virtuoso Bridge transport.

The helper uses only the target's Python standard library. It never searches or
deletes unrelated bridge workdirs. Transport errors leave records for recovery.
"""
import json
import shlex

# Kept as a separate, auditable program; also exercised locally in offline tests.
HELPER = r'''
import errno, fcntl, json, os, shutil, sys, uuid
if sys.version_info < (2, 7):
    raise RuntimeError('Scratch helper requires Python 2.7 or newer')
request = json.loads(sys.argv[1])
root = request['root']
if not os.path.isabs(root) or os.path.realpath(root) != root or os.path.islink(root):
    raise RuntimeError('Scratch root must be an absolute canonical path')
if not os.path.isdir(root):
    try: os.makedirs(root)
    except OSError as exc:
        if exc.errno != errno.EEXIST or not os.path.isdir(root): raise
lock = open(os.path.join(root, '.gator-space.lock'), 'a+b')
fcntl.flock(lock, fcntl.LOCK_EX)
def read(path, mode='r'):
    with open(path, mode) as stream: return stream.read()
def write(path, value):
    with open(path, 'w') as stream: stream.write(value)
root_marker = os.path.join(root, '.gator-scratch-root')
if not os.path.lexists(root_marker):
    if any(name != '.gator-space.lock' for name in os.listdir(root)):
        raise RuntimeError('Scratch root already contains unowned files')
    write(root_marker, 'gator-recording-v1')
elif os.path.islink(root_marker) or read(root_marker) != 'gator-recording-v1':
    raise RuntimeError('Scratch root ownership mismatch')
def size(path):
    if os.path.islink(path): raise RuntimeError('Symlink in scratch directory')
    if os.path.isfile(path): return os.stat(path).st_size
    return sum(size(os.path.join(path, name)) for name in os.listdir(path))
def free():
    usage = os.statvfs(root)
    return usage.f_bavail * usage.f_frsize
def idle(path):
    for base, dirs, files in os.walk(path):
        for name in files:
            if not name.endswith('.pid'): continue
            text = read(os.path.join(base, name)).strip()
            if text.isdigit():
                try: os.kill(int(text), 0)
                except OSError as exc:
                    if exc.errno != errno.ESRCH: raise
                else: raise RuntimeError('Workspace process still alive or unverified')
    for name in os.listdir('/proc'):
        if not name.isdigit() or int(name) == os.getpid(): continue
        proc = os.path.join('/proc', name)
        try:
            if os.stat(proc).st_uid != os.getuid(): continue
            comm = read(os.path.join(proc, 'comm')).strip()
            if not comm.startswith('spectre'): continue
            cwd = os.path.realpath(os.path.join(proc, 'cwd'))
            cmd = read(os.path.join(proc, 'cmdline'), 'rb')
            if cwd == path or cwd.startswith(path + os.sep) or path.encode('utf8') in cmd:
                raise RuntimeError('Spectre still uses the workspace')
        except OSError as exc:
            if exc.errno not in (errno.ENOENT, errno.ESRCH): raise
def checked():
    path = request['path']
    if os.path.dirname(path) != root or os.path.realpath(path) != path or os.path.islink(path):
        raise RuntimeError('Scratch path escaped root')
    if not os.path.exists(path): return path, None
    size(path)
    marker = json.loads(read(os.path.join(path, '.gator-owned')))
    if marker['token'] != request['token'] or marker['eval_id'] != request['eval_id']:
        raise RuntimeError('Scratch ownership mismatch')
    return path, marker
operation = request['operation']
if operation == 'create':
    used = size(root)
    active = sum(1 for name in os.listdir(root) if os.path.isdir(os.path.join(root, name)))
    reserve = (active + 1) * request['reserve']
    if used + reserve > request['budget'] or free() - reserve < request['min_free']:
        raise RuntimeError('Spectre scratch capacity exhausted; stop dispatch')
    path = os.path.join(root, uuid.uuid4().hex)
    os.mkdir(path)
    marker = dict(eval_id=request['eval_id'], token=uuid.uuid4().hex, finished=False)
    write(os.path.join(path, '.gator-owned'), json.dumps(marker))
    print(json.dumps(dict(marker, path=str(path), root=str(root), bytes=0)))
elif operation == 'usage':
    print(json.dumps(dict(bytes=size(root), free=free())))
else:
    path, marker = checked()
    if marker is not None:
        idle(path)
        if operation == 'finish':
            marker['finished'] = True
            write(os.path.join(path, '.gator-owned'), json.dumps(marker))
        elif operation == 'delete':
            if not marker['finished']: raise RuntimeError('Workspace is not finished')
            shutil.rmtree(path)
        else: raise RuntimeError('Unknown scratch operation')
    print(json.dumps(dict(ok=True)))
'''


class BridgeScratch:
    def __init__(self, recorder, eval_id, *, profile=None):
        from virtuoso_bridge.transport.remote_roles import remote_host_roles_from_os
        from virtuoso_bridge.transport.tunnel import SSHClient
        roles = remote_host_roles_from_os(profile)
        self.runner = None
        self.store, self.eval_id, self.profile = recorder.store, eval_id, profile
        configuration = self.store.call('read', 'run_configuration', recorder.run_id).get('remote_scratch', {})
        self.root = configuration.get('root', '/tmp/gator-spectre-recording')
        self.remote = roles.spectre_host not in ('localhost', '127.0.0.1', '::1')
        if self.remote:
            if not SSHClient.is_running(profile):
                raise RuntimeError('Recording requires the existing Spectre-host bridge transport')
            self.client = SSHClient.from_env(profile=profile, keep_remote_files=True)
            self.runner = self.client.spectre_runner
            if self.runner is None:
                raise RuntimeError('Spectre-host transport unavailable')
            budgets = self.store.call('configuration')
            self.workspace = self.command('create', eval_id=eval_id,
                budget=configuration.get('budget', budgets['project_budget']),
                min_free=configuration.get('min_free', budgets['min_free']),
                reserve=configuration.get('reserve', budgets['temporary_reserve']))
            self.workspace.update(host='spectre', profile=profile)
            self.store.call('external_workspace', self.workspace)
        else:
            self.workspace = None

    def command(self, operation, **values):
        request = dict(root=self.root, operation=operation, **values)
        # Older Spectre hosts may only expose Python 2.7, as supported by Bridge.
        # Select by availability, never retry a failed mutation on another runtime.
        arguments = ' -c ' + shlex.quote(HELPER) + ' ' + shlex.quote(json.dumps(request))
        command = ('if command -v python3 >/dev/null 2>&1; then python3' + arguments +
                   '; else python' + arguments + '; fi')
        result = self.runner.run_command(command, timeout=30)
        if result.returncode != 0:
            raise RuntimeError('Spectre scratch operation failed: ' + result.stderr[-2048:])
        return json.loads(result.stdout)

    def simulator(self, work_dir, timeout):
        from virtuoso_bridge.spectre.runner import SpectreSimulator
        options = dict(work_dir=work_dir, timeout=timeout, output_format='psfascii', spectre_args=[],
                       keep_remote_files=True, profile=self.profile)
        if self.remote:
            options.update(remote=True, ssh_runner=self.runner, remote_work_dir=self.workspace['path'])
        return SpectreSimulator(**options)

    def cleanup(self, receipt):
        if self.workspace is None:
            return
        self.store.call('verify_receipt', receipt)
        values = {k: self.workspace[k] for k in ('path', 'token', 'eval_id')}
        self.command('finish', **values)
        self.store.call('workspace_finished', self.workspace['token'])
        self.command('delete', **values)
        self.store.call('external_cleaned', receipt, self.workspace['token'])
