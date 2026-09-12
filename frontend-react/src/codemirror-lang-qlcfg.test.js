import { EditorState } from '@codemirror/state';
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  commandCompletionOptions,
  createQlCfgLinter,
  cvarCompletionOptions,
  registerPluginCvarProvider,
  setCvarCatalog,
  stripManagedCvars,
} from './codemirror-lang-qlcfg';

// Stands in for GET /api/cvar-catalog (ui/data/ql_cvar_catalog.json).
const CATALOG = {
  sources: { 'server.cfg': "the game's own annotated example server.cfg", naming: 'read off the cvar name' },
  commands: [
    { name: 'condump', description: 'Dumps all buffered console text to a file.' },
    { name: 'cvar_restart', description: 'Restarts the cvar subsystem.' },
  ],
  gametypes: ['ca', 'duel'],
  cvars: [
    { name: 'g_respawn_delay_min', group: 'gameplay', description: 'Lower bound.', source: 'server.cfg' },
    { name: 'sv_hostname', group: 'server', description: 'Server name.', source: 'server.cfg' },
    { name: 'g_startingWeapons', group: 'gameplay', description: 'Weapon bitmask.', source: 'factories' },
  ],
};

const unregisters = [];
afterEach(() => {
  while (unregisters.length) unregisters.pop()();
});

function withPlugins(cvars) {
  unregisters.push(registerPluginCvarProvider(() => cvars));
}

function lint(doc) {
  const onLintResults = vi.fn();
  const diagnostics = createQlCfgLinter([], onLintResults)({
    state: EditorState.create({ doc }),
  });

  return { diagnostics, onLintResults };
}

describe('createQlCfgLinter', () => {
  it('does not report qlx_serverBrandName as managed', () => {
    const { diagnostics, onLintResults } = lint('set qlx_serverBrandName "Custom Brand"');

    expect(diagnostics).toEqual([]);
    expect(onLintResults).toHaveBeenCalledWith(false);
  });

  it('still reports managed cvars as ignored', () => {
    const { diagnostics } = lint('set net_ip "192.0.2.1"');

    expect(diagnostics).toEqual([
      expect.objectContaining({
        severity: 'info',
        message: 'This cvar will be ignored. Forced to "" by the app (binds all interfaces, required for 99k LAN rate).',
      }),
    ]);
  });

  it('reports a managed cvar written with seta as well', () => {
    const { diagnostics } = lint('seta net_ip "192.0.2.1"');

    expect(diagnostics).toHaveLength(1);
    expect(diagnostics[0].severity).toBe('info');
  });
});

describe('commandCompletionOptions', () => {
  it('offers the commands served by the catalog', () => {
    setCvarCatalog(CATALOG);
    const labels = commandCompletionOptions('dump').map((o) => o.label);
    expect(labels).toContain('condump');
  });

  it('matches regardless of the case of the typed text or the command name', () => {
    setCvarCatalog(CATALOG);
    const labels = commandCompletionOptions('RESTART').map((o) => o.label);
    expect(labels).toContain('cvar_restart');
  });
});

describe('cvarCompletionOptions', () => {
  it('offers the cvars served by the catalog, not a list baked into the bundle', () => {
    setCvarCatalog({ cvars: [], commands: [], sources: {} });
    expect(cvarCompletionOptions('respawn_delay')).toHaveLength(0);

    setCvarCatalog(CATALOG);
    const labels = cvarCompletionOptions('respawn_delay').map((o) => o.label);
    expect(labels).toContain('g_respawn_delay_min');
  });

  it('matches a substring anywhere in the cvar name, not just the prefix', () => {
    setCvarCatalog(CATALOG);
    const labels = cvarCompletionOptions('rate').map((o) => o.label);
    expect(labels).toContain('sv_lanforcerate');
  });

  it('matches regardless of the case of the typed text or the cvar name', () => {
    setCvarCatalog(CATALOG);
    const labels = cvarCompletionOptions('LAN').map((o) => o.label);
    expect(labels).toContain('sv_lanforcerate');
  });

  it('takes qlx cvars from the plugins of this server', () => {
    setCvarCatalog(CATALOG);
    expect(cvarCompletionOptions('qlx_lobby').map((o) => o.label)).toHaveLength(0);

    withPlugins([{ cvar: 'qlx_lobbyEnabled', plugin: 'Lobby', enabled: true, description: 'on/off', type: 'bool' }]);
    const option = cvarCompletionOptions('qlx_lobby')[0];
    expect(option.label).toBe('qlx_lobbyEnabled');
    expect(option.detail).toContain('Lobby');
  });

  it('puts the enabled plugins first, then the ones merely present, then engine cvars', () => {
    setCvarCatalog(CATALOG);
    withPlugins([
      { cvar: 'qlx_offBrand', plugin: 'Branding', enabled: false },
      { cvar: 'qlx_onBrand', plugin: 'Lobby', enabled: true },
    ]);

    const labels = cvarCompletionOptions('').map((o) => o.label);
    expect(labels.indexOf('qlx_onBrand')).toBeLessThan(labels.indexOf('qlx_offBrand'));
    expect(labels.indexOf('qlx_offBrand')).toBeLessThan(labels.indexOf('g_respawn_delay_min'));
  });

  it('says where each description came from', () => {
    setCvarCatalog(CATALOG);
    const option = cvarCompletionOptions('sv_hostname')[0];
    const info = option.info();
    expect(info.textContent).toContain('Server name.');
    expect(info.textContent).toContain("the game's own annotated example server.cfg");
  });
});

describe('stripManagedCvars', () => {
  it('preserves qlx_serverBrandName values', () => {
    const cfg = [
      'set qlx_serverBrandName "Custom Brand"',
      'set net_ip "192.0.2.1"',
    ].join('\n');

    expect(stripManagedCvars(cfg)).toBe([
      'set qlx_serverBrandName "Custom Brand"',
      'set net_ip ""',
    ].join('\n'));
  });
});
