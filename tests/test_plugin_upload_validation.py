import pytest

from ui.plugin_upload_validation import (
    MAX_FILE_BYTES, UploadRejected, validate_plugin_upload)

GOOD = "import minqlxtended\n\nclass x76admin(minqlxtended.Plugin):\n    pass\n"


def test_accepts_a_ported_plugin():
    assert validate_plugin_upload('x76admin.py', GOOD) == GOOD


def test_strips_a_bom_and_keeps_crlf():
    crlf = GOOD.replace('\n', '\r\n')
    assert validate_plugin_upload('x76admin.py', '﻿' + crlf) == crlf


@pytest.mark.parametrize('path', [
    'X76ADMIN.py', '../x76admin.py', 'sub/x76admin.py',
    'x76admin.PY', 'x76admin', '76admin.py'])
def test_rejects_bad_names(path):
    with pytest.raises(UploadRejected):
        validate_plugin_upload(path, GOOD)


def test_rejects_minqlx_code_with_the_scanner_reasons():
    text = "import minqlx\n\nclass x76admin(minqlx.Plugin):\n    pass\n"
    with pytest.raises(UploadRejected) as exc:
        validate_plugin_upload('x76admin.py', text)
    assert exc.value.reasons
    assert any('imports the minqlx module' in r for r in exc.value.reasons)


@pytest.mark.parametrize('text', [
    123,
    '',
    '  \n ',
    GOOD + '\x00',
    GOOD + '#' + 'a' * MAX_FILE_BYTES,
    GOOD + '# \ud800\n',
    'class x76admin(:',
    "import minqlxtended\nif True:\n    class x76admin(minqlxtended.Plugin):\n        pass\n",
    "import minqlxtended\nclass other(minqlxtended.Plugin):\n    pass\n",
])
def test_rejects_unusable_content(text):
    with pytest.raises(UploadRejected):
        validate_plugin_upload('x76admin.py', text)
