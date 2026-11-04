#!/usr/bin/env python3
"""Remote helper for runtime-upgrade playbooks (install_runtime.yml,
update_instance_runtime.yml, finalize_runtime_operation.yml).

Run through ansible.builtin.script, so nothing is installed on the host.
Standard library only; must run on the host's system python3.

Subcommands
  acquire   take the host's runtime-operation lock for one play and check the
            fencing token. A detached holder process keeps the flock until
            `release` (or the TTL) ends it, because each Ansible task is a
            separate process.
  release   end the holder started by `acquire` for this operation/token.
  finalize  mark the token record terminal so a later operation can take over.
  apt-check report which build prerequisites are missing and (with
            --simulate) refuse any install that would upgrade, downgrade or
            remove an installed package.
  apply     install planned managed files, recording an inventory and backups
            first (write-once per operation/instance).
  restore   put an inventory back: restore backed-up files, remove files the
            operation created (only if still exactly what it wrote).

Every subcommand prints one JSON object on stdout and exits non-zero on
refusal.
"""
import argparse
import errno
import fcntl
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

DEFAULT_BASE = '/home/ql/runtime-deps'
LOCK_NAME = '.qlsm-runtime-op.lock'
TOKEN_NAME = '.qlsm-runtime-op.token'
OPERATION_ID = re.compile(r'^[0-9a-f]{32}$')


class Refused(Exception):
    pass


# --- small durable-file helpers -----------------------------------------------

def _write_json(path, data, mode=0o600):
    tmp = '%s.tmp.%d' % (path, os.getpid())
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, 'w') as handle:
        json.dump(data, handle, sort_keys=True, indent=1)
        handle.flush()
        os.fsync(handle.fileno())
    os.rename(tmp, path)
    _fsync_dir(os.path.dirname(path))


def _fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_json(path):
    try:
        with open(path) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


# --- lock and fencing -----------------------------------------------------------

def token_decision(record, operation_id, token, terminal_ids):
    """None when (operation_id, token) may proceed, else the refusal reason.

    Pure, so the rules are unit-testable without a host.
    """
    if not record:
        return None
    held_by = record.get('operation_id')
    if held_by != operation_id:
        if record.get('state') == 'finalized' or held_by in terminal_ids:
            return None
        return 'runtime operation %s still owns this host' % held_by
    if record.get('state') == 'finalized':
        return 'operation %s was already finalized on this host' % operation_id
    recorded = int(record.get('fencing_token', 0))
    if recorded > token:
        return 'stale fencing token %d; host has seen %d for operation %s' % (
            token, recorded, operation_id)
    return None


def _check_identity(operation_id, token):
    if not OPERATION_ID.match(operation_id or ''):
        raise Refused('operation_id must be 32 lowercase hex characters')
    if token < 0:
        raise Refused('fencing_token must be a non-negative integer')


