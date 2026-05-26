import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ui.routes.ssh_key_permissions import LocalSSHKeyMaterialError
from ui.routes.ssh_key_permissions import normalize_local_ssh_key_material


def test_normalize_local_ssh_key_material_uses_parent_directory_owner(monkeypatch, tmp_path):
    key_dir = tmp_path / "ssh-keys"
    key_dir.mkdir()
    private_key = key_dir / "host_id_rsa"
    public_key = key_dir / "host_id_rsa.pub"
    private_key.write_text("private")
    public_key.write_text("public")

    dir_stat = key_dir.stat()
    chown = MagicMock()
    chmod = MagicMock()
    monkeypatch.setattr(os, "chown", chown)
    monkeypatch.setattr(os, "chmod", chmod)

    normalize_local_ssh_key_material(private_key, public_key)

    chown.assert_any_call(private_key, dir_stat.st_uid, dir_stat.st_gid)
    chown.assert_any_call(public_key, dir_stat.st_uid, dir_stat.st_gid)
    chmod.assert_called_once_with(private_key, 0o600)


def test_normalize_local_ssh_key_material_raises_clean_error_on_chown_failure(monkeypatch, tmp_path):
    key_dir = tmp_path / "ssh-keys"
    key_dir.mkdir()
    private_key = key_dir / "host_id_rsa"
    public_key = key_dir / "host_id_rsa.pub"
    private_key.write_text("private")
    public_key.write_text("public")

    monkeypatch.setattr(os, "chown", MagicMock(side_effect=OSError("nope")))

    with pytest.raises(LocalSSHKeyMaterialError, match="usable ownership/permissions"):
        normalize_local_ssh_key_material(private_key, public_key)
