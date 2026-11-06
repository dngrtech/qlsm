"""Addon discovery, load-failure isolation, override precedence, hook gating.

The single most important property here is that no addon can take qlsm down:
a bad manifest, an import that raises, a register() that throws, a hook that
blows up mid-deploy -- each must be contained and visible, never fatal.
"""
import json
import os
import textwrap
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from ui import db
from ui.addons import registry
from ui.models import Host, HostStatus, QLInstance


def write_addon(base, addon_id, manifest=None, backend=None):
    """Create an addon directory under `base` and return its path."""
    root = os.path.join(str(base), addon_id)
    os.makedirs(os.path.join(root, 'ui'), exist_ok=True)
    payload = {'id': addon_id, 'version': '1.0.0'}
    if manifest is not None:
        payload = manifest
    with open(os.path.join(root, 'qlsm-addon.json'), 'w', encoding='utf-8') as f:
        if isinstance(payload, str):
            f.write(payload)          # raw text, for the malformed-JSON case
        else:
            json.dump(payload, f)
    if backend is not None:
        with open(os.path.join(root, 'backend.py'), 'w', encoding='utf-8') as f:
            f.write(textwrap.dedent(backend))
    return root


@pytest.fixture
def addon_app(tmp_path, monkeypatch):
    """An app whose only addon source is a temp dir we control.

    The bundled `addons/` directory is pointed at an empty temp dir too, so
    this never picks up a real addon that happens to be in the repo.
    """
    import tempfile

    from ui import create_app

    packages = tmp_path / 'addon-packages'
    packages.mkdir()
    bundled = tmp_path / 'bundled'
    bundled.mkdir()

    monkeypatch.setattr(
        registry, '_candidate_dirs',
        lambda app: [(str(bundled), 'bundled'), (str(app.config['ADDON_PACKAGES_DIR']), 'installed')],
    )

    db_fd, db_path = tempfile.mkstemp()
    built = []

    def _build():
        app = create_app({
            'TESTING': True,
            'SECRET_KEY': 'test-secret-key',
            'JWT_SECRET_KEY': 'test-jwt-secret-key',
            'JWT_COOKIE_CSRF_PROTECT': False,
            'JWT_TOKEN_LOCATION': ['headers', 'cookies'],
            'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
            'SQLALCHEMY_TRACK_MODIFICATIONS': False,
            'SERVER_NAME': 'test.server',
            'RCON_ENABLED': False,
            'ADDON_PACKAGES_DIR': str(packages),
        })
        with app.app_context():
            db.create_all()
        built.append(app)
        return app

    yield _build, packages, bundled

    # Dispose every engine before unlinking, the same way tests/conftest.py
    # does -- on Windows an open SQLite handle makes os.unlink fail outright.
    for app in built:
        with app.app_context():
            db.session.remove()
            db.engine.dispose()

    os.close(db_fd)
    for path in (db_path, f'{db_path}-wal', f'{db_path}-shm'):
        if os.path.exists(path):
            os.unlink(path)


# ---- discovery --------------------------------------------------------

def test_addon_with_manifest_only_loads(addon_app):
    build, packages, _ = addon_app
    write_addon(packages, 'ui-only')
    app = build()
    addon = registry.get_addon('ui-only', app)
    assert addon.loaded is True
    assert addon.errors == []


def test_directory_without_a_manifest_is_not_an_addon(addon_app):
    build, packages, _ = addon_app
    os.makedirs(os.path.join(str(packages), 'just-a-folder'))
    app = build()
    assert registry.get_addons(app) == {}


def test_register_is_called_and_can_add_a_blueprint(addon_app):
    build, packages, _ = addon_app
    write_addon(packages, 'with-api', backend='''
        from flask import Blueprint, jsonify

        bp = Blueprint('with_api', __name__)

        @bp.route('/ping')
        def ping():
            return jsonify({"data": {"pong": True}})

        def register(ctx):
            ctx.blueprint(bp)
    ''')
    app = build()
    assert registry.get_addon('with-api', app).loaded is True
    rules = [str(r) for r in app.url_map.iter_rules()]
    assert '/api/addons/with-api/ping' in rules


# ---- failure isolation ------------------------------------------------

def test_malformed_manifest_does_not_break_startup(addon_app):
    build, packages, _ = addon_app
    write_addon(packages, 'broken-json', manifest='{ not json')
    write_addon(packages, 'healthy')
    app = build()                       # must not raise
    assert registry.get_addon('healthy', app).loaded is True
    broken = registry.get_addon('broken-json', app)
    assert broken.loaded is False
    assert broken.errors


