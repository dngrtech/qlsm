import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useStateAdapter } from '../useStateAdapter';

describe('useStateAdapter', () => {
  it('exposes initial files in tree', () => {
    const { result } = renderHook(() => useStateAdapter({
      initialFiles: { 'server.cfg': 'a', 'custom.cfg': 'b' },
      protectedFiles: ['server.cfg'],
      allowedExtensions: ['.cfg'],
    }));

    const names = result.current.tree.map(t => t.name).sort();
    expect(names).toEqual(['custom.cfg', 'server.cfg']);
    expect(result.current.tree.find(t => t.name === 'server.cfg').protected).toBe(true);
    expect(result.current.tree.find(t => t.name === 'custom.cfg').protected).toBe(false);
  });

  it('writeContent updates a file and flips hasChanges', async () => {
    const { result } = renderHook(() => useStateAdapter({
      initialFiles: { 'a.cfg': 'orig' },
      allowedExtensions: ['.cfg'],
    }));

    expect(result.current.hasChanges).toBe(false);
    await act(async () => {
      await result.current.writeContent('a.cfg', 'modified');
    });

    expect(await result.current.readContent('a.cfg')).toBe('modified');
    expect(result.current.hasChanges).toBe(true);
  });

  it('deleteFile removes from tree but blocks protected files', async () => {
    const { result } = renderHook(() => useStateAdapter({
      initialFiles: { 'a.cfg': '', 'server.cfg': '' },
      protectedFiles: ['server.cfg'],
      allowedExtensions: ['.cfg'],
    }));

    await act(async () => {
      await result.current.deleteFile('a.cfg');
    });
    expect(result.current.tree.map(t => t.name)).toEqual(['server.cfg']);

    await expect(result.current.deleteFile('server.cfg')).rejects.toThrow();
  });

  it('renameFile renames and blocks protected files', async () => {
    const { result } = renderHook(() => useStateAdapter({
      initialFiles: { 'old.cfg': 'data', 'server.cfg': '' },
      protectedFiles: ['server.cfg'],
      allowedExtensions: ['.cfg'],
    }));

    await act(async () => {
      await result.current.renameFile('old.cfg', 'new.cfg');
    });

    expect(result.current.tree.map(t => t.name).sort()).toEqual(['new.cfg', 'server.cfg']);
    expect(await result.current.readContent('new.cfg')).toBe('data');
    await expect(result.current.renameFile('server.cfg', 'renamed.cfg')).rejects.toThrow();
  });

  it('serialize returns current files', () => {
    const { result } = renderHook(() => useStateAdapter({
      initialFiles: { 'a.cfg': '1', 'b.cfg': '2' },
      allowedExtensions: ['.cfg'],
    }));

    expect(result.current.serialize()).toEqual({ 'a.cfg': '1', 'b.cfg': '2' });
  });

  it('upload adds a new file', async () => {
    const { result } = renderHook(() => useStateAdapter({
      initialFiles: {},
      allowedExtensions: ['.cfg'],
    }));
    const fakeFile = new File(['hello'], 'new.cfg');

    await act(async () => {
      await result.current.upload(fakeFile);
    });

    expect(result.current.tree.map(t => t.name)).toEqual(['new.cfg']);
    expect(await result.current.readContent('new.cfg')).toBe('hello');
  });

  it('shows serverTree files unchecked and fetches content when checked', async () => {
    const readServerContent = vi.fn().mockResolvedValue('{"factory": true}');
    const { result } = renderHook(() => useStateAdapter({
      initialFiles: {},
      serverTree: [{ name: 'ca.factories', path: 'ca.factories', type: 'file' }],
      readServerContent,
      allowedExtensions: ['.factories'],
    }));

    expect(result.current.tree.map(t => t.name)).toEqual(['ca.factories']);
    expect(result.current.checkedFiles.has('ca.factories')).toBe(false);

    await act(async () => {
      await result.current.setChecked('ca.factories', true);
    });

    expect(readServerContent).toHaveBeenCalledWith('ca.factories');
    expect(result.current.serialize()).toEqual({ 'ca.factories': '{"factory": true}' });
    expect(result.current.checkedFiles.has('ca.factories')).toBe(true);

    await act(async () => {
      await result.current.setChecked('ca.factories', false);
    });

    expect(result.current.serialize()).toEqual({});
  });
});
