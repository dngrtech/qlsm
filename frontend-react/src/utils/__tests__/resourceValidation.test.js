import { describe, expect, it } from 'vitest';

import { validateHostName } from '../resourceValidation';

describe('validateHostName', () => {
  it('rejects host names that contain only digits', () => {
    expect(validateHostName('234234')).toBe('Host name cannot contain only digits.');
  });

  it('allows host names that include letters', () => {
    expect(validateHostName('host-234234')).toBeNull();
  });
});