def test_backend_that_raises_on_import_is_contained(addon_app):
    build, packages, _ = addon_app
    write_addon(packages, 'explodes', backend='raise RuntimeError("boom")')
    write_addon(packages, 'healthy')
    app = build()
    assert registry.get_addon('healthy', app).loaded is True
    bad = registry.get_addon('explodes', app)
    assert bad.loaded is False
    assert any('boom' in e for e in bad.errors)


def test_register_that_raises_is_contained(addon_app):
    build, packages, _ = addon_app
    write_addon(packages, 'bad-register', backend='''
        def register(ctx):
            raise ValueError("nope")
    ''')
    app = build()
    bad = registry.get_addon('bad-register', app)
    assert bad.loaded is False
    assert any('nope' in e for e in bad.errors)


def test_broken_addon_is_still_listed_in_the_catalog(addon_app):
    """Silently disappearing is a worse failure than showing the error."""
    build, packages, _ = addon_app
    write_addon(packages, 'explodes', backend='raise RuntimeError("boom")')
    app = build()
    with app.app_context():
        entry = next(a for a in registry.catalog() if a['id'] == 'explodes')
    assert entry['loaded'] is False
    assert entry['errors']


def test_catalog_entry_defaults_to_disabled(addon_app):
    """The whole-addon on/off switch starts off until an operator flips it."""
    build, packages, _ = addon_app
    write_addon(packages, 'ui-only')
    app = build()
    with app.app_context():
        entry = next(a for a in registry.catalog() if a['id'] == 'ui-only')
    assert entry['enabled'] is False


def test_catalog_entry_reflects_the_global_enable_switch(addon_app):
    build, packages, _ = addon_app
    write_addon(packages, 'ui-only')
    app = build()
    with app.app_context():
        registry.get_addon('ui-only').ctx.settings.set_enabled('global', 0, True)
        entry = next(a for a in registry.catalog() if a['id'] == 'ui-only')
    assert entry['enabled'] is True


def test_addon_declaring_a_future_ui_api_loads_but_is_not_mountable(addon_app):
    build, packages, _ = addon_app
    write_addon(packages, 'from-the-future',
                manifest={'id': 'from-the-future', 'version': '1.0.0', 'ui_api': 99})
    app = build()
    addon = registry.get_addon('from-the-future', app)
    assert addon.loaded is True          # backend still works
    assert addon.mountable_ui is False   # components withheld


def test_addon_declaring_an_older_ui_api_still_mounts(addon_app):
    """The bundled examples all track CURRENT_UI_API, so nothing else in the
    tree proves an addon written against an older contract keeps working."""
    build, packages, _ = addon_app
    write_addon(packages, 'from-the-past',
                manifest={'id': 'from-the-past', 'version': '1.0.0', 'ui_api': 1})
    app = build()
    addon = registry.get_addon('from-the-past', app)
    assert addon.loaded is True
    assert addon.mountable_ui is True


def test_a_validator_crash_is_contained_instead_of_killing_startup(addon_app, monkeypatch):
    """read_manifest() is contracted never to raise. If a bug ever breaks that
    contract, the scan runs inside create_app(), so without this guard one
    malformed third-party addon stops qlsm from starting at all."""
    build, packages, _ = addon_app
    write_addon(packages, 'exploding-manifest')
    write_addon(packages, 'innocent-addon')

    real = registry.read_manifest

    def _boom(root):
        if root.endswith('exploding-manifest'):
            raise TypeError('unhashable type: something')
        return real(root)

    monkeypatch.setattr(registry, 'read_manifest', _boom)

    app = build()
    broken = registry.get_addon('exploding-manifest', app)
    assert broken is not None
    assert broken.loaded is False
    assert any('manifest could not be read' in e for e in broken.errors)
    # the rest of the catalog is unaffected
    assert registry.get_addon('innocent-addon', app).loaded is True


# ---- precedence -------------------------------------------------------

def test_installed_copy_overrides_the_bundled_one(addon_app):
    build, packages, bundled = addon_app
    write_addon(bundled, 'sample-addon',
                manifest={'id': 'sample-addon', 'version': '1.0.0'})
    write_addon(packages, 'sample-addon',
                manifest={'id': 'sample-addon', 'version': '2.0.0'})
    app = build()
    addon = registry.get_addon('sample-addon', app)
    assert addon.source == 'installed'
    assert addon.manifest['version'] == '2.0.0'


def test_bundled_addon_is_used_when_nothing_overrides_it(addon_app):
    build, _, bundled = addon_app
    write_addon(bundled, 'sample-addon')
    app = build()
    assert registry.get_addon('sample-addon', app).source == 'bundled'


# ---- hooks ------------------------------------------------------------

HOOK_BACKEND = '''
    def register(ctx):
        @ctx.on('instance.launch_args')
        def args(instance_id):
            return ['+set qlx_addonMarker 1']
'''


