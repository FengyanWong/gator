"""The tested CLI runtime: uncapped output, exact token counting and owned cancellation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

from ..paths import repo_root
from .catalog import GiB


class Cancelled(Exception):
    pass


def local_path(value):
    """Accept operator paths on Windows or their mounted equivalent on WSL."""
    value = str(value)
    if os.name != 'nt' and re.match(r'^[A-Za-z]:[\\/]', value):
        value = '/mnt/' + value[0].lower() + '/' + value[3:].replace('\\', '/')
    return Path(value).expanduser().resolve()


def windows_path(path):
    path = str(Path(path).resolve())
    if os.name == 'nt':
        return path
    return subprocess.check_output(['wslpath', '-w', path], text=True, timeout=10).strip()


def asset_root():
    """Use the original checkout's benchmark assets without changing or copying them."""
    if given := os.environ.get('GATOR_AGENT_ASSET_ROOT'):
        return local_path(given)
    root = repo_root()
    pointer = root / '.git'
    if pointer.is_file():
        value = pointer.read_text().strip().removeprefix('gitdir: ')
        gitdir = local_path(value) if re.match(r'^[A-Za-z]:', value) else (root / value).resolve()
        if gitdir.parent.name == 'worktrees' and gitdir.parent.parent.name == '.git':
            root = gitdir.parent.parent.parent
    return root / 'artifacts' / 'local' / 'nemotron-test'


def powershell():
    return shutil.which('powershell.exe') or shutil.which('powershell')


def host_supported():
    return platform.machine().lower() in ('amd64', 'x86_64') and bool(powershell())


def hardware(root):
    """Read free resources on the host that executes the Windows CUDA runtime."""
    errors, gpus = [], []
    ram_total = ram_free = None
    try:
        ps = powershell()
        if not ps:
            raise ValueError('Windows x64 / WSL with Windows PowerShell is required by this runtime recipe.')
        raw = subprocess.check_output([ps, '-NoProfile', '-NonInteractive', '-Command',
            '$m=Get-CimInstance Win32_OperatingSystem; @($m.TotalVisibleMemorySize,$m.FreePhysicalMemory) | ConvertTo-Json'],
            text=True, timeout=15, stderr=subprocess.DEVNULL)
        total, free = json.loads(raw)
        ram_total, ram_free = int(total) * 1024, int(free) * 1024
    except Exception:
        errors.append('Host RAM could not be read; compatibility cannot be confirmed.')
    try:
        smi = shutil.which('nvidia-smi.exe') or shutil.which('nvidia-smi')
        if not smi:
            raise ValueError('nvidia-smi is missing')
        raw = subprocess.check_output([smi, '--query-gpu=index,name,memory.total,memory.free,driver_version,compute_cap',
                                      '--format=csv,noheader,nounits'], text=True, timeout=15,
                                      stderr=subprocess.DEVNULL)
        for line in raw.strip().splitlines():
            index, name, total, free, driver, capability = [v.strip() for v in line.split(',')]
            gpus.append(dict(index=int(index), name=name, total=int(total)*1024**2, free=int(free)*1024**2,
                             driver=driver, capability=float(capability)))
    except Exception:
        errors.append('NVIDIA GPU, free VRAM, driver and compute capability could not be read.')
    existing = Path(root)
    while not existing.exists():
        existing = existing.parent
    try:
        disk = shutil.disk_usage(existing).free
    except OSError:
        disk = None
        errors.append('Free storage could not be read.')
    return dict(supported=host_supported(), ram_total=ram_total, ram_free=ram_free, gpus=gpus,
                disk_free=disk, errors=errors)


def compatibility(model, host, *, installed=False, reusable=False, runtime_ready=False):
    errors = list(host['errors'])
    if not host['supported']:
        errors.append('Automatic installation currently supports Windows x64 CUDA, including WSL interop.')
    eligible = [g for g in host['gpus'] if g['capability'] >= 7.5 and float(g['driver'].split('.')[0]) >= 551
                and g['free'] >= model.vram_gib * GiB]
    if not eligible:
        errors.append(f'Needs one CUDA GPU (compute capability 7.5+, driver 551+) with {model.vram_gib:g} GiB free VRAM.')
    if (host['ram_total'] or 0) < model.ram_gib * GiB or (host['ram_free'] or 0) < 6 * GiB:
        errors.append(f'Needs {model.ram_gib:g} GiB host RAM and 6 GiB available RAM.')
    # Archives + extracted runtime coexist during install; GGUF is streamed once.
    disk_needed = (0 if installed or reusable else model.size) + (0 if runtime_ready else 2 * GiB) + GiB
    if (host['disk_free'] or 0) < disk_needed:
        errors.append(f'Needs {disk_needed / GiB:.1f} GiB free storage, including installation workspace.')
    return dict(compatible=not errors, errors=errors, disk_needed=disk_needed,
                gpu_index=eligible[0]['index'] if eligible else None,
                note='Resource estimates include runtime headroom; Deploy verifies the actual load before enabling chat.')


