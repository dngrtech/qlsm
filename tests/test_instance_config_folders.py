"""Tests for nested-path validation and .ent extension on instance configs."""

import pytest
from ui.routes.instance_routes import (
    _validate_path_segment,
    _validate_relative_path,
    _validate_configs_map,
    ALLOWED_CONFIG_EXTENSIONS,
    RESERVED_CONFIG_FOLDER_NAMES,
)


class TestValidatePathSegment:
    def test_accepts_safe_name(self):
        assert _validate_path_segment("foo.cfg", ALLOWED_CONFIG_EXTENSIONS) is None

    def test_rejects_slash(self):
        assert _validate_path_segment("a/b", ALLOWED_CONFIG_EXTENSIONS) is not None

    def test_rejects_dotdot(self):
        assert _validate_path_segment("..", ALLOWED_CONFIG_EXTENSIONS) is not None

    def test_rejects_leading_dot(self):
        assert _validate_path_segment(".hidden", ALLOWED_CONFIG_EXTENSIONS) is not None

    def test_segment_only_skips_extension_check(self):
        # When allowed_extensions is None, segment is treated as folder name (no extension required)
        assert _validate_path_segment("custom_entities", None) is None


class TestValidateRelativePath:
    def test_accepts_flat_file(self):
        assert _validate_relative_path("server.cfg", ALLOWED_CONFIG_EXTENSIONS) is None

    def test_accepts_nested_file(self):
        assert _validate_relative_path("custom_entities/items.ent", ALLOWED_CONFIG_EXTENSIONS) is None

    def test_rejects_too_deep(self):
        err = _validate_relative_path("a/b/c.cfg", ALLOWED_CONFIG_EXTENSIONS, max_depth=2)
        assert err is not None

    def test_rejects_leading_slash(self):
        assert _validate_relative_path("/server.cfg", ALLOWED_CONFIG_EXTENSIONS) is not None

    def test_rejects_trailing_slash(self):
        assert _validate_relative_path("foo/", ALLOWED_CONFIG_EXTENSIONS) is not None


class TestEntExtension:
    def test_ent_is_allowed(self):
        assert ".ent" in ALLOWED_CONFIG_EXTENSIONS

    def test_ent_validates_in_configs_map(self):
        err, _ = _validate_configs_map({
            'server.cfg': '',
            'mappool.txt': '',
            'access.txt': '',
            'workshop.txt': '',
            'custom_entities/items.ent': '// entity overrides',
        })
        assert err is None


class TestReservedFolders:
    def test_scripts_is_reserved(self):
        assert 'scripts' in RESERVED_CONFIG_FOLDER_NAMES

    def test_factories_is_reserved(self):
        assert 'factories' in RESERVED_CONFIG_FOLDER_NAMES
