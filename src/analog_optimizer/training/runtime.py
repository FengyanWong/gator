"""Shared CLI recording lifecycle, including initialization and report failures."""
from concurrent.futures import Future
import json
from pathlib import Path
import sys
import threading

from .workers import WorkerLimits


def add_runtime_arguments(parser):
    parser.add_argument('--recording-root', type=Path, help='SQLite records on a local Linux filesystem')
    parser.add_argument('--recording-config', type=Path)
    parser.add_argument('--worker-timeout-seconds', type=float, default=300,
                        help='Parent deadline per worker operation, including communication')
    parser.add_argument('--shutdown-timeout-seconds', type=float, default=10)
    parser.add_argument('--history-limit', type=int, default=100,
                        help='Recent in-memory entries with recording enabled; full history stays in SQLite')


def limits_from_args(args):
    return WorkerLimits(args.worker_timeout_seconds, args.shutdown_timeout_seconds, args.history_limit)


def bounded_call(function, seconds):
    future = Future()
    def execute():
        try:
            future.set_result(function())
        except BaseException as exc:
            future.set_exception(exc)
    threading.Thread(target=execute, daemon=True).start()
    return future.result(timeout=seconds)


def write_report_preserving_error(path, report):
    """A report failure during unwinding must not replace the original error."""
    from analog_optimizer.envs.sizing import write_record
    original = sys.exc_info()[1]
    try:
        write_record(path, report)
    except BaseException as exc:
        if original is None:
            raise
        report.setdefault('cleanup_errors', []).append(dict(operation='write_report',
            type=type(exc).__name__, message=str(exc)))
        print(f'write_report: {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)


class RunResources:
    def __init__(self, report, report_path, *, recording_root=None, recording_config=None,
                 cleanup_seconds=10, summary_export=None):
        self.report, self.report_path = report, Path(report_path)
        self.root, self.config_path = recording_root, recording_config
        self.cleanup_seconds, self.summary_export = cleanup_seconds, summary_export
        self.manager = self.store = self.run_id = self.recorder = self.checkpoints = self.updates = None

    def __enter__(self):
        return self

    def start(self, project_root, configuration, *, project_files=(), templates=None, assets=None):
        if self.root is None:
            return
        from analog_optimizer.recording import start_service, RecordingConfig, RunRecorder, UpdateAggregator
        from analog_optimizer.recording.checkpoint import CheckpointManager
        from analog_optimizer.recording.setup import create_run
        config = RecordingConfig(**(json.loads(self.config_path.read_text()) if self.config_path else {}))
        self.manager, self.store = start_service(self.root, config)
        configuration = dict(configuration)
        for name, (kind, value) in (assets or {}).items():
            configuration[name] = self.store.call('asset', kind, value)
        self.run_id = create_run(self.store, project_root, configuration,
                                 project_files=project_files, templates=templates)
        self.report.update(recording_run_id=self.run_id, recording_root=str(self.root))
        self.recorder = RunRecorder(self.store, self.run_id)
        self.checkpoints = CheckpointManager(self.store, self.run_id, self.root, interval=config.checkpoint_interval)
        self.updates = UpdateAggregator(self.store, self.run_id, interval=config.update_interval)

    def __exit__(self, kind, original, trace):
        from analog_optimizer.envs.sizing import write_record
        if original is not None:
            self.report.update(passed=False, exception_type=kind.__name__, error=str(original))
            if 'completed' in self.report:
                self.report['completed'] = False
            if getattr(original, 'cleanup_error', None):
                self.report.setdefault('cleanup_errors', []).append(dict(operation='environment_cleanup',
                    message=original.cleanup_error))
        errors = []
        def attempt(label, function, *, bounded=False):
            try:
                return bounded_call(function, self.cleanup_seconds) if bounded else function()
            except BaseException as exc:
                errors.append(exc)
                self.report.setdefault('cleanup_errors', []).append(dict(operation=label, type=type(exc).__name__, message=str(exc)))
                self.report['passed'] = False
                if 'completed' in self.report:
                    self.report['completed'] = False
                print(f'{label}: {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
        if self.updates is not None:
            attempt('flush_updates', self.updates.flush, bounded=True)
        if self.store is not None:
            if self.run_id is not None:
                attempt('end_run', lambda: self.store.call('end_run', self.run_id), bounded=True)
            attempt('close_writer', self.store.close, bounded=True)
        if self.manager is not None:
            attempt('shutdown_manager', self.manager.shutdown, bounded=True)
        if self.run_id is not None and self.summary_export is not None:
            attempt('export_summary', lambda: self.summary_export(self.root, self.run_id, self.report))
        attempt('write_report', lambda: write_record(self.report_path, self.report))
        if original is None and errors:
            raise errors[0]
        return False
