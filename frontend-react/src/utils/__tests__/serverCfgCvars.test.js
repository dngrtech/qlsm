import { describe, expect, it } from 'vitest';

import { parseCvarValue, readCvarFromConfig, serializeCvarValue, upsertCvarInConfig } from '../serverCfgCvars';

describe('readCvarFromConfig', () => {
  it('reads the current value of a set line', () => {
    const cfg = 'set sv_hostname "My Server"\nset qlx_chatRconEnabled "1"\n';
    expect(readCvarFromConfig(cfg, 'qlx_chatRconEnabled')).toBe('1');
  });

  it('returns null when the cvar is not present', () => {
    expect(readCvarFromConfig('set sv_hostname "x"', 'qlx_missing')).toBeNull();
  });

  it('returns null for empty/undefined config text', () => {
    expect(readCvarFromConfig('', 'qlx_foo')).toBeNull();
    expect(readCvarFromConfig(undefined, 'qlx_foo')).toBeNull();
  });

  it('treats the cvar name as a literal, not a regex', () => {
    const cfg = 'set qlx_foo.bar "1"\n';
    expect(readCvarFromConfig(cfg, 'qlx_fooXbar')).toBeNull();
    expect(readCvarFromConfig(cfg, 'qlx_foo.bar')).toBe('1');
  });
});

describe('upsertCvarInConfig', () => {
  it('appends a new set line when the cvar is absent', () => {
    expect(upsertCvarInConfig('set sv_hostname "x"', 'qlx_foo', '1')).toBe('set sv_hostname "x"\nset qlx_foo "1"');
  });

  it('starts a fresh line when config text is empty', () => {
    expect(upsertCvarInConfig('', 'qlx_foo', '1')).toBe('set qlx_foo "1"');
  });

  it('replaces an existing set line in place', () => {
    const cfg = 'set sv_hostname "x"\nset qlx_foo "0"\nset sv_maxclients "16"';
    expect(upsertCvarInConfig(cfg, 'qlx_foo', '1')).toBe('set sv_hostname "x"\nset qlx_foo "1"\nset sv_maxclients "16"');
  });

  it('does not treat a $-containing value as a replacement backreference', () => {
    const cfg = 'set qlx_foo "0"';
    expect(upsertCvarInConfig(cfg, 'qlx_foo', '$1 not a group')).toBe('set qlx_foo "$1 not a group"');
  });
});

describe('serializeCvarValue', () => {
  it('serializes bool as 1/0', () => {
    expect(serializeCvarValue('bool', true)).toBe('1');
    expect(serializeCvarValue('bool', false)).toBe('0');
  });

  it('serializes number/string via String()', () => {
    expect(serializeCvarValue('number', 5)).toBe('5');
    expect(serializeCvarValue('string', 'abc')).toBe('abc');
  });

  it('serializes a nullish value as an empty string', () => {
    expect(serializeCvarValue('string', null)).toBe('');
    expect(serializeCvarValue('number', undefined)).toBe('');
  });
});

describe('parseCvarValue', () => {
  it('parses bool from "1"/"0" and true/false strings', () => {
    expect(parseCvarValue('bool', '1')).toBe(true);
    expect(parseCvarValue('bool', '0')).toBe(false);
    expect(parseCvarValue('bool', 'true')).toBe(true);
    expect(parseCvarValue('bool', 'false')).toBe(false);
  });

  it('parses a finite number', () => {
    expect(parseCvarValue('number', '5')).toBe(5);
  });

  it('returns null for a non-finite number', () => {
    expect(parseCvarValue('number', 'not-a-number')).toBeNull();
  });

  it('returns the raw string for type "string"', () => {
    expect(parseCvarValue('string', 'a,b,c')).toBe('a,b,c');
  });

  it('returns null for null/undefined input', () => {
    expect(parseCvarValue('bool', null)).toBeNull();
    expect(parseCvarValue('number', undefined)).toBeNull();
  });
});

describe('configs written by hand', () => {
  it('reads a value that was left unquoted', () => {
    expect(readCvarFromConfig('set g_gravity 800\n', 'g_gravity')).toBe('800');
  });

  it('reads a seta line', () => {
    expect(readCvarFromConfig('seta qlx_foo "2"\n', 'qlx_foo')).toBe('2');
  });

  it('rewrites an unquoted line instead of appending a second one', () => {
    const cfg = 'set g_gravity 800\nset sv_hostname "x"';
    expect(upsertCvarInConfig(cfg, 'g_gravity', '1200')).toBe('set g_gravity "1200"\nset sv_hostname "x"');
  });

  it('keeps the seta keyword and the indentation of the line it rewrites', () => {
    expect(upsertCvarInConfig('  seta qlx_foo "1"', 'qlx_foo', '0')).toBe('  seta qlx_foo "0"');
  });
});
