import {
  canEnableLanRate,
  isLanRateForcedOn,
  isLanRateSupported,
  getLanRateUnsupportedMessage,
} from '../lanRateCompatibility';
import { describe, expect, it } from 'vitest';

describe('lanRateCompatibility (legacy API)', () => {
  it('supports debian', () => {
    expect(isLanRateSupported({ os_type: 'debian', lan_rate_uses_hook: false })).toBe(true);
    expect(canEnableLanRate({ host: { os_type: 'debian', lan_rate_uses_hook: false }, currentEnabled: false })).toBe(true);
  });

  it('supports legacy debian12 host records', () => {
    expect(isLanRateSupported({ os_type: 'debian12', lan_rate_uses_hook: false })).toBe(true);
    expect(canEnableLanRate({ host: { os_type: 'debian12', lan_rate_uses_hook: false }, currentEnabled: false })).toBe(true);
    expect(getLanRateUnsupportedMessage({ os_type: 'debian12', lan_rate_uses_hook: false })).toBe('');
  });

  it('blocks enabling on ubuntu', () => {
    expect(isLanRateSupported({ os_type: 'ubuntu', lan_rate_uses_hook: false })).toBe(false);
    expect(canEnableLanRate({ host: { os_type: 'ubuntu', lan_rate_uses_hook: false }, currentEnabled: false })).toBe(false);
    expect(getLanRateUnsupportedMessage({ os_type: 'ubuntu', lan_rate_uses_hook: false })).toMatch(/Re-run Host Setup/);
  });

  it('allows disabling a legacy enabled ubuntu instance', () => {
    expect(canEnableLanRate({ host: { os_type: 'ubuntu', lan_rate_uses_hook: false }, currentEnabled: true })).toBe(true);
  });

  it('treats unknown or missing os types as unsupported', () => {
    expect(isLanRateSupported({ os_type: null, lan_rate_uses_hook: false })).toBe(false);
    expect(isLanRateSupported({ os_type: undefined, lan_rate_uses_hook: false })).toBe(false);
    expect(isLanRateSupported({ os_type: 'centos', lan_rate_uses_hook: false })).toBe(false);
    expect(canEnableLanRate({ host: { os_type: null, lan_rate_uses_hook: false }, currentEnabled: false })).toBe(false);
    expect(getLanRateUnsupportedMessage({ os_type: null, lan_rate_uses_hook: false })).toMatch(/Re-run Host Setup/);
    expect(getLanRateUnsupportedMessage({ os_type: 'centos', lan_rate_uses_hook: false })).toMatch(/Re-run Host Setup/);
  });
});

describe('isLanRateSupported (migration-aware)', () => {
  it('returns true for a migrated host regardless of OS', () => {
    expect(isLanRateSupported({ os_type: 'ubuntu', lan_rate_uses_hook: true })).toBe(true);
    expect(isLanRateSupported({ os_type: 'centos', lan_rate_uses_hook: true })).toBe(true);
  });

  it('returns true for a legacy Debian host', () => {
    expect(isLanRateSupported({ os_type: 'debian', lan_rate_uses_hook: false })).toBe(true);
  });

  it('returns false for a legacy Ubuntu host', () => {
    expect(isLanRateSupported({ os_type: 'ubuntu', lan_rate_uses_hook: false })).toBe(false);
  });
});

describe('getLanRateUnsupportedMessage', () => {
  it('returns empty string for a migrated host', () => {
    expect(getLanRateUnsupportedMessage({ os_type: 'ubuntu', lan_rate_uses_hook: true })).toBe('');
  });

  it('returns empty string for a supported legacy host', () => {
    expect(getLanRateUnsupportedMessage({ os_type: 'debian', lan_rate_uses_hook: false })).toBe('');
  });

  it('returns actionable text for a legacy Ubuntu host', () => {
    const msg = getLanRateUnsupportedMessage({ os_type: 'ubuntu', lan_rate_uses_hook: false });
    expect(msg).toMatch(/Re-run Host Setup/);
    expect(msg).toMatch(/host actions menu/);
  });
});

// Mirrors the minqlxtended block in tests/test_lan_rate_policy.py. QLSM runs
// these hosts at 99k and does not offer 25k there, so every surface must render
// the toggle on and locked to match the cvar the backend emits.
describe('minqlxtended hosts (99k fixed on by QLSM)', () => {
  const host = { os_type: 'ubuntu', lan_rate_uses_hook: true, runtime: 'minqlxtended' };

  it('reports 99k LAN rate as fixed on', () => {
    expect(isLanRateForcedOn(host)).toBe(true);
  });

  it('still counts as supported so nothing offers to fix it', () => {
    expect(isLanRateSupported(host)).toBe(true);
    expect(canEnableLanRate({ host, currentEnabled: false })).toBe(true);
  });

  it('explains the QLSM policy rather than an engine behaviour', () => {
    const msg = getLanRateUnsupportedMessage(host);
    expect(msg).toMatch(/QLSM runs minqlxtended hosts at 99k LAN rate/);
    expect(msg).toMatch(/does not offer 25k/);
  });

  it('leaves minqlx hosts alone', () => {
    expect(isLanRateForcedOn({ ...host, runtime: 'minqlx' })).toBe(false);
    expect(isLanRateForcedOn({ ...host, runtime: undefined })).toBe(false);
    expect(isLanRateForcedOn(null)).toBe(false);
    expect(getLanRateUnsupportedMessage({ ...host, runtime: 'minqlx' })).toBe('');
  });
});
