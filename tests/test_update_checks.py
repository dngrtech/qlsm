import os
from ui.update_checks import hash_local_tree, parse_sha256sum_output, diff_trees, hash_file


def test_hash_file_is_stable(tmp_path):
    f = tmp_path / "a.py"
    f.write_text("content")
    assert hash_file(str(f)) == hash_file(str(f))


def test_hash_local_tree_filters_by_extension(tmp_path):
    (tmp_path / "a.py").write_text("x")
    (tmp_path / "a.ql-plugin.json").write_text("{}")
    (tmp_path / "b.txt").write_text("ignored")
    result = hash_local_tree(str(tmp_path), extensions=('.py', '.ql-plugin.json'))
    assert set(result.keys()) == {"a.py", "a.ql-plugin.json"}


def test_hash_local_tree_missing_dir_returns_empty():
    assert hash_local_tree("/does/not/exist") == {}


def test_hash_local_tree_is_non_recursive(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "nested.py").write_text("x")
    (tmp_path / "top.py").write_text("y")
    result = hash_local_tree(str(tmp_path), extensions=('.py',))
    assert set(result.keys()) == {"top.py"}


def test_parse_sha256sum_output_basic():
    output = (
        "c5c1cea59eda48e32405781ad964762a  /home/ql/qlds-27960/minqlx-plugins/match_restore.py\n"
        "abc123  /home/ql/qlds-27960/minqlx-plugins/aliases.py\n"
    )
    result = parse_sha256sum_output(output, strip_prefix="/home/ql/qlds-27960/minqlx-plugins/")
    assert result == {
        "match_restore.py": "c5c1cea59eda48e32405781ad964762a",
        "aliases.py": "abc123",
    }


def test_parse_sha256sum_output_ignores_blank_lines():
    output = "abc  /x/y.py\n\n"
    result = parse_sha256sum_output(output, strip_prefix="/x/")
    assert result == {"y.py": "abc"}


def test_diff_trees_detects_added_modified_removed():
    source = {"a.py": "hash1", "b.py": "hash2", "c.py": "hash3"}
    target = {"a.py": "hash1", "b.py": "DIFFERENT", "d.py": "hash4"}
    changes = diff_trees(source, target)
    by_name = {c["name"]: c["change"] for c in changes}
    assert by_name == {
        "b.py": "modified",  # differs
        "c.py": "added",     # in source, missing from target
        "d.py": "removed",   # in target, gone from source
    }


def test_diff_trees_identical_is_empty():
    tree = {"a.py": "hash1"}
    assert diff_trees(tree, dict(tree)) == []
