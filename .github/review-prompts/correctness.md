## Lens: correctness (whole stack)

Find changes that make the software behave wrongly. Look across both the Flask
backend and the React frontend, because the worst bugs here sit on the seam
between them.

Look for:
- Contract drift between layers: a field renamed, cased or typed differently on
  one side (for example `'STOPPED'` vs `'stopped'` status values, `data` vs `error`
  envelopes, null vs missing keys). For each API field the PR adds or changes,
  open both the route that produces it and the component or service that reads it.
- Status lifecycle bugs: a task that can leave a host or instance stuck in a
  transitional status (DEPLOYING, CONFIGURING and so on) on some error path, or a
  missing `db.session.commit()`.
- RQ task logic that raises instead of setting ERROR, logging with `append_log`,
  committing and returning.
- Python ↔ Ansible/Terraform mismatches: extra-vars names that don't match the
  template variables, unquoted Jinja in YAML, systemd `ExecStart` quoting.
- Migrations: a model change without an Alembic migration, or a migration that
  breaks existing rows or backups (export/import paths).
- React state: a parent passing full objects instead of IDs, so children keep
  stale data after polling (the project pattern is to pass IDs and re-derive the
  object from the master list on each render), effects with missing dependencies that cause real stale
  reads, and lists keyed by index where the order changes.
- Ordinary logic errors: off-by-one, inverted conditions, wrong variable,
  unhandled None, and races that can realistically happen (for example a worker
  vs a request handler on the same row).

Not in this lens: security issues (another finder covers them), style, naming,
and "consider adding tests".
