"""A run binds its own unchanging copy of the bridge's settings file (record 7.306). The adapter checks the file it bound
at every call and ends the run when it changed; on 2026-10-10 another session added a second Virtuoso session's keys to
the shared file and a run of a queue ended in the middle of a write. The copy keeps the adapter's check and takes the
shared file out of a running run's way."""
import stat

from analog_optimizer.backends.common import file_digest

from gator_workbench import paths, tasks

FIRST = 'VB_REMOTE_HOST=simhost\nVB_REMOTE_USER=someone\nVB_LOCAL_PORT=65221\n'
SECOND_SESSION = '# a second Virtuoso session\nVB_REMOTE_HOST_s2=simhost\nVB_LOCAL_PORT_s2=65222\n'


def test_a_settings_file_changed_during_a_run_does_not_reach_the_copy_the_run_bound(tmp_path):
    shared = tmp_path / '.env'
    shared.write_text(FIRST)
    bound = paths.bridge_env_snapshot(shared)
    assert bound.read_text() == FIRST and bound.parent == paths.bridge_state_dir().resolve() / 'env-snapshots'
    assert stat.S_IMODE(bound.stat().st_mode) == 0o600
    at_attach = file_digest(bound)                       # what the adapter keeps when it attaches (BridgeConfig.env_file)
    shared.write_text(FIRST + SECOND_SESSION)            # another session adds its keys while the run works
    assert file_digest(bound) == at_attach               # the adapter's check at the next call: unchanged, the run goes on
    assert file_digest(shared) != at_attach              # bound to the shared file it would have ended here
    later = paths.bridge_env_snapshot(shared)            # a run started afterwards takes the file as it is then
    assert later != bound and later.read_text() == FIRST + SECOND_SESSION and bound.read_text() == FIRST
    shared.unlink()                                      # even a removed file leaves the bound copy as it was
    assert file_digest(bound) == at_attach


def test_the_same_settings_give_the_same_copy_and_a_damaged_copy_is_written_again(tmp_path):
    shared = tmp_path / '.env'
    shared.write_text(FIRST)
    first = paths.bridge_env_snapshot(shared)
    assert paths.bridge_env_snapshot(shared) == first and len(list(first.parent.iterdir())) == 1
    first.chmod(0o600)
    first.write_text('damaged')
    assert paths.bridge_env_snapshot(shared) == first and first.read_text() == FIRST


def test_old_copies_go_when_a_new_one_is_written_and_a_file_that_cannot_be_read_is_named_as_it_was(tmp_path):
    import os
    import time
    shared = tmp_path / '.env'
    shared.write_text(FIRST)
    old = paths.bridge_env_snapshot(shared)
    assert stat.S_IMODE(old.parent.stat().st_mode) == 0o700
    long_ago = time.time() - 31 * 86400
    os.utime(old, (long_ago, long_ago))
    (old.parent / 'notes.txt').write_text('not a copy')
    shared.write_text(FIRST + SECOND_SESSION)
    new = paths.bridge_env_snapshot(shared)
    assert new.exists() and not old.exists() and (old.parent / 'notes.txt').exists()      # only month-old copies go
    missing = tmp_path / 'nowhere' / '.env'
    assert paths.bridge_env_snapshot(missing) == missing.resolve()


def test_a_real_tasks_bridge_configuration_names_the_copy_not_the_shared_file(tmp_path):
    shared, receipt = tmp_path / '.env', tmp_path / 'creation.json'
    shared.write_text(FIRST)
    receipt.write_text('{}')
    config = tasks.bridge_config_of(dict(env_file=str(shared), library='LIB', creation_receipt=str(receipt), model_file='/pdk/model.scs', profile=None))
    assert config.env_file != shared.resolve() and config.env_file.parent.name == 'env-snapshots' and config.env_file.read_text() == FIRST
    assert config.profile is None and config.library == 'LIB'
