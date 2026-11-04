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
import signal
import stat
import subprocess
import sys
import time

# Root-owned operation state: lock, token record and per-operation
# inventories/backups/staging. Never under the ql-controlled /home/ql tree.
DEFAULT_BASE = '/var/lib/qlsm/runtime-ops'
LOCK_NAME = '.lock'
TOKEN_NAME = '.token'
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
    _verify_trusted_dir(base, create=True)
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


# --- no-follow filesystem primitives ------------------------------------------------
#
# This helper runs as root but writes into /home/ql/qlds-<port>, a tree the
# ql user controls. Every path is therefore resolved one component at a time
# from `/` with O_NOFOLLOW directory descriptors, files are created with
# O_CREAT|O_EXCL|O_NOFOLLOW in the verified parent and renamed into place, and
# ownership/mode are set on the descriptor. A symlink anywhere in a path is a
# refusal, never something to follow.

_DIR_FLAGS = os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0) | os.O_NOFOLLOW


def _parts(path):
    if not os.path.isabs(path):
        raise Refused('path %s is not absolute' % path)
    parts = [part for part in path.split('/') if part]
    if any(part in ('.', '..') for part in parts):
        raise Refused('path %s is not normalized' % path)
    return parts


def _inside(path, root):
    path, root = os.path.normpath(path), os.path.normpath(root)
    return path.startswith(root.rstrip('/') + '/')


def _open_dir(path, create_below=None, uid=None, gid=None):
    """An O_NOFOLLOW descriptor for directory `path`. Missing components
    strictly inside `create_below` are created (0755, uid/gid)."""
    fd = os.open('/', _DIR_FLAGS)
    current = ''
    try:
        for part in _parts(path):
            current += '/' + part
            try:
                child = os.open(part, _DIR_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                if not (create_below and _inside(current, create_below)):
                    raise Refused('directory %s does not exist' % current)
                os.mkdir(part, 0o755, dir_fd=fd)
                child = os.open(part, _DIR_FLAGS, dir_fd=fd)
                os.fchmod(child, 0o755)
                if os.geteuid() == 0 and uid is not None:
                    os.fchown(child, uid, gid)
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENOTDIR, errno.EMLINK):
                    raise Refused('%s is a symlink or not a directory' % current)
                raise
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _verify_trusted_dir(path, create=False):
    """Require every component of `path` to be a real directory owned by root
    (or by this process's user, for unit tests) and not group/other-writable.
    The one exception is an ANCESTOR that is root-owned with the sticky bit
    (e.g. /tmp): nobody else can rename or remove entries in it that they do
    not own. On the production path (/var/lib/...) no component is sticky, so
    every component gets the full check. With create=True, missing
    components are created 0700."""
    fd = os.open('/', _DIR_FLAGS)
    current = ''
    parts = _parts(path)
    try:
        for index, part in enumerate(parts):
            current += '/' + part
            try:
                child = os.open(part, _DIR_FLAGS, dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise Refused('directory %s does not exist' % current)
                os.mkdir(part, 0o700, dir_fd=fd)
                child = os.open(part, _DIR_FLAGS, dir_fd=fd)
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENOTDIR, errno.EMLINK):
                    raise Refused('%s is a symlink or not a directory' % current)
                raise
            os.close(fd)
            fd = child
            st = os.fstat(fd)
            sticky_ancestor = (index < len(parts) - 1 and st.st_uid == 0
                               and st.st_mode & stat.S_ISVTX)
            if st.st_uid not in (0, os.geteuid()) or (st.st_mode & 0o022 and not sticky_ancestor):
                raise Refused('%s is not a root-owned, non-writable-by-others directory' % current)
        os.fchmod(fd, 0o700)
    finally:
        os.close(fd)


def _trusted_uids():
    """Owners allowed for files in the root-owned operation tree."""
    return {0, os.geteuid()}


