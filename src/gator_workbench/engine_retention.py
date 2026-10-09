"""Raw-output retention of a run: after a result is durable, its simulator job folder is kept (moved into waveforms/,
listed in waveforms/index.json) or removed, by the run's retention policy and storage limit.

Moved from engine.py by the refactoring (docs/plan-refactoring.md): RunEngine inherits Retention; the method names
are unchanged.
"""
from __future__ import annotations

from pathlib import Path
import shutil

from .paths import directory_bytes
from .run_lock import iso
from .storage.atomic import read_json, write_json


class Retention:
    """RunEngine's raw-output retention: whether a path is inside the run's work folder, and what is kept or removed
    after each commit."""

    # ------------------------------------------------------------------ raw-output retention
    def _inside_work(self, path):
        try:
            resolved = Path(path).resolve()
            if self._work_resolved is None:              # work/, and the run's local scratch when it has one
                self._work_resolved = [self.layout.work.resolve()] + ([self._scratch.resolve()] if self._scratch else [])
            return any(root in resolved.parents for root in self._work_resolved) and not Path(path).is_symlink()
        except OSError:
            return False
    def _apply_retention(self, plan, role):
        """Acts only AFTER the result is durable, and only on registered paths inside work/."""
        index_path = self.layout.waveforms / 'index.json'
        if self._waveform_index is None:
            self._waveform_index = read_json(index_path, default=dict(entries={}))
        index = self._waveform_index                      # every change below is written at once, as before
        changed = False
        for item in plan:
            source, record = item['source'], item['record']
            try:
                if source and self._inside_work(source) and Path(source).exists():
                    if item['decision'].startswith('retained'):
                        target = self.layout.run_dir / item['target']
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.move(source, target)
                        index['entries'][item['job_id']] = dict(path=item['target'], status=item['decision'],
                                                                       evaluation_id=item['evaluation_id'],
                                                                       updated_utc=iso())
                        changed = True
                    else:
                        self._remember_host_folder(Path(source))
                        shutil.rmtree(source, ignore_errors=True)
                if self.config.output.waveform_retention != 'all':
                    # Registered temporaries only: the export package and the per-candidate journal are
                    # redundant once the result is durable in the raw tables.
                    export = record.get('netlist_path')
                    if export and self._inside_work(Path(export).parent):
                        shutil.rmtree(Path(export).parent, ignore_errors=True)
                    if item.get('journal') and self._inside_work(item['journal']):
                        Path(item['journal']).unlink(missing_ok=True)
            except OSError as exc:
                self._log_error('retention_failed', exc, evaluation_id=item['evaluation_id'])
        if role is not None and self.config.output.waveform_retention == 'best_and_failures':
            previous = self.previous_best_waveform
            current = plan[-1]['evaluation_id'] if plan else None
            if previous and previous != current:
                for key, entry in index['entries'].items():
                    if entry.get('evaluation_id', key) == previous and entry['status'] == 'retained_best':
                        self._remember_host_folder(self.layout.run_dir / entry['path'])
                        shutil.rmtree(self.layout.run_dir / entry['path'], ignore_errors=True)
                        entry.update(status='deleted_by_policy', updated_utc=iso(), reason='superseded by a better design')
                        changed = True
                self._event('waveform_retention_changed', evaluation_id=previous, status='deleted_by_policy')
            self.previous_best_waveform = current
        limit = self.config.output.waveform_storage_limit_bytes
        if limit is not None and changed:
            failures = sorted((v['updated_utc'], k) for k, v in index['entries'].items() if v['status'] == 'retained_failure')
            # Only failures may be deleted for space, so measure only while one is left: the folder walk grows with every
            # retained job and cost seconds per evaluation on the 9p mount (review of 2026-09-30).
            while failures and directory_bytes(self.layout.waveforms) > limit:
                _, key = failures.pop(0)
                self._remember_host_folder(self.layout.run_dir / index['entries'][key]['path'])   # before the copy goes (7.283)
                shutil.rmtree(self.layout.run_dir / index['entries'][key]['path'], ignore_errors=True)
                index['entries'][key].update(status='deleted_storage_limit', updated_utc=iso())
                self._event('waveform_retention_changed', evaluation_id=key, status='deleted_storage_limit')
        if changed:
            index['policy'] = dict(retention=self.config.output.waveform_retention, storage_limit_bytes=limit,
                                   cleanup='oldest retained failures first; the best design and all models/primary '
                                           'data are never removed automatically',
                                   note='simulator_jobs.retention_status is the decision at commit time; this index '
                                        'is the current state')
            write_json(index_path, index)
