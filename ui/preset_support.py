import os
import re

from ui.database import get_preset_by_name


PRESETS_DIR = os.path.join('configs', 'presets')
BUILTIN_PRESETS_DIR = os.path.join(PRESETS_DIR, '_builtin')
PRESET_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
INTERNAL_PRESET_NAMES = {'_builtin'}


def user_preset_path(name, configs_base=None):
    if configs_base is not None:
        return os.path.join(configs_base, 'presets', name)
    return os.path.join(PRESETS_DIR, name)


def builtin_preset_path(name):
    return os.path.join(BUILTIN_PRESETS_DIR, name)


def is_internal_preset_name(name):
    return isinstance(name, str) and name.lower() in INTERNAL_PRESET_NAMES


def resolve_preset_path(name, configs_base=None):
    preset = get_preset_by_name(name)
    if preset:
        return preset.path
    return user_preset_path(name, configs_base=configs_base)


def resolve_preset_subdir(name, subdir, configs_base=None):
    return os.path.join(resolve_preset_path(name, configs_base=configs_base), subdir)


def validate_preset_name_format(name):
    if not name:
        return False, "Preset name is required."
    if not PRESET_NAME_PATTERN.match(name):
        return False, "Preset name can only contain letters, numbers, hyphens, and underscores."
    return True, None


def validate_user_preset_name(name, current_preset_id=None):
    is_valid, error = validate_preset_name_format(name)
    if not is_valid:
        return False, error, 'format'
    if is_internal_preset_name(name):
        return False, f"The name '{name}' is reserved for internal preset storage.", 'internal'

    existing = get_preset_by_name(name)
    if existing and existing.id != current_preset_id:
        if existing.is_builtin:
            return False, f"The name '{name}' is reserved by a built-in preset.", 'builtin'
        return False, f"Preset with name '{name}' already exists.", 'duplicate'

    return True, None, None
