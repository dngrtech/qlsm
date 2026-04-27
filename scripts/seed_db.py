#!/usr/bin/env python3
"""Load mock data into the QLSM dev database from CSV files.

Usage:
  python scripts/seed_db.py --hosts scripts/sample_data/hosts.csv \\
                             --instances scripts/sample_data/instances.csv
  python scripts/seed_db.py --hosts ... --instances ... --clear
  python scripts/seed_db.py --hosts ... --instances ... --update
"""
import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import create_app, db
from ui.database import get_host_by_name, get_instance_by_name
from ui.models import Host, HostStatus, InstanceStatus, QLFilterStatus, QLInstance

BOOL_TRUE = {'true', '1', 'yes', 'y'}


def _bool(val):
    return val.strip().lower() in BOOL_TRUE


def _opt(val):
    s = val.strip()
    return s if s else None


def _int_opt(val):
    s = val.strip()
    return int(s) if s else None


def _host_status(raw, row_num):
    try:
        return HostStatus(raw)
    except ValueError:
        print(f"  [ERROR] row {row_num}: unknown host status '{raw}'")
        return None


def _qlfilter_status(raw, row_num):
    try:
        return QLFilterStatus(raw)
    except ValueError:
        print(f"  [ERROR] row {row_num}: unknown qlfilter_status '{raw}'")
        return None


def _instance_status(raw, row_num):
    try:
        return InstanceStatus(raw)
    except ValueError:
        print(f"  [ERROR] row {row_num}: unknown instance status '{raw}'")
        return None


def _apply(obj, kwargs):
    for k, v in kwargs.items():
        if hasattr(obj, k):
            setattr(obj, k, v)


def load_hosts(path, update):
    counts = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
    with open(path, newline='') as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            name = row.get('name', '').strip()
            if not name:
                continue

            status_raw = _opt(row.get('status', '')) or 'active'
            status = _host_status(status_raw, i)
            if status is None:
                counts['errors'] += 1
                continue

            qlf_raw = _opt(row.get('qlfilter_status', ''))
            qlf_status = None
            if qlf_raw:
                qlf_status = _qlfilter_status(qlf_raw, i)
                if qlf_status is None:
                    counts['errors'] += 1
                    continue

            existing = get_host_by_name(name)
            if existing and not update:
                print(f"  [SKIPPED] {name} (host)")
                counts['skipped'] += 1
                continue

            kwargs = {
                'name': name,
                'provider': row.get('provider', '').strip(),
                'ip_address': _opt(row.get('ip_address', '')),
                'region': _opt(row.get('region', '')),
                'machine_size': _opt(row.get('machine_size', '')),
                'is_standalone': _bool(row.get('is_standalone', 'false')),
                'ssh_user': _opt(row.get('ssh_user', '')) or 'ansible',
                'ssh_port': int(row.get('ssh_port', '22') or '22'),
                'ssh_key_path': _opt(row.get('ssh_key_path', '')),
                'os_type': _opt(row.get('os_type', '')),
                'timezone': _opt(row.get('timezone', '')),
                'status': status,
                'qlfilter_status': qlf_status,
                'auto_restart_schedule': _opt(row.get('auto_restart_schedule', '')),
                'workspace_name': _opt(row.get('workspace_name', '')),
            }

            if existing:
                _apply(existing, kwargs)
                db.session.commit()
                print(f"  [UPDATED] {name} (host)")
                counts['updated'] += 1
            else:
                host = Host(**kwargs)
                db.session.add(host)
                db.session.commit()
                print(f"  [CREATED] {name} (host)")
                counts['created'] += 1
    return counts


def load_instances(path, update):
    counts = {'created': 0, 'updated': 0, 'skipped': 0, 'errors': 0}
    with open(path, newline='') as f:
        for i, row in enumerate(csv.DictReader(f), start=2):
            name = row.get('name', '').strip()
            if not name:
                continue

            host_name = row.get('host_name', '').strip()
            host = get_host_by_name(host_name)
            if not host:
                print(f"  [ERROR] row {i}: host '{host_name}' not found for instance '{name}'")
                counts['errors'] += 1
                continue

            status_raw = _opt(row.get('status', '')) or 'idle'
            status = _instance_status(status_raw, i)
            if status is None:
                counts['errors'] += 1
                continue

            existing = get_instance_by_name(name)
            if existing and not update:
                print(f"  [SKIPPED] {name} (instance)")
                counts['skipped'] += 1
                continue

            kwargs = {
                'name': name,
                'host_id': host.id,
                'port': int(row.get('port', '').strip()),
                'hostname': row.get('hostname', '').strip(),
                'lan_rate_enabled': _bool(row.get('lan_rate_enabled', 'false')),
                'qlx_plugins': _opt(row.get('qlx_plugins', '')),
                'zmq_rcon_port': _int_opt(row.get('zmq_rcon_port', '')),
                'zmq_rcon_password': _opt(row.get('zmq_rcon_password', '')),
                'zmq_stats_port': _int_opt(row.get('zmq_stats_port', '')),
                'zmq_stats_password': _opt(row.get('zmq_stats_password', '')),
                'status': status,
                'config': _opt(row.get('config', '')),
            }

            if existing:
                _apply(existing, kwargs)
                db.session.commit()
                print(f"  [UPDATED] {name} (instance)")
                counts['updated'] += 1
            else:
                inst = QLInstance(**kwargs)
                db.session.add(inst)
                db.session.commit()
                print(f"  [CREATED] {name} (instance)")
                counts['created'] += 1
    return counts


def clear_all():
    count_i = QLInstance.query.count()
    count_h = Host.query.count()
    QLInstance.query.delete()
    Host.query.delete()
    db.session.commit()
    print(f"  Cleared {count_i} instance(s) and {count_h} host(s).")


def main():
    parser = argparse.ArgumentParser(description='Seed QLSM dev database from CSV files.')
    parser.add_argument('--hosts', metavar='PATH', help='Path to hosts CSV')
    parser.add_argument('--instances', metavar='PATH', help='Path to instances CSV')
    parser.add_argument('--clear', action='store_true', help='Delete all instances and hosts before seeding')
    parser.add_argument('--update', action='store_true', help='Update existing records instead of skipping')
    args = parser.parse_args()

    if not args.hosts and not args.instances:
        parser.print_help()
        sys.exit(1)

    app = create_app()
    with app.app_context():
        if args.clear:
            print('Clearing existing data...')
            clear_all()

        all_results = {}

        if args.hosts:
            print(f'Seeding hosts from {args.hosts}...')
            all_results['hosts'] = load_hosts(args.hosts, args.update)

        if args.instances:
            print(f'Seeding instances from {args.instances}...')
            all_results['instances'] = load_instances(args.instances, args.update)

        print('\nSummary:')
        for entity, r in all_results.items():
            print(f'  {entity}: {r["created"]} created, {r["updated"]} updated, '
                  f'{r["skipped"]} skipped, {r["errors"]} error(s)')


if __name__ == '__main__':
    main()
