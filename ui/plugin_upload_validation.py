"""Validation of plugin files uploaded in the runtime-upgrade dialog."""

import ast

from ui.plugin_compat import VERDICT_INCOMPATIBLE, classify
from ui.runtime_upgrade import UPGRADE_TARGET_RUNTIME

MAX_FILE_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024


class UploadRejected(ValueError):
    def __init__(self, message, reasons=None):
        super().__init__(message)
        self.message = message
        self.reasons = list(reasons or [])


def validate_plugin_upload(path, text):
    """Return the cleaned text, or raise UploadRejected."""
    if not isinstance(path, str) or not isinstance(text, str):
        raise UploadRejected('Plugin file must be text')
    if text.startswith('﻿'):
        text = text[1:]
    if not text.strip():
        raise UploadRejected('Plugin file is empty')
    if '\x00' in text:
        raise UploadRejected('Plugin file contains a NUL byte')
    try:
        raw = text.encode('utf-8')
    except UnicodeEncodeError:
        raise UploadRejected('Plugin file is not valid UTF-8 text')
    if len(raw) > MAX_FILE_BYTES:
        raise UploadRejected(
            f'Plugin file is larger than {MAX_FILE_BYTES // 1024} KiB')
    if '/' in path or not path.endswith('.py') or not path[:-3].isidentifier():
        raise UploadRejected('Plugin file name must be <plugin_name>.py')
    name = path[:-3]
    if name != name.lower() or name[0].isdigit():
        raise UploadRejected('Plugin file name must be lowercase and a valid identifier')
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise UploadRejected(
            f'Syntax error at line {exc.lineno}: {exc.msg}')
    except (ValueError, RecursionError) as exc:
        raise UploadRejected(f'Plugin file could not be parsed: {exc}')
    if not any(isinstance(n, ast.ClassDef) and n.name == name
               for n in tree.body):
        raise UploadRejected(f'Plugin file must define a top-level class {name}')
    verdict, reasons = classify(text, UPGRADE_TARGET_RUNTIME)
    if verdict == VERDICT_INCOMPATIBLE:
        raise UploadRejected('Plugin is not compatible with minqlxtended', reasons)
    return text
