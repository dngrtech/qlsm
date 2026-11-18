"""Validate Custom runtime packages and resolve immutable releases."""

import gzip
import hashlib
import json
import os
import re
import shutil
import stat
import tarfile
import tempfile
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path

from flask import current_app

RELEASES_DIR = ".runtime-releases"
BUNDLE_LIMIT = 128 * 1024 * 1024
MEMBER_LIMIT = 2000
_PATH_PART = re.compile(r"[A-Za-z0-9_.-]+")
_PLUGIN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")


class RuntimeUnavailable(ValueError):
    """A Custom host's runtime cannot be used."""


@dataclass(frozen=True)
class RuntimeRelease:
    provider_id: str
    label: str
    version: str
    metadata: dict
    bundle_path: Path

    @property
    def sha256(self):
        return self.metadata["sha256"]

    @property
    def installed_path(self):
        return f"/var/lib/qlsm/custom-runtime/{self.sha256}"


def _path(value, *, basename=False):
    if not isinstance(value, str):
        return False
    parts = value.split("/")
    return (not basename or len(parts) == 1) and all(
        part not in (".", "..") and _PATH_PART.fullmatch(part) for part in parts
    )


def _matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def validate_custom_runtime(data):
    """Validate the JSON manifest fields without touching the archive."""
    if not isinstance(data, dict):
        raise ValueError("custom_runtime must be an object.")
    scalar_checks = {
        "plugin_api": lambda value: value in ("minqlx", "minqlxtended"),
        "source_commit": lambda value: _matches(_COMMIT, value),
        "sha256": lambda value: _matches(_SHA256, value),
        "bundle_path": _path,
        "engine_so": lambda value: _path(value, basename=True),
        "launch_script": lambda value: _path(value, basename=True),
        "log_filename": lambda value: _path(value, basename=True),
        "requirements_file": lambda value: _path(value, basename=True),
        "forced_lan_rate": lambda value: value is None or isinstance(value, bool),
    }
    for field, valid in scalar_checks.items():
        if not valid(data.get(field)):
            raise ValueError(f"Invalid custom_runtime.{field}.")
    list_checks = {
        "python_runtime_files": lambda value: _path(value, basename=True),
        "required_plugins": lambda value: _matches(_PLUGIN, value),
        "excluded_preloads": lambda value: _path(value, basename=True),
        "dependency_imports": lambda value: _matches(_PLUGIN, value),
    }
    for field, valid in list_checks.items():
        values = data.get(field, [] if field == "dependency_imports" else None)
        if (not isinstance(values, list) or not all(valid(value) for value in values)
                or len(set(values)) != len(values)):
            raise ValueError(f"Invalid custom_runtime.{field}.")
    platform = data.get("platform")
    if not isinstance(platform, dict):
        raise ValueError("Invalid custom_runtime.platform.")
    for field in ("os_id", "os_version", "arch"):
        if not _path(platform.get(field), basename=True):
            raise ValueError(f"Invalid custom_runtime.platform.{field}.")
    python = platform.get("python")
    if (not isinstance(python, list) or len(python) != 2
            or not all(type(version) is int and version >= 0 for version in python)):
        raise ValueError("Invalid custom_runtime.platform.python.")
    if tuple(python) < (3, 11):
        raise ValueError("Custom runtime installation requires Python 3.11 or newer.")
    return {key: data[key] for key in (*scalar_checks, *list_checks, "platform") if key in data}


