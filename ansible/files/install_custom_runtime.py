"""Publish a verified Custom runtime and its Python dependencies together."""

import argparse
from functools import partial
import fcntl
import hashlib
import json
import os
import platform
import sys
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile


def _dependency_member(member, destination):
    if member.type not in (tarfile.DIRTYPE, tarfile.REGTYPE, tarfile.AREGTYPE) or member.sparse is not None:
        raise tarfile.FilterError("Unexpected member in the runtime dependency tree.")
    return tarfile.data_filter(member, destination)


def _install_dependencies(stage, requirements, imports):
    dependencies = stage.parent / "dependencies"
    dependencies.mkdir()
    shutil.chown(dependencies, user="ql", group="ql")
    as_ql = ["runuser", "-u", "ql", "--"]
    subprocess.run([
        *as_ql, "/usr/bin/python3", "-m", "pip", "install", "--no-cache-dir", "--only-binary=:all:",
        "--target", str(dependencies), "-r", str(stage / requirements),
    ], check=True, cwd=stage)

    # Read ql's files as ql and publish fresh files with safe modes and ownership.
    published = stage / "deps"
    published.mkdir()
    with tempfile.TemporaryFile(dir=stage.parent) as snapshot:
        subprocess.run([*as_ql, "/bin/tar", "-C", str(dependencies), "-cf", "-", "."],
                       check=True, stdout=snapshot, cwd=stage)
        snapshot.seek(0)
        with tarfile.open(fileobj=snapshot, mode="r:") as archive:
            archive.extractall(published, filter=_dependency_member)

    if imports:
        probe = "import importlib, sys; [importlib.import_module(name) for name in sys.argv[1:]]"
        subprocess.run([
            *as_ql, "env", f"PYTHONPATH={published}",
            "/usr/bin/python3", "-c", probe, *imports,
        ], check=True, cwd=stage)


def install(bundle, digest, root, requirements, launcher, imports, *, verify_owner=None):
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Invalid Custom runtime release digest.")
    with bundle.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != digest:
            raise ValueError("Custom runtime bundle digest mismatch.")
    root.mkdir(mode=0o755, parents=True, exist_ok=True)
    target = root / digest
    with (root / ".install.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if verify_owner is not None:
            verify_owner()
        if target.is_dir():
            if (target / ".qlsm-release").read_text(encoding="ascii").strip() != digest:
                raise ValueError("Existing runtime installation has an invalid release marker.")
            return
        with tempfile.TemporaryDirectory(dir=root, prefix=".install-") as temporary:
            container = Path(temporary)
            container.chmod(0o755)
            stage = container / "release"
            stage.mkdir(mode=0o755)
            with tarfile.open(bundle, "r:gz") as archive:
                archive.extractall(stage, filter="data")
            executable = stage / launcher
            executable.chmod(0o755)
            _install_dependencies(stage, requirements, imports)
            (stage / ".qlsm-release").write_text(digest + "\n", encoding="ascii")
            if verify_owner is not None:
                verify_owner()
            os.rename(stage, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("digest")
    parser.add_argument("root", type=Path)
    parser.add_argument("requirements")
    parser.add_argument("launcher")
    parser.add_argument("imports", type=json.loads)
    parser.add_argument("--platform", type=json.loads)
    parser.add_argument("--operation-fence", nargs=3, metavar=("HELPER", "OPERATION", "TOKEN"))
    args = parser.parse_args()
    if args.platform:
        os_release = platform.freedesktop_os_release()
        actual = {"os_id": os_release.get("ID", "").lower(), "os_version": os_release.get("VERSION_ID"),
                  "arch": platform.machine(), "python": list(sys.version_info[:2])}
        if (any(actual[key] != args.platform.get(key) for key in actual)
                or not hasattr(tarfile, "data_filter")):
            parser.error("The host is incompatible with the release platform.")
    verify_owner = None
    if args.operation_fence:
        helper, operation, token = args.operation_fence
        verify_owner = partial(subprocess.run, [
            sys.executable, helper, "check", "--operation-id", operation, "--fencing-token", token,
        ], check=True)
    install(args.bundle, args.digest, args.root, args.requirements, args.launcher, args.imports,
            verify_owner=verify_owner)


if __name__ == "__main__":
    main()
