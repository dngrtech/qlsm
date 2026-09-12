import pytest

from ui.admin_permissions import (
    entries_from_rows,
    strip_numeric_admin_lines,
    validate_admin_entries,
)


class Row:
    def __init__(self, steam_id64, level):
        self.steam_id64 = steam_id64
        self.level = level


def test_validate_accepts_well_formed_entries():
    entries, error = validate_admin_entries([
        {"steam_id64": "76561198012345678", "level": 3},
        {"steam_id64": "76561198087654321", "level": 0},
    ])
    assert error is None
    assert entries == [
        {"steam_id64": "76561198012345678", "level": 3},
        {"steam_id64": "76561198087654321", "level": 0},
    ]


def test_validate_accepts_digit_string_level():
    entries, error = validate_admin_entries([{"steam_id64": "76561198012345678", "level": "5"}])
    assert error is None
    assert entries[0]["level"] == 5


@pytest.mark.parametrize("payload", [
    "nope",
    [{"steam_id64": "123", "level": 1}],
    [{"steam_id64": "76561198012345678", "level": 99}],
    [{"steam_id64": "76561198012345678", "level": "e"}],
    [{"steam_id64": "76561198012345678"}],
    [{"level": 3}],
])
def test_validate_rejects_bad_payloads(payload):
    entries, error = validate_admin_entries(payload)
    assert entries is None
    assert error


def test_validate_dedupes_last_wins():
    entries, error = validate_admin_entries([
        {"steam_id64": "76561198012345678", "level": 1},
        {"steam_id64": "76561198012345678", "level": 4},
    ])
    assert error is None
    assert entries == [{"steam_id64": "76561198012345678", "level": 4}]


def test_strip_removes_only_numeric_level_lines():
    text = (
        "# comment\n"
        "76561198012345678|3\n"
        "76561198087654321|admin\n"
        "76561199580544522|mod  # keep\n"
        "76561198111111111|2 # trailing\n"
        "\n"
        "garbage line\n"
    )
    assert strip_numeric_admin_lines(text) == (
        "# comment\n"
        "76561198087654321|admin\n"
        "76561199580544522|mod  # keep\n"
        "\n"
        "garbage line\n"
    )


def test_entries_from_rows():
    assert entries_from_rows([Row("76561198012345678", 3)]) == {"76561198012345678": 3}
