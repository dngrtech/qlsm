import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { useFileManagerController } from '../useFileManagerController';
import { useStateAdapter } from '../adapters/useStateAdapter';

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
      result.current.openNewFileModal();
    });
    await act(async () => {
      await result.current.handleCreateFromModal('new.factories');
    });

    expect(adapter.writeContent).toHaveBeenCalledWith('new.factories', '{\n  \n}');
    expect(setChecked).not.toHaveBeenCalled();
    expect(result.current.actionError).toBeNull();
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

  it('downloads row menu content from the requested file', async () => {
    const createObjectURL = vi.fn(() => 'blob:test-url');
    const revokeObjectURL = vi.fn();
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    vi.stubGlobal('URL', {
      ...URL,
      createObjectURL,
      revokeObjectURL,
    });

    const adapter = createSerializableAdapter({
      'selected.cfg': 'selected content',
      'other.cfg': 'other content',
    });

    const { result } = renderHook(() => useFileManagerController({
      adapter,
      capabilities: { allowedExtensions: ['.cfg'] },
      defaultSelectedPath: 'selected.cfg',
    }));

    await waitFor(() => expect(result.current.selectedFile?.path).toBe('selected.cfg'));

    await act(async () => {
      await result.current.handleDownload({ name: 'other.cfg', path: 'other.cfg', type: 'file' });
    });

    expect(adapter.readContent).toHaveBeenCalledWith('other.cfg');
    const blob = createObjectURL.mock.calls[0][0];
    await expect(blob.text()).resolves.toBe('other content');
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:test-url');

    anchorClick.mockRestore();
    vi.unstubAllGlobals();
  });

  it('does not refetch from the server after uploading into a state adapter', async () => {
    const readServerContent = vi.fn().mockRejectedValue(new Error('404 not found'));

    const { result } = renderHook(() => {
      const adapter = useStateAdapter({
        initialFiles: {},
        serverTree: [{ name: 'ca.factories', path: 'ca.factories', type: 'file' }],
        readServerContent,
        allowedExtensions: ['.factories'],
      });
      return useFileManagerController({
        adapter,
        capabilities: { allowedExtensions: ['.factories'] },
        checkable: true,
        checkedFiles: adapter.checkedFiles,
        onCheck: adapter.setChecked,
      });
    });

    await act(async () => {
      await result.current.handleUpload(
        new File(['{"factory": true}'], 'ak.factories'),
      );
    });

    expect(result.current.actionError).toBeNull();
    expect(result.current.currentContent).toBe('{"factory": true}');
    expect(readServerContent).not.toHaveBeenCalledWith('ak.factories');
  });

  it('selects and opens the uploaded file', async () => {
    const adapter = createAdapter([]);
    adapter.upload.mockResolvedValue({ path: 'uploaded.cfg' });
    adapter.readContent.mockImplementation(path => Promise.resolve(
      path === 'uploaded.cfg' ? 'uploaded content' : '',
    ));

    const { result } = renderHook(() => useFileManagerController({
      adapter,
      capabilities: { allowedExtensions: ['.cfg'] },
    }));

    await act(async () => {
      await result.current.handleUpload(new File(['uploaded content'], 'uploaded.cfg'));
    });

    expect(adapter.upload).toHaveBeenCalledWith(expect.any(File), '');
    expect(result.current.selectedFile?.path).toBe('uploaded.cfg');
    expect(result.current.currentContent).toBe('uploaded content');
  });
});
