"""The simulator host's side of a run (record 7.282): the job folders a run removes on the simulator host as its raw
outputs go, and Virtuoso's memory said at the run's start and end.

Moved from engine.py by the refactoring (docs/plan-refactoring.md): RunEngine inherits HostMaintenance; the method
names are unchanged.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shlex

from .storage.atomic import read_dict


# A Spectre job's folder on the simulator host, as the bridge names it (record 7.282): nothing else is ever deleted there.
HOST_JOB_FOLDER = re.compile(r'^/tmp/virtuoso_bridge_[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/virtuoso_bridge_spectre/[0-9a-f]{6,64}$')
HOST_CLEANUP_CHUNK = 200                            # folders per rm command


class HostMaintenance:
    """RunEngine's methods for the simulator host: the runner that reaches it, the job folders to remove there, their
    removal in chunks, and Virtuoso's memory."""

    # ------------------------------------------------------------------ the simulator host (record 7.282)
    def _host_runner(self):
        """run(script) on the simulator host through the bridge's own SSH runner (model_library.host_runner), or None: a
        MOCK or ngspice run, output.keep_simulator_host_folders, or a host that cannot be reached (said in errors.jsonl)."""
        if self._host_run is not False:
            return self._host_run
        self._host_run = None
        key = str(getattr(self.task, 'task_key', '') or '')
        if self.task.mock or not key.startswith('real:') or self.config.output.keep_simulator_host_folders:
            return None
        try:
            from .model_library import host_runner  # lazy: in the try: a failure of the import is handled with the rest
            # lazy: in the try: a failure of the import is handled with the rest
            from .tasks import generated_bridge_config
            self._host_run = host_runner(generated_bridge_config(key[len('real:'):], self.config.run.connection_profile_id)[0])
        except Exception as exc:
            self._log_error('simulator_host_unreachable', exc)
        return self._host_run
    def _remember_host_folder(self, job_dir):
        """The host folder of a design whose raw output this run drops: its measurements.json names the result folder
        (results_on_host, written by the Maestro measurement). Only a folder of the bridge's own form is kept for removal."""
        if self.task.mock or self.config.output.keep_simulator_host_folders:
            return
        raw = read_dict(Path(job_dir) / 'measurements.json').get('results_on_host')
        folder = os.path.dirname(raw) if isinstance(raw, str) else ''
        if HOST_JOB_FOLDER.match(folder) and '/../' not in folder and folder not in self._host_folders:
            self._host_folders.append(folder)
    def _clean_host(self):
        """Remove the remembered folders from the simulator host, HOST_CLEANUP_CHUNK per command: the host kept every job's
        folder (58,000 by the morning of 2026-10-08, when its Virtuoso had grown to 10.5 GB and the queue stopped). Never
        a pattern: each folder is named, and each one was named by this run's own measurement. A failure is said and the
        folders are tried again at the next save point."""
        folders = list(self._host_folders)
        if not folders or self._host_runner() is None:
            return
        removed = 0
        try:
            for start in range(0, len(folders), HOST_CLEANUP_CHUNK):
                chunk = folders[start:start + HOST_CLEANUP_CHUNK]
                self._host_run('rm -rf -- ' + ' '.join(shlex.quote(folder) for folder in chunk) + '\n')
                removed += len(chunk)
                self._host_folders = [f for f in self._host_folders if f not in set(chunk)]
        except Exception as exc:
            self._log_error('simulator_host_cleanup_failed', exc)
        if removed:
            self._event('simulator_host_folders_removed', count=removed, left=len(self._host_folders))
    def _log_virtuoso_memory(self, when):
        """Virtuoso's memory on the simulator host at the run's start and end (record 7.282): it had grown to 10.5 GB over
        a night of runs. Said in events.jsonl as `virtuoso_memory`; nothing is changed on the host."""
        if self._host_runner() is None:
            return
        try:
            listing = self._host_run('ps -u "$(id -un)" -o pid,rss,comm\n')      # its header line is no process
            processes = []
            for line in (listing or '').splitlines():
                fields = line.split(None, 2)
                if len(fields) == 3 and 'virtuoso' in fields[2].lower() and fields[0].isdigit() and fields[1].isdigit():
                    processes.append(dict(pid=int(fields[0]), rss_mb=round(int(fields[1]) / 1024, 1), name=fields[2].strip()))
            self._event('virtuoso_memory', when=when, processes=processes, total_mb=round(sum(p['rss_mb'] for p in processes), 1))
        except Exception as exc:
            self._log_error('virtuoso_memory_unread', exc)