def _verify_bundle(bundle, metadata):
    if not bundle.is_file():
        raise ValueError("Runtime bundle is missing from the addon package.")
    with bundle.open("rb") as source:
        if hashlib.file_digest(source, "sha256").hexdigest() != metadata["sha256"]:
            raise ValueError("Runtime bundle digest does not match its manifest.")
    # Bound decompression before parsing tar records, including PAX metadata.
    with gzip.open(bundle, "rb") as source, tempfile.TemporaryFile() as raw:
        while chunk := source.read(64 * 1024):
            if raw.tell() + len(chunk) > BUNDLE_LIMIT:
                raise ValueError("Expanded runtime bundle exceeds the size limit.")
            raw.write(chunk)
        raw.seek(0)
        members = {}
        with tarfile.open(fileobj=raw, mode="r:") as archive:
            for member in archive:
                name = member.name
                directory = member.isdir()
                # The host installer creates deps/ and .qlsm-release in the release.
                if (len(members) >= MEMBER_LIMIT or not _path(name) or name in members
                        or name.split("/")[0] in ("deps", ".qlsm-release")
                        or (not directory and member.type not in (tarfile.REGTYPE, tarfile.AREGTYPE))
                        or member.sparse is not None):
                    raise ValueError(f"Invalid runtime bundle member {name!r}.")
                members[name] = directory
    for name in members:
        if any(members.get(str(parent)) is False for parent in Path(name).parents):
            raise ValueError(f"Invalid runtime bundle member {name!r} under a file.")
    for field in ("engine_so", "launch_script", "requirements_file"):
        if members.get(metadata[field]) is not False:
            raise ValueError(f"Runtime bundle is missing {metadata[field]}.")
    for path in metadata["python_runtime_files"]:
        if path not in members and not any(name.startswith(f"{path}/") for name in members):
            raise ValueError(f"Runtime bundle is missing {path}.")
    for name in metadata["required_plugins"]:
        if members.get(f"plugins/{name}.py") is not False:
            raise ValueError(f"Runtime bundle is missing plugins/{name}.py.")


def retain_release(packages_dir, staging, manifest):
    """Validate and retain the release before replacing the active package."""
    metadata = manifest["custom_runtime"]
    source = Path(staging) / metadata["bundle_path"]
    try:
        _verify_bundle(source, metadata)
    except (OSError, EOFError, tarfile.TarError) as error:
        raise ValueError(f"Cannot read runtime bundle: {error}") from error
    parent = Path(packages_dir) / RELEASES_DIR / manifest["id"]
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / metadata["sha256"]
    release = {"label": manifest["name"], "version": manifest["version"], "metadata": metadata}
    with tempfile.TemporaryDirectory(dir=parent, prefix=".incoming-") as temporary:
        incoming = Path(temporary) / "release"
        incoming.mkdir()
        shutil.copyfile(source, incoming / "bundle.tar.gz")
        (incoming / "release.json").write_text(json.dumps(release), encoding="utf-8")
        try:
            incoming.rename(target)
        except OSError:
            if not target.is_dir():
                raise
            stored = json.loads((target / "release.json").read_text(encoding="utf-8"))
            if stored["metadata"] != metadata:
                raise ValueError("Runtime bundle digest already has different release metadata.")
            # Reinstalling the exact release can restore missing or corrupted bytes.
            os.replace(incoming / "bundle.tar.gz", target / "bundle.tar.gz")


def _active_provider(provider_id):
    from ui.addons.registry import get_addon

    addon = get_addon(provider_id)
    if addon is None or not Path(addon.root_dir).exists():
        raise RuntimeUnavailable(f"Runtime provider {provider_id} is missing.")
    if not addon.loaded or addon.errors:
        raise RuntimeUnavailable(f"Runtime provider {provider_id} is broken.")
    if not addon.globally_enabled:
        raise RuntimeUnavailable(f"Runtime provider {provider_id} is disabled.")
    if not addon.manifest.get("custom_runtime"):
        raise RuntimeUnavailable(f"Addon {provider_id} does not provide a Custom runtime.")
    return addon


