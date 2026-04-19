import {
  canEnableLanRate,
  getLanRateUnsupportedReason,
  isLanRateSupported,
  UNKNOWN_99K_LAN_RATE_MESSAGE,
} from '../lanRateCompatibility';
import { describe, expect, it } from 'vitest';

describe('lanRateCompatibility', () => {
  it('supports debian', () => {
    expect(isLanRateSupported('debian')).toBe(true);
    expect(canEnableLanRate({ osType: 'debian', currentEnabled: false })).toBe(true);
  });

  it('blocks enabling on ubuntu', () => {
    expect(isLanRateSupported('ubuntu')).toBe(false);
    expect(canEnableLanRate({ osType: 'ubuntu', currentEnabled: false })).toBe(false);
    expect(getLanRateUnsupportedReason('ubuntu')).toBe('99k LAN rate is not compatible with Ubuntu.');
  });

  it('allows disabling a legacy enabled ubuntu instance', () => {
    expect(canEnableLanRate({ osType: 'ubuntu', currentEnabled: true })).toBe(true);
  });

  it('treats unknown or missing os types as unsupported', () => {
    expect(isLanRateSupported(null)).toBe(false);
    expect(isLanRateSupported(undefined)).toBe(false);
    expect(isLanRateSupported('centos')).toBe(false);
    expect(canEnableLanRate({ osType: null, currentEnabled: false })).toBe(false);
    expect(getLanRateUnsupportedReason(null)).toBe(UNKNOWN_99K_LAN_RATE_MESSAGE);
    expect(getLanRateUnsupportedReason('centos')).toBe(UNKNOWN_99K_LAN_RATE_MESSAGE);
  });
});
