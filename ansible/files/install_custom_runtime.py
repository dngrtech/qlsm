"""Publish a verified Custom runtime and its Python dependencies together."""

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile


def _install_dependencies(stage, requirements, imports):
    dependencies = stage / "deps"
    dependencies.mkdir()
    stage.chmod(0o755)
    shutil.chown(dependencies, user="ql", group="ql")
    python = ["runuser", "-u", "ql", "--", "/usr/bin/python3"]
    subprocess.run([
        *python, "-m", "pip", "install", "--no-cache-dir", "--only-binary=:all:",
        "--target", str(dependencies), "-r", str(stage / requirements),
    ], check=True, cwd=stage)
    if imports:
        probe = "import importlib, sys; [importlib.import_module(name) for name in sys.argv[1:]]"
        subprocess.run([
            "runuser", "-u", "ql", "--", "env", f"PYTHONPATH={dependencies}",
            "/usr/bin/python3", "-c", probe, *imports,
        ], check=True, cwd=stage)


def install(bundle, digest, root, requirements, launcher, imports):
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Invalid Custom runtime release digest.")
    with bundle.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != digest:
            raise ValueError("Custom runtime bundle digest mismatch.")
    root.mkdir(mode=0o755, parents=True, exist_ok=True)
    target = root / digest
    with (root / ".install.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
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
            os.rename(stage, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("digest")
    parser.add_argument("root", type=Path)
    parser.add_argument("requirements")
    parser.add_argument("launcher")
    parser.add_argument("imports", type=json.loads)
    args = parser.parse_args()
    install(args.bundle, args.digest, args.root, args.requirements, args.launcher, args.imports)


if __name__ == "__main__":
    main()
