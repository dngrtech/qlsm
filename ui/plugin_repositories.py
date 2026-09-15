"""External plugin repositories: fetch a `qlsm-plugins.json` manifest over
plain HTTP from an operator-supplied repo URL, and download individual plugin
files from it into the local pool (ql-assets/data/<runtime>-plugins/).

This is deliberately separate from `.ql-plugin.json` (plugin_manifest.py,
per-plugin display/edit metadata for a file already in the pool) and from the
qlsm control-plane addon system (docs/superpowers/specs/...-qlsm-addon-system-
design.md, extensions to qlsm itself) -- a repository is just a remote source
list for THIS manifest format's files.

Repo manifest shape, all fields but `filename` optional:
    {"plugins": [
        {"filename": "some_plugin.py", "label": "...", "description": "...",
         "runtime": "minqlx" | "minqlxtended" | "minqlxtended-patched",
         "requires_qlsm_version": "1.30.0"},
        ...
    ]}
`filename` must be a bare, root-level, importable module name ending in
.py -- same constraint the pool itself enforces (see plugin_manifest.py /
pluginSelection.js isEnableablePluginPath). `requires_qlsm_version` is the
plugin author's own claim, compared against this qlsm's own VERSION file by
version_risk() below -- see that function's docstring for what "risk" does
and does not mean here (operator decision, 2026-09-14).
"""
import json
import os
import re

import requests

from ui.plugin_pool import pool_dir as shared_pool_dir
from ui.runtime import is_valid_runtime

MANIFEST_FILENAME = 'qlsm-plugins.json'
MANIFEST_MAX_SIZE = 256 * 1024
PLUGIN_FILE_MAX_SIZE = 512 * 1024
FETCH_TIMEOUT_SECONDS = 10

# A plugin file is a Python module loaded by bare name -- no dots, no path
# separators, nothing but what a valid module name and this pool allow.
_FILENAME_RE = re.compile(r'^[A-Za-z0-9_\-]+\.py$')


