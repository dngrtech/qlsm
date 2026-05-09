import { renderHook, act } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { useStateAdapter } from '../adapters/useStateAdapter';

const opts = {
  initialFiles: { 'server.cfg': '' },
  allowedExtensions: ['.cfg', '.txt', '.ent'],
  protectedFiles: ['server.cfg'],
};

describe('useStateAdapter folders', () => {
  it('createFolder adds to folder set and serializes', () => {
    const { result } = renderHook(() => useStateAdapter(opts));
    act(() => { result.current.createFolder('extras'); });
    expect(result.current.tree.some(i => i.type === 'folder' && i.name === 'extras')).toBe(true);
    const { folders } = result.current.serialize();
    expect(folders).toContain('extras');
  });

  it('createFolder rejects duplicates and reserved names', () => {
    const { result } = renderHook(() => useStateAdapter({
      ...opts,
      reservedFolderNames: ['scripts'],
    }));
    act(() => { result.current.createFolder('extras'); });
    expect(() => { result.current.createFolder('extras'); }).toThrow();
    expect(() => { result.current.createFolder('scripts'); }).toThrow();
  });

  it('deleteFolder removes folder and child files', async () => {
    const { result } = renderHook(() => useStateAdapter(opts));
    act(() => { result.current.createFolder('extras'); });
    await act(async () => { await result.current.writeContent('extras/a.ent', '// a'); });
    act(() => { result.current.deleteFolder('extras'); });
    expect(result.current.tree.some(i => i.type === 'folder' && i.name === 'extras')).toBe(false);
    const { files } = result.current.serialize();
    expect(files['extras/a.ent']).toBeUndefined();
  });

  it('renameFolder rewrites child paths', async () => {
    const { result } = renderHook(() => useStateAdapter(opts));
    act(() => { result.current.createFolder('old'); });
    await act(async () => { await result.current.writeContent('old/x.cfg', 'data'); });
    act(() => { result.current.renameFolder('old', 'new'); });
    const { files, folders } = result.current.serialize();
    expect(files['new/x.cfg']).toBe('data');
    expect(files['old/x.cfg']).toBeUndefined();
    expect(folders).toContain('new');
    expect(folders).not.toContain('old');
  });
});
