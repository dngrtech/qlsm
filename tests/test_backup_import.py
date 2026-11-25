import errno
import io
import json
import os
import zipfile

import pytest
from ui import db
from ui.models import AddonState, Host, QLInstance
from ui.backup_crypto import encrypt_archive
from ui.task_logic.backup_export import build_backup_zip_bytes
from ui.task_logic.backup_files import backup_file_trees
from ui.task_logic.backup_import import _swap_tree as real_swap_tree
from ui.task_logic.backup_import import restore_backup_archive, BackupRestoreError, BACKUP_SNAPSHOTS_DIR


@pytest.fixture
def app_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'VERSION').write_text('1.0.0')
    (tmp_path / 'terraform' / 'ssh-keys').mkdir(parents=True)
    (tmp_path / 'terraform' / 'ssh-keys' / 'old_key').write_text('OLD KEY')
    (tmp_path / 'configs' / 'presets' / '_builtin' / 'default').mkdir(parents=True)
    (tmp_path / 'configs' / 'presets' / '_builtin' / 'default' / 'server.cfg').write_text('shipped with app')
    return tmp_path


def _make_backup_with_host(app, app_root, password=None):
    with app.app_context():
        db.session.add(Host(name='original-host', provider='vultr'))
        db.session.commit()
        zip_bytes = build_backup_zip_bytes()
    return encrypt_archive(zip_bytes, password)


def _reject_crossing_ssh_mount(monkeypatch, app_root):
    mount_root = os.path.realpath(app_root / 'terraform' / 'ssh-keys')
    real_rename = os.rename

    def guarded_rename(source, target):
        source_path = os.path.realpath(source)
        target_path = os.path.realpath(target)
        source_inside = os.path.commonpath((mount_root, source_path)) == mount_root
        target_inside = os.path.commonpath((mount_root, target_path)) == mount_root
        if source_inside != target_inside:
            raise OSError(errno.EXDEV, 'Invalid cross-device link', source, target)
        return real_rename(source, target)

    monkeypatch.setattr('ui.task_logic.backup_import.os.rename', guarded_rename)


def _managed_tree_contents(app_root):
    contents = {}
    for _prefix, root, _skip in backup_file_trees():
        root_path = app_root / root
        for directory, _dirs, files in os.walk(root_path):
            for filename in files:
                path = os.path.join(directory, filename)
                with open(path, 'rb') as file:
                    contents[os.path.relpath(path, app_root)] = file.read()
    return contents