class PluginRepositoryError(Exception):
    """Any fetch/parse/download failure. The message is written to be shown
    to the operator verbatim -- it never carries raw exception internals.
    `code` is set only for failures the caller (the route, then the UI) needs
    to branch on rather than just display -- currently just 'exists', so a
    download-blocked-by-an-existing-file can offer an overwrite confirmation
    instead of a dead-end error."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def _fetch(url, max_size):
    try:
        response = requests.get(url, timeout=FETCH_TIMEOUT_SECONDS)
    except requests.RequestException as e:
        raise PluginRepositoryError(f"Could not reach {url}: {e}") from e
    if response.status_code != 200:
        raise PluginRepositoryError(f"{url} returned HTTP {response.status_code}")
    content = response.content
    if len(content) > max_size:
        raise PluginRepositoryError(f"{url} is larger than the {max_size} byte limit")
    return content


def _manifest_url(base_url):
    return base_url.rstrip('/') + '/' + MANIFEST_FILENAME


def fetch_manifest(base_url):
    """Fetch and validate <base_url>/qlsm-plugins.json.

    Returns the normalized plugin list (a list of dicts, always present even
    if empty). A malformed individual entry is dropped rather than failing
    the whole fetch -- same "never throws on one bad entry" rule
    plugin_manifest.py already applies to `.ql-plugin.json`. Raises
    PluginRepositoryError for anything wrong with the fetch itself or the
    manifest's outer shape.
    """
    content = _fetch(_manifest_url(base_url), MANIFEST_MAX_SIZE)
    try:
        data = json.loads(content)
    except ValueError as e:
        raise PluginRepositoryError(f"{_manifest_url(base_url)} is not valid JSON: {e}") from e
    if not isinstance(data, dict) or not isinstance(data.get('plugins'), list):
        raise PluginRepositoryError(
            f"{_manifest_url(base_url)} must be a JSON object with a \"plugins\" array"
        )

    plugins = []
    for entry in data['plugins']:
        if not isinstance(entry, dict):
            continue
        filename = entry.get('filename')
        if not isinstance(filename, str) or not _FILENAME_RE.match(filename):
            continue
        plugins.append({
            'filename': filename,
            'label': entry['label'] if isinstance(entry.get('label'), str) and entry['label'].strip() else None,
            'description': (
                entry['description'] if isinstance(entry.get('description'), str) and entry['description'].strip()
                else None
            ),
            'runtime': entry.get('runtime') if is_valid_runtime(entry.get('runtime')) else None,
            'requires_qlsm_version': (
                entry['requires_qlsm_version']
                if isinstance(entry.get('requires_qlsm_version'), str) and entry['requires_qlsm_version'].strip()
                else None
            ),
        })
    return plugins


def _read_app_version():
    """This qlsm install's own VERSION file. Mirrors
    ui/task_logic/backup_export.py's _read_app_version() -- kept as its own
    copy rather than a shared import since it's five lines and the two
    modules have no other reason to depend on each other."""
    try:
        with open('VERSION', 'r', encoding='utf-8') as f:
            return f.read().strip()
    except OSError:
        return None


def _parse_dotted_version(value):
    if not isinstance(value, str):
        return None
    parts = value.strip().split('.')
    if not parts:
        return None
    try:
        return tuple(int(p) for p in parts)
    except ValueError:
        return None


def version_risk(requires_qlsm_version, current_qlsm_version=None):
    """Whether a plugin's declared `requires_qlsm_version` is a known problem
    for this install.

    We cannot confirm a plugin works at all -- not below its stated
    requirement, and not above it either, since "requires >= X" says nothing
    about whether a much newer qlsm broke something the plugin relies on.
    The one thing we CAN state with certainty is the opposite case: this
    install is older than what the plugin declares it needs, so a feature it
    depends on (e.g. a `.ql-plugin.json` field a later qlsm release added)
    may simply not exist yet. That -- and only that -- gets a hard warning;
    everything else returns None (no verdict, shown as plain info in the UI).
    """
    if current_qlsm_version is None:
        current_qlsm_version = _read_app_version()
    required = _parse_dotted_version(requires_qlsm_version)
    current = _parse_dotted_version(current_qlsm_version)
    if required is None or current is None or required <= current:
        return None
    return {
        'level': 'hard',
        'message': f"Needs qlsm >= {requires_qlsm_version}; this install runs {current_qlsm_version}.",
    }


def download_plugin(base_url, filename, runtime, overwrite=False):
    """Fetch <base_url>/<filename> (and its `.ql-plugin.json` sidecar, if the
    repo ships one) over HTTP and write them into the local pool for
    `runtime`. Raises PluginRepositoryError if the plugin source itself can't
    be fetched; a missing or malformed sidecar is silently skipped, same as
    plugin_manifest.py already tolerates for any other plugin.

    Refuses to replace a file already in the pool unless `overwrite` is set:
    a repo plugin sharing a name with a bundled one (e.g. balance.py) would
    otherwise silently replace it, and that copy then ships to every host and
    breaks the manifest.json sha256 baseline. The caller (the route) is the
    one that turns this into an operator-facing confirm-and-retry.
    """
    if not _FILENAME_RE.match(filename):
        raise PluginRepositoryError(f"Refusing to download unsafe filename: {filename!r}")

    pool_dir = shared_pool_dir(runtime)
    os.makedirs(pool_dir, exist_ok=True)
    dest_path = os.path.join(pool_dir, filename)
    if os.path.exists(dest_path) and not overwrite:
        raise PluginRepositoryError(
            f"{filename} already exists in the local pool.", code='exists',
        )

    source = _fetch(base_url.rstrip('/') + '/' + filename, PLUGIN_FILE_MAX_SIZE)
    with open(dest_path, 'wb') as f:
        f.write(source)

    manifest_filename = filename[:-len('.py')] + '.ql-plugin.json'
    manifest_path = os.path.join(pool_dir, manifest_filename)
    try:
        manifest_content = _fetch(base_url.rstrip('/') + '/' + manifest_filename, MANIFEST_MAX_SIZE)
        json.loads(manifest_content)  # validate before writing -- same trust boundary as the .py source
    except (PluginRepositoryError, ValueError):
        # No usable sidecar this time around -- a stale one from a previous
        # download of this same filename must not linger and describe the
        # new .py incorrectly.
        if os.path.exists(manifest_path):
            os.remove(manifest_path)
        return
    with open(manifest_path, 'wb') as f:
        f.write(manifest_content)
