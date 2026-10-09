"""Simulation workspaces and their retention: created, finished, kept as an attachment (initial, best, a few
failures) within the byte budget, cleaned up, and space reserved before each evaluation.

One of the parts ExperimentStore (store.py) is made of since 2026-10-09 (plan-refactoring E5); its methods run on
the store's writer thread, inside the transaction of the operation that called them."""
from pathlib import Path
from uuid import uuid4

from .codec import pack, unpack
from .space import (SpaceExhausted, checked_workspace, create_workspace, disk_bytes, fsync_directory,
                    remove_workspace, require_space)


class WorkspaceRecords:
    def _op_retention(self, receipt):
        row = self._evaluation(receipt['eval_id'])
        if row['result'] is None or receipt != self._receipt(row):
            raise ValueError('Retention requires durable acknowledgement')
        summary = unpack(self.db.execute('SELECT summary FROM runs WHERE id=?', (row['run_id'],)).fetchone()[0])
        role = None
        if summary['initial'] and summary['initial']['eval_id'] == row['id']:
            role = 'initial'
        elif row['result']['status'] != 'ok' or row['result'].get('environment', {}).get('evaluation_valid') is False:
            role = 'failure'
        else:
            best = summary['best_feasible'] or summary.get('best_nominal_feasible') or summary['best_infeasible']
            if best and best['eval_id'] == row['id']:
                role = 'best'
        return dict(role=role, error_class=row['result'].get('error_class'))

    def _op_external_workspace(self, data):
        self._evaluation(data['eval_id'])
        self.db.execute('INSERT INTO workspaces VALUES(?,?,?,0)', (data['token'], data['eval_id'], pack(data)))

    def _op_external_cleaned(self, receipt, token):
        self._op_verify_receipt(receipt)
        row = self.db.execute('SELECT * FROM workspaces WHERE id=?', (token,)).fetchone()
        if row is None or row['eval_id'] != receipt['eval_id'] or not unpack(row['data'])['finished']:
            raise ValueError('Workspace acknowledgement mismatch')
        self.db.execute('UPDATE workspaces SET cleaned=1 WHERE id=?', (token,))

    def _op_workspace(self, eval_id):
        row = self._evaluation(eval_id)
        if row['result'] is not None:
            raise ValueError('Evaluation already ended')
        data = create_workspace(self.root / 'temporary', eval_id)
        self.db.execute('INSERT INTO workspaces VALUES(?,?,?,0)', (data['token'], eval_id, pack(data)))
        return data

    def _op_begin_workspace(self, run_id, task_id, graph_id, request, eval_id=None):
        """One pre-dispatch transaction for the request and its owned workspace."""
        eval_id = self._op_begin(run_id, task_id, graph_id, request, eval_id=eval_id)
        for row in self.db.execute('SELECT data FROM workspaces WHERE eval_id=? AND cleaned=0', (eval_id,)):
            data = unpack(row['data'])
            if data['host'] == 'local':
                return data
        return self._op_workspace(eval_id)

    def _op_workspace_finished(self, token):
        row = self.db.execute('SELECT data FROM workspaces WHERE id=?', (token,)).fetchone()
        data = unpack(row[0])
        data['finished'] = True
        self.db.execute('UPDATE workspaces SET data=? WHERE id=?', (pack(data), token))

    def _op_finalize_workspace(self, receipt, token):
        """Separate from result commit: only an already durable result permits cleanup.

        Metadata changes share one transaction; file deletion still requires the
        existing ownership and live-process checks. A failed commit can leave
        stale cleanup metadata, never an uncommitted numerical result deleted.
        """
        self._op_verify_receipt(receipt)
        workspace = self.db.execute('SELECT * FROM workspaces WHERE id=?', (token,)).fetchone()
        if workspace is None or workspace['eval_id'] != receipt['eval_id']:
            raise ValueError('Workspace/evaluation mismatch')
        if workspace['cleaned']:
            return
        data = unpack(workspace['data'])
        if data['host'] != 'local':
            raise ValueError('Local finalization cannot remove a remote workspace')
        self._op_workspace_finished(token)
        retention = self._op_retention(receipt)
        if retention['role']:
            self._op_attach(receipt, token, retention['role'], retention['error_class'])
        self._op_cleanup(receipt, token)

    def _op_cleanup(self, receipt, token):
        row = self._evaluation(receipt['eval_id'])
        if row['result'] is None or receipt != self._receipt(row):
            raise ValueError('Cleanup requires a matching durable result acknowledgement')
        item = self.db.execute('SELECT * FROM workspaces WHERE id=?', (token,)).fetchone()
        if item is None or item['eval_id'] != row['id']:
            raise ValueError('Workspace belongs to another evaluation')
        remove_workspace(unpack(item['data']))
        self.db.execute('UPDATE workspaces SET cleaned=1 WHERE id=?', (token,))

    def _op_usage(self):
        return dict(database=disk_bytes(self.path),
                    journal=sum(disk_bytes(Path(str(self.path) + suffix)) for suffix in ('-wal', '-shm', '-journal')),
                    attachments=disk_bytes(self.root / 'attachments'), checkpoints=disk_bytes(self.root / 'checkpoints'),
                    temporary=disk_bytes(self.root / 'temporary'), total=disk_bytes(self.root))

    def _evict(self, item):
        path = Path(item['path'])
        if path.parent != self.root / 'attachments' or path.is_symlink():
            raise ValueError('Attachment path escaped its dedicated directory')
        path.unlink(missing_ok=True)
        fsync_directory(path.parent)
        self.db.execute("UPDATE attachments SET status='evicted',reason='budget_or_replaced' WHERE id=?", (item['id'],))

    def _op_preflight(self, extra=0):
        in_flight = self.db.execute("SELECT count(*) FROM evaluations WHERE result IS NULL").fetchone()[0]
        reserved = (in_flight + 1) * (self.config.temporary_reserve + self.config.result_reserve) + extra
        try:
            require_space(self.root, self.config, reserved)
        except SpaceExhausted:
            for item in self.db.execute("SELECT * FROM attachments WHERE status='retained'").fetchall():
                self._evict(item)
                # Preflight runs before any core mutation. Filesystem deletion
                # cannot roll back: preserve its metadata even if capacity is
                # still insufficient and this operation must raise below.
                self.db.commit()
                try:
                    require_space(self.root, self.config, reserved)
                    return
                except SpaceExhausted:
                    pass
            require_space(self.root, self.config, reserved)

    def _op_attach(self, receipt, token, role, error_type=None):
        import tarfile
        row = self._evaluation(receipt['eval_id'])
        if row['result'] is None or receipt != self._receipt(row):
            raise ValueError('Attachment retention requires durable acknowledgement')
        if role not in ('initial', 'best', 'failure'):
            raise ValueError('Unknown attachment retention role')
        workspace_row = self.db.execute('SELECT * FROM workspaces WHERE id=?', (token,)).fetchone()
        if workspace_row is None or workspace_row['eval_id'] != row['id']:
            raise ValueError('Workspace/evaluation mismatch')
        workspace = unpack(workspace_row['data'])
        path = checked_workspace(workspace)
        size = disk_bytes(path)
        existing = self.db.execute("SELECT * FROM attachments WHERE run_id=? AND status='retained'", (row['run_id'],)).fetchall()
        same = [a for a in existing if a['role'] == role]
        reason = 'workspace_missing_after_cleanup_or_recovery' if not path.exists() else None
        if role == 'initial' and same:
            reason = 'initial_already_retained'
        if role == 'failure' and (len(same) >= 2 or any(a['error_type'] == error_type for a in same)):
            reason = 'representative_failure_limit'
        # Conservative bound for tar headers; compressed bytes checked again below.
        reserve = size + 10240 + sum(1024 for _ in path.rglob('*'))
        reclaim = sum(a['bytes'] for a in same) if role == 'best' else 0
        if reserve + sum(a['bytes'] for a in existing) - reclaim > self.config.attachment_budget:
            reason = 'attachment_byte_budget'
        key = uuid4().hex
        destination = self.root / 'attachments' / (key + '.tar.gz')
        if reason is None:
            try:
                self._op_preflight(extra=reserve)
            except SpaceExhausted:
                reason = 'space_reserve'
        if reason is None:
            temporary = destination.with_suffix('.tmp')
            with tarfile.open(temporary, 'w:gz') as archive:
                archive.add(path, arcname='job')
            with temporary.open('rb') as stream:
                import os
                os.fsync(stream.fileno())
            if temporary.stat().st_size > self.config.attachment_budget:
                temporary.unlink()
                reason = 'compressed_attachment_byte_budget'
            else:
                temporary.replace(destination)
                fsync_directory(destination.parent)
                if role == 'best':
                    for item in same:
                        self._evict(item)
        self.db.execute('INSERT INTO attachments VALUES(?,?,?,?,?,?,?,?,?)',
                        (key, row['run_id'], row['id'], role, error_type,
                         str(destination) if reason is None else None,
                         destination.stat().st_size if reason is None else 0,
                         'retained' if reason is None else 'omitted', reason))
        return key
