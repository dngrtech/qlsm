import os
import shutil

import click
from flask.cli import with_appcontext

from ui import db
from ui.builtin_presets import sync_builtin_presets_command
from ui.database import (
    create_preset,
    delete_preset,
    get_preset,
    get_preset_by_name,
    get_presets,
)
from ui.preset_support import (
    is_internal_preset_name,
    user_preset_path,
    validate_user_preset_name,
)


@click.command('add-preset')
@click.option('--name', required=True, help='Unique name for the preset (alphanumeric, hyphens, underscores only).')
@click.option('--description', default='', help='Optional description for the preset.')
@click.option('--server-cfg-path', help='Path to server.cfg file to load content.')
@click.option('--mappool-path', help='Path to mappool.txt file to load content.')
@click.option('--access-path', help='Path to access.txt file to load content.')
@click.option('--workshop-path', help='Path to workshop.txt file to load content.')
@click.option('--factory-path', help='Path to factory file (e.g., .factories) to load content.')
@with_appcontext
def add_preset_command(name, description, server_cfg_path, mappool_path, access_path, workshop_path, factory_path):
    """CLI command to add a new configuration preset."""
    is_valid, error, _ = validate_user_preset_name(name)
    if not is_valid:
        click.echo(f"Error: {error}")
        return

    preset_path = user_preset_path(name)

    def read_content(path, field_name):
        if path:
            try:
                with open(path, 'r') as handle:
                    return handle.read()
            except FileNotFoundError:
                click.echo(f"Warning: File not found for {field_name}: {path}")
            except Exception as exc:
                click.echo(f"Warning: Error reading file for {field_name} ({path}): {exc}")
        return None

    config_contents = {
        'server.cfg': read_content(server_cfg_path, 'server.cfg'),
        'mappool.txt': read_content(mappool_path, 'mappool'),
        'access.txt': read_content(access_path, 'access'),
        'workshop.txt': read_content(workshop_path, 'workshop'),
        'factory.factories': read_content(factory_path, 'factory'),
    }

    try:
        os.makedirs(preset_path, exist_ok=True)
        for filename, content in config_contents.items():
            if content:
                filepath = os.path.join(preset_path, filename)
                with open(filepath, 'w') as handle:
                    handle.write(content)
                click.echo(f"  Wrote: {filepath}")

        preset = create_preset(name=name, description=description, path=preset_path)
        click.echo(f"Preset '{preset.name}' created successfully with ID {preset.id} at {preset_path}.")
    except Exception as exc:
        if os.path.exists(preset_path):
            try:
                shutil.rmtree(preset_path)
            except Exception:
                pass
        db.session.rollback()
        click.echo(f"Error creating preset: {exc}")


@click.command('list-presets')
@with_appcontext
def list_presets_command():
    """CLI command to list all configuration presets."""
    presets = get_presets()
    if not presets:
        click.echo("No configuration presets found.")
        return

    click.echo("Available Configuration Presets:")
    for preset in presets:
        click.echo(
            f"- ID: {preset.id}, Name: {preset.name}, Path: {preset.path}, "
            f"Description: {preset.description or 'N/A'}"
        )


@click.command('delete-preset')
@click.option('--id', type=int, help='ID of the preset to delete.')
@click.option('--name', help='Name of the preset to delete.')
@with_appcontext
def delete_preset_command(id, name):
    """CLI command to delete a configuration preset by ID or name."""
    if not id and not name:
        click.echo("Error: Please provide either --id or --name.")
        return

    preset = get_preset(id) if id else get_preset_by_name(name)
    if not preset:
        if id:
            click.echo(f"Error: Preset with ID {id} not found.")
        else:
            click.echo(f"Error: Preset with name '{name}' not found.")
        return

    if preset.is_builtin:
        click.echo(f"Error: Cannot delete built-in preset '{preset.name}'.")
        return
    if is_internal_preset_name(preset.name):
        click.echo(f"Error: Cannot delete internal preset namespace '{preset.name}'.")
        return

    try:
        preset_name = preset.name
        preset_path = preset.path

        if delete_preset(preset.id):
            click.echo(f"Preset '{preset_name}' (ID: {preset.id}) deleted from database.")
            if os.path.exists(preset_path):
                shutil.rmtree(preset_path)
                click.echo(f"Deleted preset folder: {preset_path}")
            click.echo(f"Preset '{preset_name}' deleted successfully.")
        else:
            click.echo(f"Error: Failed to delete preset '{preset_name}'.")
    except Exception as exc:
        db.session.rollback()
        click.echo(f"Error deleting preset: {exc}")


def register_preset_commands(app):
    """Register preset-related CLI commands."""
    app.cli.add_command(add_preset_command)
    app.cli.add_command(list_presets_command)
    app.cli.add_command(delete_preset_command)
    app.cli.add_command(sync_builtin_presets_command)
