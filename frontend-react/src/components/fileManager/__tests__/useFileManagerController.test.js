import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useFileManagerController } from '../useFileManagerController';

function createAdapter(tree) {
  return {
    tree,
    readContent: vi.fn().mockResolvedValue('content'),
    writeContent: vi.fn().mockResolvedValue(undefined),
    upload: vi.fn(),
    deleteFile: vi.fn(),
    renameFile: vi.fn(),
    loading: false,
    error: null,
  };
}

function createSerializableAdapter(files) {
  return {
    tree: Object.keys(files).map(path => ({ name: path, path, type: 'file' })),
    readContent: vi.fn(path => Promise.resolve(files[path] || '')),
    writeContent: vi.fn().mockResolvedValue(undefined),
    upload: vi.fn(),
    deleteFile: vi.fn(),
    renameFile: vi.fn(),
    serialize: () => ({ ...files }),
    loading: false,
    error: null,
  };
}

describe('useFileManagerController initial selection', () => {
  it('does not auto-select unchecked files in checkable managers', async () => {
    const adapter = createAdapter([
      { name: 'ca.factories', path: 'ca.factories', type: 'file' },
    ]);

    const { result } = renderHook(() => useFileManagerController({
      adapter,
      capabilities: { allowedExtensions: ['.factories'] },
      checkable: true,
      checkedFiles: new Set(),
    }));

    await waitFor(() => expect(result.current.selectedFile).toBeNull());
    expect(adapter.readContent).not.toHaveBeenCalled();
  });

  it('selects the first checked file according to checked-first alphabetical order', async () => {
    const adapter = createAdapter([
      { name: 'zeta.py', path: 'zeta.py', type: 'file' },
      { name: 'bravo.py', path: 'bravo.py', type: 'file' },
      { name: 'alpha.py', path: 'alpha.py', type: 'file' },
    ]);

    const { result } = renderHook(() => useFileManagerController({
      adapter,
      capabilities: { allowedExtensions: ['.py'] },
      checkable: true,
      checkedFiles: new Set(['bravo.py', 'alpha.py']),
    }));

    await waitFor(() => expect(result.current.selectedFile?.path).toBe('alpha.py'));
  });

  it('moves selection when the active file is not in the next adapter tree', async () => {
    const configAdapter = createAdapter([
      { name: 'server.cfg', path: 'server.cfg', type: 'file' },
    ]);
    const pluginAdapter = createAdapter([
      { name: 'balance.py', path: 'balance.py', type: 'file' },
    ]);

    const { result, rerender } = renderHook(
      ({ adapter, checkable, checkedFiles, defaultSelectedPath }) => useFileManagerController({
        adapter,
        capabilities: { allowedExtensions: ['.cfg', '.py'] },
        checkable,
        checkedFiles,
        defaultSelectedPath,
      }),
      {
        initialProps: {
          adapter: configAdapter,
          checkable: false,
          checkedFiles: new Set(),
          defaultSelectedPath: 'server.cfg',
        },
      },
    );

    await waitFor(() => expect(result.current.selectedFile?.path).toBe('server.cfg'));

    rerender({
      adapter: pluginAdapter,
      checkable: true,
      checkedFiles: new Set(['balance.py']),
      defaultSelectedPath: null,
    });

    await waitFor(() => expect(result.current.selectedFile?.path).toBe('balance.py'));
  });

  it('does not re-check locally created adapter-managed factories from the server', async () => {
    const setChecked = vi.fn().mockRejectedValue(new Error('server file missing'));
    const adapter = {
      tree: [],
      readContent: vi.fn().mockResolvedValue(''),
      writeContent: vi.fn().mockResolvedValue(undefined),
      upload: vi.fn(),
      deleteFile: vi.fn(),
      renameFile: vi.fn(),
      setChecked,
      loading: false,
      error: null,
    };

    const { result } = renderHook(() => useFileManagerController({
      adapter,
      capabilities: {
        allowedExtensions: ['.factories'],
        newFileTemplate: () => '{\n  \n}',
      },
      checkable: true,
      checkedFiles: new Set(),
      onCheck: setChecked,
    }));

    await act(async () => {
      await result.current.handleCreate('new.factories');
    });

    expect(adapter.writeContent).toHaveBeenCalledWith('new.factories', '{\n  \n}');
    expect(setChecked).not.toHaveBeenCalled();
    expect(result.current.actionError).toBeNull();
    expect(result.current.selectedFile?.path).toBe('new.factories');
  });

  it('refreshes the selected editor when adapter content changes externally', async () => {
    const { result, rerender } = renderHook(
      ({ files }) => useFileManagerController({
        adapter: createSerializableAdapter(files),
        capabilities: { allowedExtensions: ['.cfg'] },
        defaultSelectedPath: 'server.cfg',
      }),
      {
        initialProps: {
          files: {
            'server.cfg': 'set sv_hostname "Old"',
          },
        },
      },
    );

    await waitFor(() => expect(result.current.currentContent).toBe('set sv_hostname "Old"'));

    rerender({
      files: {
        'server.cfg': 'set sv_hostname "New"',
      },
    });

    await waitFor(() => expect(result.current.currentContent).toBe('set sv_hostname "New"'));
  });
});