class TestRestoreBackupArchive:
    def test_wipes_and_reloads_database(self, app, app_root):
        blob = _make_backup_with_host(app, app_root)
        with app.app_context():
            db.session.query(Host).delete()
            db.session.add(Host(name='pre-existing-host-to-be-wiped', provider='standalone'))
            db.session.commit()

            summary = restore_backup_archive(blob, None)

            names = {h.name for h in Host.query.all()}
            assert names == {'original-host'}
            assert summary['qlsm_version'] == '1.0.0'

    def test_round_trip_omits_orphan_addon_scopes_without_mutating_source(self, app, app_root):
        from ui.addons.registry import get_addon

        valid_states = [
            (40, 'global', 0, True, {'label': 'global', 'nested': {'keep': [1, None]}}),
            (41, 'host', 10, False, {'label': 'host'}),
            (42, 'instance', 20, True, {'label': 'instance'}),
        ]
        orphan_states = [
            (43, 'host', 20, True, {'label': 'removed-host'}),
            (44, 'instance', 10, False, {'label': 'removed-instance'}),
        ]
        with app.app_context():
            db.session.add(Host(id=10, name='retained-host', provider='standalone'))
            db.session.flush()
            db.session.add(QLInstance(id=20, name='retained-instance', hostname='server',
                                      host_id=10, port=27960))
            for row_id, scope, scope_id, enabled, settings in valid_states + orphan_states:
                db.session.add(AddonState(
                    id=row_id, addon_id='uninstalled-addon', scope=scope, scope_id=scope_id,
                    enabled=enabled, settings_json=json.dumps(settings)))
            db.session.commit()
            assert get_addon('uninstalled-addon') is None
            state_query = db.select(AddonState.__table__).order_by(AddonState.id)
            source_rows = db.session.execute(state_query).all()

            blob = encrypt_archive(build_backup_zip_bytes(), None)

            # Export may omit stale scopes, but must leave every source row,
            # including its raw settings and timestamps, untouched.
            assert db.session.execute(state_query).all() == source_rows
            db.session.remove()
            summary = restore_backup_archive(blob, None)

            assert summary['addon_state_restored'] is True
            assert Host.query.one().id == 10
            assert QLInstance.query.one().id == 20
            restored = AddonState.query.order_by(AddonState.id).all()
            assert [(row.id, row.scope, row.scope_id, row.enabled, row.settings)
                    for row in restored] == valid_states
            assert all(row.addon_id == 'uninstalled-addon' for row in restored)

    def test_restores_file_trees(self, app, app_root):
        (app_root / 'configs' / 'presets' / 'custom').mkdir(parents=True)
        (app_root / 'configs' / 'presets' / 'custom' / 'server.cfg').write_text('custom preset')
        with app.app_context():
            db.session.add(Host(name='h', provider='vultr'))
            db.session.commit()
            zip_bytes = build_backup_zip_bytes()
        blob = encrypt_archive(zip_bytes, None)

        # Simulate a different on-disk state before restoring.
        (app_root / 'terraform' / 'ssh-keys' / 'old_key').unlink()
        (app_root / 'terraform' / 'ssh-keys' / 'unexpected_leftover').write_text('should be gone after restore')

        with app.app_context():
            restore_backup_archive(blob, None)

        assert (app_root / 'configs' / 'presets' / 'custom' / 'server.cfg').read_text() == 'custom preset'
        assert not (app_root / 'terraform' / 'ssh-keys' / 'unexpected_leftover').exists()
        # The app-shipped builtin preset folder must be untouched by the swap.
        assert (app_root / 'configs' / 'presets' / '_builtin' / 'default' / 'server.cfg').exists()

    def test_restores_across_managed_tree_filesystem_boundary(self, app, app_root, monkeypatch):
        blob = _make_backup_with_host(app, app_root)
        ssh_keys = app_root / 'terraform' / 'ssh-keys'
        (ssh_keys / 'old_key').unlink()
        (ssh_keys / 'unexpected_leftover').write_text('remove me')
        _reject_crossing_ssh_mount(monkeypatch, app_root)

        with app.app_context():
            restore_backup_archive(blob, None)

        assert (ssh_keys / 'old_key').read_text() == 'OLD KEY'
        assert not (ssh_keys / 'unexpected_leftover').exists()
        assert not list(ssh_keys.glob('.qlsm-restore-*'))

    def test_swapped_out_file_child_is_cleaned_up_after_success(self, app, app_root):
        """terraform/ssh-keys has flat *files* as direct children (unlike
        configs/presets, whose direct children are subdirectories). A
        successful restore must reclaim the swapped-out old file, not
        just a swapped-out old directory."""
        blob = _make_backup_with_host(app, app_root)
        # Not part of the backup being restored, so the swap moves it
        # aside as a *file* rather than restaging it from the archive.
        (app_root / 'terraform' / 'ssh-keys' / 'second_key').write_text('SECOND KEY')

        with app.app_context():
            restore_backup_archive(blob, None)

        leftovers = [
            name for name in os.listdir(app_root / 'terraform')
            if name.startswith('.qlsm-restore-old-')
        ]
        assert leftovers == []

    def test_wrong_password_raises_and_touches_nothing(self, app, app_root):
        blob = _make_backup_with_host(app, app_root, password='correct-pw')
        with app.app_context():
            db.session.query(Host).delete()
            db.session.add(Host(name='untouched', provider='standalone'))
            db.session.commit()

            with pytest.raises(BackupRestoreError):
                restore_backup_archive(blob, 'wrong-pw')

            assert [h.name for h in Host.query.all()] == ['untouched']

    def test_corrupted_archive_raises(self, app, app_root):
        with app.app_context():
            with pytest.raises(BackupRestoreError):
                restore_backup_archive(b'not a real backup', None)

    def test_writes_a_pre_restore_safety_snapshot(self, app, app_root):
        blob = _make_backup_with_host(app, app_root)
        with app.app_context():
            restore_backup_archive(blob, None)
        snapshots = os.listdir(BACKUP_SNAPSHOTS_DIR)
        assert len(snapshots) == 1
        assert snapshots[0].endswith('.qlsmbak')

    def test_safety_snapshot_is_owner_only(self, app, app_root):
        """backup_snapshots/ holds plaintext-equivalent dumps of every
        secret the instance has (SSH keys, API keys, credentials) — the
        directory and file must not be group/world-readable."""
        blob = _make_backup_with_host(app, app_root)
        with app.app_context():
            restore_backup_archive(blob, None)
        dir_mode = os.stat(BACKUP_SNAPSHOTS_DIR).st_mode & 0o777
        assert dir_mode == 0o700
        snapshot_name = os.listdir(BACKUP_SNAPSHOTS_DIR)[0]
        file_mode = os.stat(os.path.join(BACKUP_SNAPSHOTS_DIR, snapshot_name)).st_mode & 0o777
        assert file_mode == 0o600

    @pytest.mark.parametrize('failed_step', ['commit', 'filesystem-swap'])
    def test_failure_rolls_back_addon_state_and_files(self, app, app_root, monkeypatch, failed_step):
        ssh_key = app_root / 'terraform' / 'ssh-keys' / 'old_key'
        with app.app_context():
            row = AddonState(addon_id='custom-provider', scope='global', enabled=True,
                             settings_json='{"setting": "archived"}')
            db.session.add(row)
            db.session.commit()
            blob = encrypt_archive(build_backup_zip_bytes(), None)
            row.enabled = False
            row.settings_json = '{"setting": "local"}'
            db.session.commit()
        ssh_key.write_text('LOCAL KEY')

        def fail_with_replacement_pending():
            row = AddonState.query.one()
            assert row.enabled is True
            assert row.settings == {'setting': 'archived'}
            assert ssh_key.read_text() == 'OLD KEY'
            raise RuntimeError('simulated failure with database and filesystem changes pending')

        if failed_step == 'commit':
            monkeypatch.setattr(db.session, 'commit', fail_with_replacement_pending)
        else:
            def fail_last_tree_swap(root, staged_dir, skip):
                if os.path.abspath(root) == str(app_root / 'data' / 'addon-packages'):
                    fail_with_replacement_pending()
                return real_swap_tree(root, staged_dir, skip)

            monkeypatch.setattr('ui.task_logic.backup_import._swap_tree', fail_last_tree_swap)
        _reject_crossing_ssh_mount(monkeypatch, app_root)
        with app.app_context():
            with pytest.raises(RuntimeError, match='changes pending'):
                restore_backup_archive(blob, None)

            row = AddonState.query.one()
            assert row.enabled is False
            assert row.settings == {'setting': 'local'}
        assert ssh_key.read_text() == 'LOCAL KEY'
        assert not list(ssh_key.parent.glob('.qlsm-restore-*'))

    def test_restored_ssh_key_keeps_its_permissions(self, app, app_root):
        (app_root / 'terraform' / 'ssh-keys' / 'old_key').chmod(0o600)
        with app.app_context():
            db.session.add(Host(name='h', provider='vultr'))
            db.session.commit()
            zip_bytes = build_backup_zip_bytes()
        blob = encrypt_archive(zip_bytes, None)

        with app.app_context():
            restore_backup_archive(blob, None)

        mode = os.stat(app_root / 'terraform' / 'ssh-keys' / 'old_key').st_mode & 0o777
        assert mode == 0o600

    def test_safety_snapshot_can_be_restored(self, app, app_root):
        blob = _make_backup_with_host(app, app_root)
        with app.app_context():
            restore_backup_archive(blob, None)
        snapshots = os.listdir(BACKUP_SNAPSHOTS_DIR)
        snapshot_path = os.path.join(BACKUP_SNAPSHOTS_DIR, snapshots[0])
        with open(snapshot_path, 'rb') as f:
            snapshot_blob = f.read()

        with app.app_context():
            # Must not raise BackupRestoreError('Not a valid QLSM backup file.')
            restore_backup_archive(snapshot_blob, None)

    def test_prunes_old_safety_snapshots(self, app, app_root):
        blob = _make_backup_with_host(app, app_root)
        with app.app_context():
            for _ in range(5):
                restore_backup_archive(blob, None)
        snapshots = os.listdir(BACKUP_SNAPSHOTS_DIR)
        assert len(snapshots) == 3

    def test_rollback_removes_archive_only_file_with_no_prior_counterpart(self, app, app_root, monkeypatch):
        """terraform/ssh-keys/old_key exists in the archive but is removed
        locally *after* the archive is built, so restoring introduces a
        file with nothing local to swap it in for (backup_path=None in
        _swap_tree's bookkeeping). If a later step fails, that
        archive-introduced file must be removed by rollback, not left
        behind as an orphan. Building the archive before the unlink is
        essential here: unlinking first would mean neither the local disk
        nor the archive has the file, and the final assertion would pass
        vacuously without exercising the archive-only rollback path at all."""
        blob = _make_backup_with_host(app, app_root)
        (app_root / 'terraform' / 'ssh-keys' / 'old_key').unlink()

        def _boom():
            assert (app_root / 'terraform' / 'ssh-keys' / 'old_key').exists()
            raise RuntimeError('simulated failure after file swap')

        monkeypatch.setattr(db.session, 'commit', _boom)

        with app.app_context():
            with pytest.raises(RuntimeError):
                restore_backup_archive(blob, None)

        assert not (app_root / 'terraform' / 'ssh-keys' / 'old_key').exists()

    def test_path_traversal_entry_raises_and_touches_nothing(self, app, app_root):
        with app.app_context():
            db.session.query(Host).delete()
            db.session.add(Host(name='untouched', provider='standalone'))
            db.session.commit()
            zip_bytes = build_backup_zip_bytes()

        buffer = io.BytesIO(zip_bytes)
        with zipfile.ZipFile(buffer, 'a', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('files/ssh-keys/../../../../tmp/pwned', 'malicious payload')
        blob = encrypt_archive(buffer.getvalue(), None)
        contents_before_restore = _managed_tree_contents(app_root)

        with app.app_context():
            with pytest.raises(BackupRestoreError):
                restore_backup_archive(blob, None)

            assert [h.name for h in Host.query.all()] == ['untouched']
        assert not os.path.exists('/tmp/pwned')
        assert _managed_tree_contents(app_root) == contents_before_restore
        for _prefix, root, _skip in backup_file_trees():
            assert not list((app_root / root).glob('.qlsm-restore-staging-*'))

    def test_builtin_presets_are_never_touched(self, app, app_root, monkeypatch):
        """configs/presets/_builtin ships with the app (it's in git, not
        user data) and must survive both a successful restore and a
        rolled-back one untouched — it's never captured in a backup and
        never deleted by one either, even though it's nested two levels
        inside a tree ('configs') that gets wiped and replaced."""
        (app_root / 'configs' / 'presets' / 'custom').mkdir(parents=True)
        (app_root / 'configs' / 'presets' / 'custom' / 'server.cfg').write_text('old custom')
        with app.app_context():
            db.session.add(Host(name='h', provider='vultr'))
            db.session.commit()
            zip_bytes = build_backup_zip_bytes()
        blob = encrypt_archive(zip_bytes, None)

        # Successful restore: _builtin must still be exactly as it was.
        with app.app_context():
            restore_backup_archive(blob, None)
        assert (app_root / 'configs' / 'presets' / '_builtin' / 'default' / 'server.cfg').read_text() == 'shipped with app'

        # A restore that fails after the file swap must also leave
        # _builtin alone, and must roll the custom preset back too.
        (app_root / 'configs' / 'presets' / 'custom' / 'server.cfg').write_text('changed after first restore')

        def _boom():
            raise RuntimeError('simulated failure')

        monkeypatch.setattr(db.session, 'commit', _boom)
        with app.app_context():
            with pytest.raises(RuntimeError):
                restore_backup_archive(blob, None)

        assert (app_root / 'configs' / 'presets' / '_builtin' / 'default' / 'server.cfg').read_text() == 'shipped with app'
        assert (app_root / 'configs' / 'presets' / 'custom' / 'server.cfg').read_text() == 'changed after first restore'
