import { describe, expect, it } from 'vitest';

import { resolveDocPath } from '../resolveDocPath';

describe('resolveDocPath', () => {
  const articlePath = '/docs/getting-started/introduction.md';

  it('returns external http(s) URLs unchanged', () => {
    expect(resolveDocPath('https://example.com/x', articlePath)).toBe('https://example.com/x');
    expect(resolveDocPath('http://example.com/x', articlePath)).toBe('http://example.com/x');
  });

  it('returns protocol-relative URLs unchanged', () => {
    expect(resolveDocPath('//cdn.example.com/x.png', articlePath)).toBe('//cdn.example.com/x.png');
  });

  it('returns already-absolute /docs/... paths unchanged', () => {
    expect(resolveDocPath('/docs/images/foo.png', articlePath)).toBe('/docs/images/foo.png');
  });

  it('resolves ../ relative paths against the article folder', () => {
    expect(
      resolveDocPath('../features/qlfilter.md', articlePath)
    ).toBe('/docs/features/qlfilter.md');
  });

  it('resolves images one level up', () => {
    expect(
      resolveDocPath('../images/qlsm-self-deployment.png', articlePath)
    ).toBe('/docs/images/qlsm-self-deployment.png');
  });

  it('resolves ./ same-folder paths', () => {
    expect(
      resolveDocPath('./add-host.md', articlePath)
    ).toBe('/docs/getting-started/add-host.md');
  });

  it('resolves bare filename (same folder)', () => {
    expect(
      resolveDocPath('add-host.md', articlePath)
    ).toBe('/docs/getting-started/add-host.md');
  });

  it('collapses double traversal', () => {
    const deeper = '/docs/operations/sub/foo.md';
    expect(
      resolveDocPath('../../images/x.png', deeper)
    ).toBe('/docs/images/x.png');
  });

  it('returns empty string unchanged', () => {
    expect(resolveDocPath('', articlePath)).toBe('');
  });

  it('returns undefined unchanged', () => {
    expect(resolveDocPath(undefined, articlePath)).toBe(undefined);
  });

  it('preserves in-page anchors on absolute paths', () => {
    expect(
      resolveDocPath('/docs/features/qlfilter.md#setup', articlePath)
    ).toBe('/docs/features/qlfilter.md#setup');
  });

  it('preserves in-page anchors on relative paths', () => {
    expect(
      resolveDocPath('../features/qlfilter.md#setup', articlePath)
    ).toBe('/docs/features/qlfilter.md#setup');
  });
});
