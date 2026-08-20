import os
import re

from ui.database import get_preset_by_name
from ui.runtime import MINQLXTENDED, normalize_runtime


PRESETS_DIR = os.path.join('configs', 'presets')
BUILTIN_PRESETS_DIR = os.path.join(PRESETS_DIR, '_builtin')
PRESET_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
INTERNAL_PRESET_NAMES = {'_builtin'}
DEFAULT_PRESET_NAME = 'default'

# The builtin preset that carries a runtime's plugin baseline. Plugins are not
# interchangeable between the two runtimes, so every path that seeds an
# instance, a draft or a preset response from "the default preset" has to
# resolve the name through here -- hardcoding 'default' silently means "the
# minqlx one" and ships files that cannot import. Mirrors
# DEFAULT_PRESET_BY_RUNTIME in the frontend's constants/runtimes.js -- the two
# must not drift.
_DEFAULT_PRESET_BY_RUNTIME = {
    MINQLXTENDED: 'default-minqlxtended',
}


def default_preset_name_for_runtime(runtime):
    """The builtin preset supplying `runtime`'s baseline plugins.

    Falls back to the minqlx default for anything unrecognized: a NULL runtime
    column means the row predates the feature, and nothing but minqlx has ever
    existed.
    """
    return _DEFAULT_PRESET_BY_RUNTIME.get(
        normalize_runtime(runtime), DEFAULT_PRESET_NAME
    )


def default_preset_name_for_preset(preset_name):
    """The builtin preset to overlay beneath the preset named `preset_name`."""
    preset = get_preset_by_name(preset_name) if preset_name else None
    return default_preset_name_for_runtime(getattr(preset, 'runtime', None))



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
