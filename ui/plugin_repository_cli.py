"""`flask seed-plugin-repositories`: register the plugin repositories a fresh
QLSM install lists under Settings -> Plugin Repositories.

Listing only -- nothing is downloaded into the plugin pool. entrypoint.sh
runs this on first-run database init only, so a repository the operator
deletes stays deleted across restarts.
"""
import click
from flask import current_app
from flask.cli import with_appcontext

from ui import db
from ui.models import PluginRepository
# The same sync the Add Repository route runs, so a seeded repository is
# stored exactly as if the operator had added it by hand.
from ui.routes.plugin_repository_routes import _repo_urls, _sync

DEFAULT_PLUGIN_REPOSITORIES = (
    ('Doomsday\'s Plugins Repository', 'https://github.com/D00MSDAYDEVICE/minqlx'),
)


def seed_plugin_repositories(repositories=None):
    """Add each (name, url) not already present by name or URL. A repository
    whose first sync fails is still added, carrying the error; the Sync
    button retries the GitHub resolution. Returns the names added."""
    added = []
    for name, url in (DEFAULT_PLUGIN_REPOSITORIES if repositories is None else repositories):
        existing = PluginRepository.query.all()
        if any(r.name.lower() == name.lower() or url.rstrip('/') in _repo_urls(r) for r in existing):
            continue
        repo = PluginRepository(name=name, url=url)
        ok, error = _sync(repo, resolve=True)
        repo.display_url = url if repo.url != url else None
        if not ok:
            current_app.logger.warning(f"Seeded plugin repository '{name}' failed its first sync: {error}")
        db.session.add(repo)
        db.session.commit()
        added.append(name)
    return added


@click.command('seed-plugin-repositories')
@with_appcontext
def seed_plugin_repositories_command():
    """Register the default plugin repositories."""
    added = seed_plugin_repositories()
    if added:
        click.echo(f"Added plugin repositories: {', '.join(added)}")
    else:
        click.echo('Default plugin repositories already present.')


def register_plugin_repository_commands(app):
    app.cli.add_command(seed_plugin_repositories_command)