@pytest.fixture
def hook_app(addon_app):
    build, packages, _ = addon_app
    write_addon(packages, 'hooky',
                manifest={'id': 'hooky', 'version': '1.0.0',
                          'scopes': ['global', 'host', 'instance']},
                backend=HOOK_BACKEND)
    app = build()
    with app.app_context():
        host = Host(name='germany', ip_address='10.0.0.1', provider='vultr',
                    status=HostStatus.ACTIVE)
        db.session.add(host)
        db.session.flush()
        instance = QLInstance(name='duel', port=27960, hostname='duel', host_id=host.id)
        db.session.add(instance)
        db.session.commit()
        yield app, host.id, instance.id


def test_hook_is_not_dispatched_while_the_addon_is_disabled(hook_app):
    app, _, instance_id = hook_app
    assert registry.dispatch('instance.launch_args', instance_id, instance_id) == []


def test_hook_fires_once_every_layer_is_enabled(hook_app):
    app, host_id, instance_id = hook_app
    settings = registry.get_addon('hooky').ctx.settings
    settings.set_enabled('global', 0, True)
    settings.set_enabled('host', host_id, True)
    settings.set_enabled('instance', instance_id, True)
    assert registry.dispatch('instance.launch_args', instance_id, instance_id) == [
        '+set qlx_addonMarker 1'
    ]


def test_hook_stops_firing_when_the_host_layer_is_switched_off(hook_app):
    app, host_id, instance_id = hook_app
    settings = registry.get_addon('hooky').ctx.settings
    for scope, sid in (('global', 0), ('host', host_id), ('instance', instance_id)):
        settings.set_enabled(scope, sid, True)
    settings.set_enabled('host', host_id, False)
    assert registry.dispatch('instance.launch_args', instance_id, instance_id) == []


def test_a_raising_hook_cannot_abort_the_operation(addon_app):
    """An addon decorating a deploy must not be able to fail that deploy."""
    build, packages, _ = addon_app
    write_addon(packages, 'angry', manifest={'id': 'angry', 'version': '1.0.0'}, backend='''
        def register(ctx):
            @ctx.on('backup.export')
            def boom():
                raise RuntimeError("hook exploded")
    ''')
    write_addon(packages, 'calm', manifest={'id': 'calm', 'version': '1.0.0'}, backend='''
        def register(ctx):
            @ctx.on('backup.export')
            def trees():
                return ['addon-packages/calm']
    ''')
    app = build()
    with app.app_context():
        # backup.export is ungated (HOOK_SCOPES None), so both are attempted
        assert registry.dispatch('backup.export') == ['addon-packages/calm']


def test_an_addon_owned_list_hook_is_flattened_not_nested(addon_app):
    """demo_management.file_kinds is a contribution hook: a handler returning
    a list of extensions must come back out of dispatch() as those same
    extensions, not as a one-element list wrapping the list. A hook declared
    in HOOK_SCOPES but left out of LIST_HOOKS fails exactly that way, and a
    consumer iterating the result per string then drops every contribution
    without an error anywhere."""
    build, packages, _ = addon_app
    write_addon(packages, 'packer', manifest={'id': 'packer', 'version': '1.0.0'}, backend='''
        def register(ctx):
            @ctx.on('demo_management.file_kinds')
            def kinds():
                return ['pack', 'packer.log']
    ''')
    app = build()
    with app.app_context():
        registry.get_addon('packer').ctx.settings.set_enabled('global', 0, True)
        assert registry.dispatch('demo_management.file_kinds', 0) == ['pack', 'packer.log']


def test_unknown_hook_name_raises_at_registration(addon_app):
    build, packages, _ = addon_app
    write_addon(packages, 'typo', backend='''
        def register(ctx):
            ctx.on('instance.lunch_args', lambda: None)
    ''')
    app = build()
    bad = registry.get_addon('typo', app)
    assert bad.loaded is False
    assert any('unknown hook' in e for e in bad.errors)


def test_dispatch_rejects_an_unknown_hook_name(addon_app):
    build, _, _ = addon_app
    app = build()
    with app.app_context():
        with pytest.raises(ValueError):
            registry.dispatch('instance.nonexistent', 1)


# ---- context path safety ----------------------------------------------

def test_ctx_path_refuses_to_escape_the_addon_directory(addon_app):
    build, packages, _ = addon_app
    write_addon(packages, 'nosy')
    app = build()
    ctx = registry.get_addon('nosy', app).ctx
    assert ctx.path('ui', 'panel.js').startswith(os.path.abspath(ctx.root_dir))
    with pytest.raises(ValueError):
        ctx.path('..', '..', 'terraform', 'ssh-keys')


def _slow_tick_app(addon_app):
    build, packages, _ = addon_app
    write_addon(packages, 'sluggish', manifest={'id': 'sluggish', 'version': '1.0.0'}, backend='''
        def register(ctx):
            @ctx.on('poller.tick')
            def tick():
                return 'ticked'
    ''')
    return build()