class Runtime:
    def __init__(self, executable):
        self.executable = local_path(executable)

    def verify(self):
        if not self.executable.is_file() or not self.executable.with_name('llama-tokenize.exe').is_file():
            raise ValueError('The completion runtime and tokenizer are both required.')
        raw = subprocess.check_output([str(self.executable), '--version'], stderr=subprocess.STDOUT,
                                      text=True, timeout=20)
        if '11669' not in raw or '620d2225c' not in raw:
            raise ValueError('This model recipe requires the tested llama.cpp b11669 (620d2225c) runtime.')
        help_text = subprocess.check_output([str(self.executable), '--help'], stderr=subprocess.STDOUT,
                                            text=True, timeout=20)
        if not all(flag in help_text for flag in ('--context-shift', '--keep', '--no-conversation')):
            raise ValueError('Runtime lacks the required uncapped context-continuation options.')
        return raw.strip()

    def execute(self, arguments, folder, cancel, *, tokenizer=False):
        """Stream to owned files. There is no generation timeout or output-token cap."""
        folder.mkdir(parents=True, exist_ok=True)
        exe = self.executable.with_name('llama-tokenize.exe') if tokenizer else self.executable
        out, err = folder / 'stdout.txt', folder / 'stderr.txt'
        lease, stop = folder / 'lease', folder / 'cancel'
        lease.touch()
        spec = dict(executable=windows_path(exe), arguments=subprocess.list2cmdline(arguments),
                    cwd=windows_path(exe.parent), stdout=windows_path(out), stderr=windows_path(err),
                    lease=windows_path(lease), cancel=windows_path(stop))
        spec_path = folder / 'process.json'
        spec_path.write_text(json.dumps(spec), encoding='utf-8')
        script = Path(__file__).with_name('windows_runner.ps1')
        # All arguments come from our fixed recipe; prompts travel in files, never in shell code.
        process = subprocess.Popen([powershell(), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                                    '-File', windows_path(script), '-Spec', windows_path(spec_path)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            while process.poll() is None:
                if cancel.wait(.1):
                    stop.touch()
                lease.touch()
            wrapper_error = process.communicate()[1].decode('utf-8', errors='replace')
        finally:
            if process.poll() is None:
                stop.touch()  # the native supervisor owns and terminates its exact child
        if cancel.is_set():
            raise Cancelled()
        if process.returncode:
            detail = err.read_text(encoding='utf-8', errors='replace')[-1500:] if err.exists() else wrapper_error[-1500:]
            raise ValueError(f'Local runtime exited with code {process.returncode}: {detail}')
        return out.read_text(encoding='utf-8', errors='replace')

    def generate(self, model, path, prompt, folder, cancel, gpu_index):
        prompt_file = folder / 'prompt.txt'
        folder.mkdir(parents=True, exist_ok=True)
        prompt_file.write_text(prompt, encoding='utf-8', newline='\n')
        raw_count = self.execute(['-m', windows_path(path), '-f', windows_path(prompt_file), '--ids'],
                                 folder / 'tokenize', cancel, tokenizer=True)
        tokens = json.loads(raw_count.strip())
        if not isinstance(tokens, list) or len(tokens) > 6144:
            raise ValueError('The prompt exceeds the 6,144-token input window. Start a new conversation or shorten it. '
                             'The 8,192-token runtime window keeps space for shifting; answers remain uncapped.')
        args = ['-m', windows_path(path), '-f', windows_path(prompt_file), '-ngl', '999', '-c', '8192',
                '-b', '512', '-ub', '128', '-n', '-1', '--keep', '-1', '--context-shift',
                '-t', str(min(16, os.cpu_count() or 4)), '--flash-attn', 'on', '--fit', 'off',
                '--split-mode', 'none', '--main-gpu', str(gpu_index), '--no-conversation', '--simple-io',
                '--no-display-prompt', '--color', 'off', '--temp', '1.0', '--top-p', '0.95',
                '--top-k', '0', '--min-p', '0', '--seed', '42', '--no-escape']
        raw = self.execute(args, folder / 'inference', cancel)
        if '[end of text]' not in raw:
            raise ValueError('The runtime stopped without its normal end-of-text marker; no proposal is applicable.')
        return raw.split('[end of text]')[0].rsplit('</think>', 1)[-1].rsplit('<channel|>', 1)[-1].strip()


def prompt_text(model, messages):
    # Role and special-token delimiters in content are untrusted text, not a new model turn.
    def safe(text):
        return re.sub(r'<\|[^\n<>]{1,80}[|>]|</?think>|<turn\|>|<channel\|>|<start_of_turn>|<end_of_turn>|<bos>|<eos>', '[delimiter]', text)
    if model.template == 'chatml':
        return ''.join(f'<|im_start|>{role}\n{safe(content)}<|im_end|>\n' for role, content in messages) + \
            '<|im_start|>assistant\n<think>\n'
    return '<|turn>system\n<|think|>\n<turn|>\n' + ''.join(
        f'<|turn>{"model" if role == "assistant" else "user"}\n{safe(content)}<turn|>\n'
        for role, content in messages) + '<|turn>model\n'