@lru_cache(maxsize=128)
def _retained_bundle_digest(bundle, _stamp):
    # Status polling shares the result until the file is replaced or edited.
    with bundle.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _require_verified_bundle(bundle, provider_id, digest):
    identifier = f"{provider_id}/{digest[:12]}"
    try:
        info = bundle.stat()
        if not stat.S_ISREG(info.st_mode):
            raise RuntimeUnavailable(f"The pinned runtime bundle {identifier} is not a regular file.")
        stamp = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        actual = _retained_bundle_digest(bundle, stamp)
    except FileNotFoundError:
        raise RuntimeUnavailable(f"The pinned runtime bundle {identifier} is missing.") from None
    except OSError as error:
        raise RuntimeUnavailable(f"The pinned runtime bundle {identifier} cannot be read.") from error
    if actual != digest:
        raise RuntimeUnavailable(f"The pinned runtime bundle {identifier} failed its digest check.")


def _retained_release(provider_id, digest, *, require_bundle=True):
    if not _matches(_SHA256, digest):
        raise RuntimeUnavailable(f"Runtime provider {provider_id} has an invalid release digest.")
    directory = Path(current_app.config["ADDON_PACKAGES_DIR"]) / RELEASES_DIR / provider_id / digest
    bundle = directory / "bundle.tar.gz"
    if require_bundle:
        _require_verified_bundle(bundle, provider_id, digest)
    try:
        release = json.loads((directory / "release.json").read_text(encoding="utf-8"))
        metadata = validate_custom_runtime(release["metadata"])
        if metadata["sha256"] != digest:
            raise ValueError("mismatched digest")
        return RuntimeRelease(provider_id, release["label"], release["version"], metadata, bundle)
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise RuntimeUnavailable(f"Retained runtime metadata for {provider_id}/{digest[:12]} is invalid.") from error


def approved_release(provider_id: str) -> RuntimeRelease:
    addon = _active_provider(provider_id)
    metadata = addon.manifest["custom_runtime"]
    release = _retained_release(provider_id, metadata["sha256"])
    if release.metadata != metadata:
        raise RuntimeUnavailable(f"Runtime provider {provider_id} has conflicting release metadata.")
    return release


def pinned_release(provider_id: str, digest: str) -> RuntimeRelease:
    _active_provider(provider_id)
    return _retained_release(provider_id, digest)


def custom_platform_error(release, detected):
    expected = release.metadata["platform"]
    python = ".".join(map(str, expected["python"]))
    actual_python = (detected.get("python_version") or "").split(".")
    if (detected.get("id") == expected["os_id"] and detected.get("version_id") == expected["os_version"]
            and detected.get("arch") == expected["arch"] and actual_python[:2] == python.split(".")):
        return None
    return (f"{release.label} requires {expected['os_id']} {expected['os_version']} "
            f"{expected['arch']} with Python {python}.")


def release_for_host(host, *, require_provider=True):
    provider_id = host.runtime_provider_id
    digest = host.runtime_release_sha256
    release = (
        pinned_release(provider_id, digest) if require_provider
        else _retained_release(provider_id, digest, require_bundle=False)
    )
    if release.metadata["plugin_api"] != host.runtime_plugin_api:
        raise RuntimeUnavailable("The runtime release does not match this host's pinned plugin API.")
    return release


def custom_setup_extravars(host) -> dict:
    from ui.plugin_pool import operator_pool_dir
    from ui.runtime import runtime_paths

    release = release_for_host(host)
    metadata = release.metadata
    plugin_api = metadata["plugin_api"]
    return {
        "custom_bundle_path": str(release.bundle_path.resolve()),
        "custom_release_digest": release.sha256,
        "custom_platform": metadata["platform"],
        "custom_requirements_file": metadata["requirements_file"],
        "custom_launch_script": metadata["launch_script"],
        "custom_dependency_imports": metadata.get("dependency_imports", []),
        "runtime_shared_dir": release.installed_path,
        "runtime_plugins_dirname": runtime_paths(plugin_api)["plugins_dirname"],
        "common_plugins_operator_src": operator_pool_dir(plugin_api),
        "skip_pip_install": True,
    }