def _dispatch_tick(app, readings):
    """Dispatch poller.tick with monotonic() returning `readings`; returns the
    warnings the registry logged."""
    ticks = iter(readings)
    with app.app_context():
        registry.get_addon('sluggish').ctx.settings.set_enabled('global', 0, True)
        with patch('ui.addons.registry.time', SimpleNamespace(monotonic=lambda: next(ticks))),                 patch.object(registry.log, 'warning') as warning:
            assert registry.dispatch('poller.tick') == ['ticked']
    return warning


def test_a_slow_poller_tick_handler_is_logged_by_addon_id(addon_app):
    # monotonic() is read before and after the handler: 12s apart
    warning = _dispatch_tick(_slow_tick_app(addon_app), [100.0, 112.0])
    warning.assert_called_once()
    message = warning.call_args.args[0] % warning.call_args.args[1:]
    assert message.startswith('Addon sluggish hook poller.tick handler took 12.0s')


def test_a_fast_poller_tick_handler_logs_no_warning(addon_app):
    warning = _dispatch_tick(_slow_tick_app(addon_app), [100.0, 100.5])
    warning.assert_not_called()


# ---- dispatch_each ------------------------------------------------------

def test_dispatch_each_gives_every_addon_its_own_arguments(addon_app):
    """instance.created carries per-addon input (an add-instance tab's
    values): each addon must see its own part, never another addon's."""
    build, packages, _ = addon_app
    for addon_id in ('alpha', 'beta'):
        write_addon(packages, addon_id, manifest={'id': addon_id, 'version': '1.0.0'}, backend='''
            def register(ctx):
                @ctx.on('instance.created')
                def created(instance_id, options):
                    return (ctx.addon_id, instance_id, options)
        ''')
    app = build()
    options = {'alpha': {'token': 'a-secret'}, 'beta': {'on': True}}
    with app.app_context():
        results = registry.dispatch_each(
            'instance.created', 7, lambda addon_id: ((7, options.get(addon_id, {})), {}),
        )
    assert results == [('alpha', 7, {'token': 'a-secret'}), ('beta', 7, {'on': True})]


def test_dispatch_by_addon_pairs_each_result_with_its_addon(addon_app):
    build, packages, _ = addon_app
    for addon_id in ('alpha', 'beta'):
        write_addon(packages, addon_id, manifest={'id': addon_id, 'version': '1.0.0'}, backend='''
            def register(ctx):
                @ctx.on('preset.keep_cvars')
                def keep(instance):
                    return [ctx.addon_id + "_cvar", "second"]
        ''')
    write_addon(packages, 'angry', manifest={'id': 'angry', 'version': '1.0.0'}, backend='''
        def register(ctx):
            @ctx.on('preset.keep_cvars')
            def boom(instance):
                raise RuntimeError("hook exploded")
    ''')
    app = build()
    with app.app_context(), patch.object(registry, '_gates_open', return_value=True):
        results = registry.dispatch_by_addon('preset.keep_cvars', 1, object())
    assert results == [('alpha', ['alpha_cvar', 'second']), ('beta', ['beta_cvar', 'second'])]


def test_dispatch_each_reports_a_raising_handler_and_carries_on(addon_app):
    build, packages, _ = addon_app
    write_addon(packages, 'angry', manifest={'id': 'angry', 'version': '1.0.0'}, backend='''
        def register(ctx):
            @ctx.on('instance.created')
            def boom(instance_id, options):
                raise RuntimeError("hook exploded")
    ''')
    write_addon(packages, 'calm', manifest={'id': 'calm', 'version': '1.0.0'}, backend='''
        def register(ctx):
            @ctx.on('instance.created')
            def fine(instance_id, options):
                return 'ok'
    ''')
    app = build()
    failed = []
    with app.app_context():
        results = registry.dispatch_each(
            'instance.created', 1, lambda addon_id: ((1, {}), {}),
            on_error=lambda addon_id, exc: failed.append((addon_id, str(exc))),
        )
    assert results == ['ok']
    assert failed == [('angry', 'hook exploded')]


def test_instance_created_fires_for_a_globally_disabled_addon(addon_app):
    """Ungated on purpose: a new instance has no instance-layer row yet, and
    whether to switch itself on for it is the addon's own decision."""
    build, packages, _ = addon_app
    write_addon(packages, 'quiet', manifest={'id': 'quiet', 'version': '1.0.0'}, backend='''
        def register(ctx):
            @ctx.on('instance.created')
            def created(instance_id, options):
                return instance_id
    ''')
    app = build()
    with app.app_context():
        assert registry.get_addon('quiet').globally_enabled is False
        assert registry.dispatch('instance.created', 3, 3, {}) == [3]