def _ql_tree_uids():
    """Owners allowed for files read from the ql-controlled tree."""
    uids = _trusted_uids()
    try:
        import pwd
        uids.add(pwd.getpwnam('ql').pw_uid)
    except (ImportError, KeyError):
        pass
    return uids


def _read_file(path, allowed_uids):
    """(bytes, stat) of a regular file, refusing symlinks anywhere in `path`,
    FIFOs/devices (opened non-blocking, then fstat'd), hard links and files
    owned by anyone outside `allowed_uids`."""
    dfd = _open_dir(os.path.dirname(path))
    try:
        try:
            fd = os.open(os.path.basename(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=dfd)
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise Refused('%s is a symlink' % path)
            raise
        with os.fdopen(fd, 'rb') as handle:
            st = os.fstat(handle.fileno())
            if not stat.S_ISREG(st.st_mode):
                raise Refused('%s is not a regular file' % path)
            if st.st_nlink != 1:
                raise Refused('%s has %d hard links' % (path, st.st_nlink))
            if st.st_uid not in allowed_uids:
                raise Refused('%s is owned by uid %d' % (path, st.st_uid))
            return handle.read(), st
    finally:
        os.close(dfd)


def _lstat(path):
    """lstat of `path` with no-follow parents; None if it does not exist."""
    try:
        dfd = _open_dir(os.path.dirname(path))
    except Refused:
        if os.path.lexists(os.path.dirname(path)):
            raise
        return None
    try:
        return os.stat(os.path.basename(path), dir_fd=dfd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    finally:
        os.close(dfd)


def _write_file(path, data, mode, uid, gid, create_below=None):
    """Atomically replace `path` with `data`, never following a symlink."""
    dfd = _open_dir(os.path.dirname(path), create_below, uid, gid)
    name = os.path.basename(path)
    tmp = '.qlsm-tmp-%d-%s' % (os.getpid(), os.urandom(6).hex())
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=dfd)
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
            os.fchmod(fd, mode & 0o777)
            if os.geteuid() == 0 and uid is not None:
                os.fchown(fd, uid, gid)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.rename(tmp, name, src_dir_fd=dfd, dst_dir_fd=dfd)
    except BaseException:
        try:
            os.unlink(tmp, dir_fd=dfd)
        except OSError:
            pass
        raise
    finally:
        os.close(dfd)


def _unlink(path):
    dfd = _open_dir(os.path.dirname(path))
    try:
        os.unlink(os.path.basename(path), dir_fd=dfd)
    finally:
        os.close(dfd)


def _rmdir(path):
    dfd = _open_dir(os.path.dirname(path))
    try:
        os.rmdir(os.path.basename(path), dir_fd=dfd)
    finally:
        os.close(dfd)


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _ql_ids():
    if os.geteuid() != 0:
        return None, None
    import grp
    import pwd
    return pwd.getpwnam('ql').pw_uid, grp.getgrnam('ql').gr_gid


# --- managed files: plan, inventory, apply, restore ----------------------------------

def expand_plan(plan):
    """[(src, dest)] for every file the plan installs.

    Sources: `tree` (every file under `from`, relative layout kept),
    `names` (named files or directories from `from`), `missing_only` trees
    (files whose destination does not exist yet and no other source covers),
    and single `file` entries whose destination must be an explicit
    extra destination (the systemd unit).
    """
    qlds_dir = plan['qlds_dir']
    allowed_extra = set(plan.get('extra_destinations') or [])
    files = {}
    deferred = []

    def add(src, dest):
        dest = os.path.normpath(dest)
        if not (_inside(dest, qlds_dir) or dest in allowed_extra):
            raise Refused('destination %s is outside the instance directory' % dest)
        files[dest] = src

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
        if kind == 'tree':
            if os.path.isdir(source['from']):
                walk(source['from'], source['into'], add)
        elif kind == 'names':
            for name in source['names']:
                src = os.path.join(source['from'], name)
                dest = os.path.join(source['into'], name)
                if os.path.isdir(src) and not os.path.islink(src):
                    walk(src, dest, add)
                elif os.path.lexists(src):
                    add(src, dest)
                elif not source.get('optional'):
                    raise Refused('runtime artifact %s is missing' % src)
        elif kind == 'missing_only':
            deferred.append(source)
        elif kind == 'file':
            if os.path.normpath(source['to']) not in allowed_extra:
                raise Refused('file destination %s is not an allowed extra destination' % source['to'])
            add(source['from'], source['to'])
        else:
            raise Refused('unknown plan source kind %r' % kind)

    for source in deferred:
        if not os.path.isdir(source['from']):
            continue

        def maybe(src, dest):
            dest = os.path.normpath(dest)
            if dest not in files and _lstat(dest) is None:
                add(src, dest)
        walk(source['from'], source['into'], maybe)
    return sorted((src, dest) for dest, src in files.items())


def _dest_class(dest, qlds_dir, unit_paths):
    """(uid, gid, forced_mode) for a destination, or a refusal."""
    dest = os.path.normpath(dest)
    if dest in unit_paths:
        return 0, 0, 0o644
    if _inside(dest, qlds_dir):
        uid, gid = _ql_ids()
        return uid, gid, None
    raise Refused('destination %s is outside the instance directory' % dest)


def _check_ops_dir(ops_dir, base):
    if not OPERATION_ID.match(os.path.basename(os.path.dirname(os.path.normpath(ops_dir)))) \
            or not _inside(ops_dir, os.path.join(base, 'ops')):
        raise Refused('operation directory %s is not under %s/ops' % (ops_dir, base))


def _manifest_dest_ok(dest, qlds_dir, unit_paths):
    dest = os.path.normpath(dest)
    return dest in unit_paths or _inside(dest, qlds_dir)


def cmd_apply(args):
    with open(args.plan) as handle:
        plan = json.load(handle)
    _verify_trusted_dir(args.base)
    qlds_dir = os.path.normpath(plan['qlds_dir'])
    unit_paths = {os.path.normpath(p) for p in plan.get('extra_destinations') or []}
    ops_dir = os.path.normpath(plan['ops_dir'])
    _check_ops_dir(ops_dir, args.base)
    files = expand_plan(plan)
    record = plan.get('record', True) in (True, 'true', 'True')
    manifest_path = os.path.join(ops_dir, 'manifest.json')
    files_dir = os.path.join(ops_dir, 'files')

    # Read every source up front, no-follow, so what is recorded as
    # "written" is exactly what gets written.
    payload = []
    for src, dest in files:
        data, st = _read_file(src, _trusted_uids() if _inside(src, args.base) else _ql_tree_uids())
        uid, gid, forced = _dest_class(dest, qlds_dir, unit_paths)
        payload.append((dest, data, forced if forced is not None else (st.st_mode & 0o777), uid, gid))

    if record:
        _verify_trusted_dir(files_dir, create=True)
        manifest = _read_json(manifest_path) or {
            'schema': 1, 'operation_id': plan['operation_id'],
            'instance_id': plan['instance_id'], 'qlds_dir': qlds_dir,
            'unit_paths': sorted(unit_paths), 'entries': {}, 'created_dirs': [],
        }
        if os.path.normpath(manifest.get('qlds_dir', '')) != qlds_dir:
            raise Refused('inventory belongs to another instance directory')
        entries = manifest['entries']
        created_dirs = manifest['created_dirs']
        # Inventory first, write-once: a replay only adds paths it has not
        # seen, so the originals are never replaced by already-converted files.
        for dest, data, _mode, _uid, _gid in payload:
            parent = os.path.dirname(dest)
            missing = []
            while _inside(parent, qlds_dir) and _lstat(parent) is None:
                missing.append(parent)
                parent = os.path.dirname(parent)
            for directory in reversed(missing):
                if directory not in created_dirs:
                    created_dirs.append(directory)
            if dest in entries:
                entries[dest]['written_sha256'] = _sha256_bytes(data)
                continue
            current = _lstat(dest)
            if current is not None and not stat.S_ISREG(current.st_mode):
                raise Refused('%s exists and is not a regular file' % dest)
            entry = {'existed': current is not None, 'written_sha256': _sha256_bytes(data)}
            if current is not None:
                original, st = _read_file(
                    dest, _trusted_uids() if dest in unit_paths else _ql_tree_uids())
                backup = os.path.join(files_dir, '%06d' % len(entries))
                _write_file(backup, original, 0o600, None, None)
                entry.update({'sha256': _sha256_bytes(original), 'mode': '%04o' % (st.st_mode & 0o777),
                              'backup': backup})
            entries[dest] = entry
        _write_json(manifest_path, manifest)

    for dest, data, mode, uid, gid in payload:
        _write_file(dest, data, mode, uid, gid, create_below=qlds_dir)
    return {'applied': len(payload), 'recorded': bool(record),
            'manifest': manifest_path if record else None}


def cmd_restore(args):
    _verify_trusted_dir(args.base)
    ops_dir = os.path.normpath(args.ops_dir)
    _check_ops_dir(ops_dir, args.base)
    qlds_dir = os.path.normpath(args.qlds_dir)
    unit_paths = {os.path.normpath(p) for p in args.unit_path or []}
    manifest_path = os.path.join(ops_dir, 'manifest.json')
    if _lstat(manifest_path) is None:
        return {'restored': 0, 'removed': 0, 'kept': [], 'note': 'no inventory recorded'}
    manifest = json.loads(_read_file(manifest_path, _trusted_uids())[0].decode('utf-8'))
    if os.path.normpath(manifest.get('qlds_dir', '')) != qlds_dir:
        raise Refused('inventory belongs to another instance directory')
    files_dir = os.path.join(ops_dir, 'files')
    entries = manifest.get('entries') or {}
    # Validate everything before changing anything.
    for dest, entry in entries.items():
        if not _manifest_dest_ok(dest, qlds_dir, unit_paths):
            raise Refused('inventory destination %s is outside the allowed roots' % dest)
        if entry.get('existed'):
            backup = os.path.normpath(entry.get('backup') or '')
            if os.path.dirname(backup) != files_dir or not re.match(r'^[0-9]{6}$', os.path.basename(backup)):
                raise Refused('inventory backup %s is outside %s' % (backup, files_dir))
    for directory in manifest.get('created_dirs') or []:
        if not _inside(directory, qlds_dir):
            raise Refused('inventory directory %s is outside the instance directory' % directory)

    restored, removed, kept = 0, 0, []
    for dest, entry in sorted(entries.items()):
        uid, gid, forced = _dest_class(dest, qlds_dir, unit_paths)
        if entry['existed']:
            data, _st = _read_file(entry['backup'], _trusted_uids())
            if _sha256_bytes(data) != entry['sha256']:
                raise Refused('backup of %s does not match its recorded sha256' % dest)
            mode = forced if forced is not None else int(entry['mode'], 8) & 0o777
            _write_file(dest, data, mode, uid, gid, create_below=qlds_dir)
            restored += 1
        else:
            current = _lstat(dest)
            if current is None:
                continue
            if (stat.S_ISREG(current.st_mode) and current.st_nlink == 1
                    and _sha256_bytes(_read_file(dest, _ql_tree_uids())[0]) == entry.get('written_sha256')):
                _unlink(dest)
                removed += 1
            else:
                kept.append(dest)  # changed since we wrote it: not ours to delete
    for directory in sorted(manifest.get('created_dirs') or [], key=len, reverse=True):
        try:
            _rmdir(directory)
        except (OSError, Refused):
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
    apply_cmd.add_argument('--base', default=DEFAULT_BASE)
    apply_cmd.add_argument('--plan', required=True)
    restore = sub.add_parser('restore')
    restore.add_argument('--base', default=DEFAULT_BASE)
    restore.add_argument('--ops-dir', required=True)
    restore.add_argument('--qlds-dir', required=True)
    restore.add_argument('--unit-path', action='append')
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
