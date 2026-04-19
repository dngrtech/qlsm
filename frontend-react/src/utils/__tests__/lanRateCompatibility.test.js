import {
  canEnableLanRate,
  getLanRateUnsupportedReason,
  isLanRateSupported,
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
});