def _open_lock(base):
    os.makedirs(base, exist_ok=True)
    fd = os.open(os.path.join(base, LOCK_NAME), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        if exc.errno in (errno.EAGAIN, errno.EACCES, errno.EWOULDBLOCK):
            record = _read_json(os.path.join(base, TOKEN_NAME)) or {}
            raise Refused('another runtime operation play is still running on this host '
                          '(operation %s, holder pid %s)' % (record.get('operation_id'),
                                                             record.get('holder_pid')))
        raise
    return fd


def _spawn_holder(lock_fd, ttl):
    """Fork a detached child that keeps `lock_fd` (and so the flock) open
    until it is signalled or `ttl` seconds pass. Returns the child's pid."""
    read_end, write_end = os.pipe()
    pid = os.fork()
    if pid == 0:  # first child
        os.close(read_end)
        os.setsid()
        grandchild = os.fork()
        if grandchild:
            os.write(write_end, str(grandchild).encode())
            os._exit(0)
        os.close(write_end)
        devnull = os.open(os.devnull, os.O_RDWR)
        for fd in (0, 1, 2):
            os.dup2(devnull, fd)
        # Keep only the locked descriptor: an inherited pipe would make the
        # calling Ansible task wait for the holder to exit.
        os.closerange(3, lock_fd)
        os.closerange(lock_fd + 1, 1024)
        signal.signal(signal.SIGTERM, lambda *_: os._exit(0))
        deadline = time.time() + ttl
        while time.time() < deadline:
            time.sleep(1)
        os._exit(0)
    os.close(write_end)
    os.waitpid(pid, 0)
    holder = int(os.read(read_end, 32).decode() or 0)
    os.close(read_end)
    return holder


def cmd_acquire(args):
    _check_identity(args.operation_id, args.fencing_token)
    terminal = set(filter(None, (args.terminal_ids or '').split(',')))
    fd = _open_lock(args.base)
    try:
        token_path = os.path.join(args.base, TOKEN_NAME)
        reason = token_decision(_read_json(token_path), args.operation_id,
                                args.fencing_token, terminal)
        if reason:
            raise Refused(reason)
        holder = _spawn_holder(fd, args.ttl)
        _write_json(token_path, {
            'operation_id': args.operation_id,
            'fencing_token': args.fencing_token,
            'state': 'active',
            'holder_pid': holder,
            'acquired_at': int(time.time()),
            'ttl': args.ttl,
        })
        return {'acquired': True, 'holder_pid': holder}
    finally:
        os.close(fd)  # the holder keeps its own copy of the locked descriptor


def cmd_release(args):
    _check_identity(args.operation_id, args.fencing_token)
    record = _read_json(os.path.join(args.base, TOKEN_NAME)) or {}
    if (record.get('operation_id') != args.operation_id
            or int(record.get('fencing_token', -1)) != args.fencing_token):
        # A newer owner took over; its holder is not ours to stop.
        return {'released': False, 'reason': 'record belongs to another owner'}
    pid = int(record.get('holder_pid') or 0)
    if pid > 0:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    return {'released': True, 'holder_pid': pid}


def cmd_finalize(args):
    _check_identity(args.operation_id, args.fencing_token)
    fd = _open_lock(args.base)
    try:
        token_path = os.path.join(args.base, TOKEN_NAME)
        record = _read_json(token_path)
        if not record:
            return {'finalized': False, 'reason': 'no operation recorded on this host'}
        if record.get('operation_id') != args.operation_id:
            return {'finalized': False, 'reason': 'host is recorded for another operation'}
        if record.get('state') == 'finalized':
            return {'finalized': True, 'already': True}
        reason = token_decision(record, args.operation_id, args.fencing_token, set())
        if reason:
            raise Refused(reason)
        record.update({'state': 'finalized', 'fencing_token': args.fencing_token,
                       'holder_pid': None, 'finalized_at': int(time.time())})
        _write_json(token_path, record)
        return {'finalized': True}
    finally:
        os.close(fd)


# --- apt additive-install guard -------------------------------------------------

_INST = re.compile(r'^Inst (\S+)( \[([^\]]*)\])?')
_REMV = re.compile(r'^Remv (\S+)')


def parse_apt_simulation(output):
    """Return (would_install, violations) from `apt-get -s install` output.

    An `Inst pkg [old] (new ...)` line means an installed package would be
    upgraded or downgraded; any `Remv` line means one would be removed. Both
    are violations: the installer may only add missing packages.
    """
    installs, violations = [], []
    for line in output.splitlines():
        match = _INST.match(line)
        if match:
            if match.group(2):
                violations.append('would change installed %s (%s)' % (match.group(1), match.group(3)))
            else:
                installs.append(match.group(1))
            continue
        match = _REMV.match(line)
        if match:
            violations.append('would remove %s' % match.group(1))
    return installs, violations


def _missing_packages(packages):
    missing = []
    for package in packages:
        result = subprocess.run(['dpkg-query', '-W', '-f=${Status}', package],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                universal_newlines=True)
        if result.returncode != 0 or result.stdout.strip() != 'install ok installed':
            missing.append(package)
    return missing


def cmd_apt_check(args):
    missing = _missing_packages(args.packages)
    result = {'missing': missing, 'would_install': [], 'violations': []}
    if not missing or not args.simulate:
        return result
    env = dict(os.environ, DEBIAN_FRONTEND='noninteractive', LC_ALL='C')
    sim = subprocess.run(['apt-get', '-s', 'install', '--no-install-recommends', '--no-upgrade'] + missing,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         universal_newlines=True, env=env)
    if sim.returncode != 0:
        raise Refused('apt-get simulation failed: ' + sim.stdout.strip()[-500:])
    result['would_install'], result['violations'] = parse_apt_simulation(sim.stdout)
    if result['violations']:
        raise Refused('installing %s would change installed packages: %s' % (
            ' '.join(missing), '; '.join(result['violations'])))
    return result


# --- managed files: plan, inventory, apply, restore ----------------------------------

def _inside(path, root):
    path, root = os.path.normpath(path), os.path.normpath(root)
    return path.startswith(root + os.sep)


def expand_plan(plan):
    """[(src, dest, mode, owner)] for every file the plan installs.

    Sources: `tree` (every file under `from`, relative layout kept),
    `names` (named files or directories from `from`), `missing_only` trees
    (files whose destination does not exist yet and no other source covers),
    and single `file` entries with an explicit destination.
    """
    qlds_dir = plan['qlds_dir']
    allowed_extra = set(plan.get('extra_destinations') or [])
    files = {}
    deferred = []

    def add(src, dest, mode, owner):
        dest = os.path.normpath(dest)
        if not (_inside(dest, qlds_dir) or dest in allowed_extra):
            raise Refused('destination %s is outside the instance directory' % dest)
        files[dest] = (src, mode, owner)

    def walk(root, into, sink):
        for current, dirs, names in os.walk(root):
            dirs.sort()
            for name in sorted(names):
                src = os.path.join(current, name)
                if os.path.islink(src):
                    raise Refused('refusing to install symlink %s' % src)
                sink(src, os.path.join(into, os.path.relpath(src, root)))

    for source in plan.get('sources') or []:
        kind = source['kind']
        owner = source.get('owner', 'ql')
        if kind == 'tree':
            if os.path.isdir(source['from']):
                walk(source['from'], source['into'], lambda s, d: add(s, d, None, owner))
        elif kind == 'names':
            for name in source['names']:
                src = os.path.join(source['from'], name)
                dest = os.path.join(source['into'], name)
                if os.path.isdir(src):
                    walk(src, dest, lambda s, d: add(s, d, None, owner))
                elif os.path.isfile(src):
                    add(src, dest, None, owner)
                elif not source.get('optional'):
                    raise Refused('runtime artifact %s is missing' % src)
        elif kind == 'missing_only':
            deferred.append(source)
        elif kind == 'file':
            add(source['from'], source['to'], int(source['mode'], 8) if source.get('mode') else None, owner)
        else:
            raise Refused('unknown plan source kind %r' % kind)

    for source in deferred:
        if not os.path.isdir(source['from']):
            continue

        def maybe(src, dest, owner=source.get('owner', 'ql')):
            dest = os.path.normpath(dest)
            if dest not in files and not os.path.lexists(dest):
                add(src, dest, None, owner)
        walk(source['from'], source['into'], maybe)
    return [(src, dest, mode, owner) for dest, (src, mode, owner) in sorted(files.items())]


def _owner_ids(owner):
    import grp
    import pwd
    return pwd.getpwnam(owner).pw_uid, grp.getgrnam(owner).gr_gid


def _chown(path, owner):
    if os.geteuid() == 0 and owner:
        uid, gid = _owner_ids(owner)
        os.chown(path, uid, gid)


def _install(src, dest, mode, owner):
    tmp = '%s.qlsm-tmp' % dest
    shutil.copyfile(src, tmp)
    os.chmod(tmp, mode if mode is not None else (os.stat(src).st_mode & 0o7777))
    _chown(tmp, owner)
    with open(tmp, 'rb') as handle:
        os.fsync(handle.fileno())
    os.rename(tmp, dest)


def _missing_parents(dest, stop):
    missing = []
    current = os.path.dirname(dest)
    while current != stop and not os.path.isdir(current) and _inside(current, stop):
        missing.append(current)
        current = os.path.dirname(current)
    return list(reversed(missing))


def cmd_apply(args):
    with open(args.plan) as handle:
        plan = json.load(handle)
    files = expand_plan(plan)
    qlds_dir = plan['qlds_dir']
    ops_dir = plan['ops_dir']
    record = plan.get('record', True) in (True, 'true', 'True')
    manifest_path = os.path.join(ops_dir, 'manifest.json')

    if record:
        os.makedirs(os.path.join(ops_dir, 'files'), mode=0o700, exist_ok=True)
        os.chmod(ops_dir, 0o700)
        manifest = _read_json(manifest_path) or {
            'schema': 1, 'operation_id': plan['operation_id'],
            'instance_id': plan['instance_id'], 'qlds_dir': qlds_dir,
            'entries': {}, 'created_dirs': [],
        }
        entries = manifest['entries']
        created_dirs = manifest['created_dirs']
        # Inventory first, write-once: a replay only adds paths it has not
        # seen, so the originals are never replaced by already-converted files.
        for src, dest, _mode, _owner in files:
            for parent in _missing_parents(dest, qlds_dir):
                if parent not in created_dirs:
                    created_dirs.append(parent)
            if dest in entries:
                entries[dest]['written_sha256'] = _sha256(src)
                continue
            entry = {'existed': os.path.isfile(dest), 'written_sha256': _sha256(src)}
            if entry['existed']:
                st = os.stat(dest)
                backup = os.path.join(ops_dir, 'files', '%06d' % len(entries))
                shutil.copy2(dest, backup)
                entry.update({'sha256': _sha256(dest), 'mode': '%04o' % (st.st_mode & 0o7777),
                              'uid': st.st_uid, 'gid': st.st_gid, 'backup': backup})
            entries[dest] = entry
        _write_json(manifest_path, manifest)

    for src, dest, mode, owner in files:
        for parent in _missing_parents(dest, qlds_dir):
            os.mkdir(parent, 0o755)
            _chown(parent, owner)
        _install(src, dest, mode, owner)
    return {'applied': len(files), 'recorded': bool(record),
            'manifest': manifest_path if record else None}


def cmd_restore(args):
    manifest_path = os.path.join(args.ops_dir, 'manifest.json')
    manifest = _read_json(manifest_path)
    if manifest is None:
        return {'restored': 0, 'removed': 0, 'kept': [], 'note': 'no inventory recorded'}
    restored, removed, kept = 0, 0, []
    for dest, entry in sorted(manifest['entries'].items()):
        if entry['existed']:
            tmp = '%s.qlsm-tmp' % dest
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(entry['backup'], tmp)
            os.chmod(tmp, int(entry['mode'], 8))
            if os.geteuid() == 0:
                os.chown(tmp, entry['uid'], entry['gid'])
            os.rename(tmp, dest)
            if _sha256(dest) != entry['sha256']:
                raise Refused('restored %s does not match its recorded sha256' % dest)
            restored += 1
        elif os.path.isfile(dest):
            if _sha256(dest) == entry.get('written_sha256'):
                os.unlink(dest)
                removed += 1
            else:
                kept.append(dest)  # changed since we wrote it: not ours to delete
    for directory in sorted(manifest.get('created_dirs') or [], key=len, reverse=True):
        try:
            os.rmdir(directory)
        except OSError:
            pass  # not empty (plugin-owned data) or already gone
    return {'restored': restored, 'removed': removed, 'kept': kept}


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command')
    for name in ('acquire', 'release', 'finalize'):
        cmd = sub.add_parser(name)
        cmd.add_argument('--base', default=DEFAULT_BASE)
        cmd.add_argument('--operation-id', required=True)
        cmd.add_argument('--fencing-token', type=int, required=True)
        if name == 'acquire':
            cmd.add_argument('--terminal-ids', default='')
            cmd.add_argument('--ttl', type=int, default=4200)
    apt = sub.add_parser('apt-check')
    apt.add_argument('--simulate', action='store_true')
    apt.add_argument('packages', nargs='+')
    apply_cmd = sub.add_parser('apply')
    apply_cmd.add_argument('--plan', required=True)
    restore = sub.add_parser('restore')
    restore.add_argument('--ops-dir', required=True)
    args = parser.parse_args(argv)
    handlers = {'acquire': cmd_acquire, 'release': cmd_release, 'finalize': cmd_finalize,
                'apt-check': cmd_apt_check, 'apply': cmd_apply, 'restore': cmd_restore}
    if args.command not in handlers:
        parser.error('a subcommand is required')
    try:
        print(json.dumps(handlers[args.command](args), sort_keys=True))
        return 0
    except Refused as exc:
        print(json.dumps({'refused': str(exc)}, sort_keys=True))
        return 3


if __name__ == '__main__':
    sys.exit(main())
