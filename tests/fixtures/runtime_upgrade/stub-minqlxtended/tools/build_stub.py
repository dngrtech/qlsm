"""Build stub minqlxtended artifacts for the integration fixture.

bin/minqlxtended.x64.so   -- placeholder bytes (no real engine on this target)
bin/minqlxtended.zip      -- a `minqlxtended` package whose initialize() records
                             which redis the interpreter imported
bin/run_server_x64_minqlxtended.sh
                          -- runs the (patched) `loader` literal from
                             src/python/python_embed.c under system python3,
                             standing in for the embedded interpreter
"""
import ast
import os
import re
import zipfile

src = open('src/python/python_embed.c').read()
block = re.search(r'static const char loader\[\] = (.*?);\n', src, re.S).group(1)
block = block.replace('" CORE_MODULE "', 'minqlxtended.zip')
loader = ''.join(ast.literal_eval(piece) for piece in re.findall(r'"(?:[^"\\]|\\.)*"', block))

os.makedirs('bin', exist_ok=True)
with open('bin/minqlxtended.x64.so', 'wb') as handle:
    handle.write(b'stub minqlxtended engine\n')
with zipfile.ZipFile('bin/minqlxtended.zip', 'w') as archive:
    archive.writestr('minqlxtended/__init__.py', (
        'import json, os, sys\n'
        'def initialize():\n'
        '    import redis\n'
        '    probe = {"redis_version": redis.__version__, "redis_file": redis.__file__,\n'
        '             "sys_path": sys.path}\n'
        '    with open(os.environ["QLSM_PROBE_OUT"], "w") as handle:\n'
        '        json.dump(probe, handle)\n'
    ))
with open('bin/run_server_x64_minqlxtended.sh', 'w') as handle:
    handle.write('#!/bin/bash\ncd "$(dirname "$0")"\nexec python3 -c "$(cat <<\'PY\'\n'
                 + loader + 'import sys\nsys.exit(0 if ret else 1)\nPY\n)"\n')
os.chmod('bin/run_server_x64_minqlxtended.sh', 0o755)
