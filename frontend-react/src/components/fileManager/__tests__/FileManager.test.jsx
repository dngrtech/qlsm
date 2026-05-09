import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PLUGIN_CAPS } from '../capabilities';
import FileManager from '../FileManager';

const BINARY_FILE = {
  name: 'foo.so',
  path: 'plugins/foo.so',
  file_type: 'binary',
  type: 'file',
  size: 16,
  last_modified: 1,
};

const mocks = vi.hoisted(() => ({
  editorProps: null,
  rowMenuHandlers: null,
}));

vi.mock('../FileTree', () => ({
  default: ({ onSelectFile, rowMenuHandlers }) => {
    mocks.rowMenuHandlers = rowMenuHandlers;
    return (
      <button type="button" onClick={() => onSelectFile(BINARY_FILE)}>
        Select File
      </button>
    );
  },
}));

vi.mock('../FileEditorPanel', () => ({
  default: (props) => {
    mocks.editorProps = props;
    if (!props.selectedFile) return <div>Select a file to view or edit</div>;
    return (
      <div>
        <div data-testid="binary-description">{props.binaryDescription}</div>
        <div data-testid="description-save-state">
          {props.onSaveBinaryDescription ? 'enabled' : 'hidden'}
        </div>
        <button
          type="button"
          onClick={() => props.onSaveBinaryDescription?.('Saved description')}
        >
          Save Description
        </button>
        <button
          type="button"
          onClick={() => props.onReplace(new File(['elf'], 'foo.so', { type: 'application/octet-stream' }))}
        >
          Replace Binary
        </button>
      </div>
    );
  },
}));

vi.mock('../FileSidebarActions', () => ({
  default: () => null,
}));

vi.mock('../NewFileModal', () => ({
  default: () => null,
}));

vi.mock('../RenameFileModal', () => ({
  default: () => null,
}));

vi.mock('../../ConfirmationModal', () => ({
  default: ({ isOpen, onConfirm }) => (
    isOpen ? (
      <button type="button" onClick={onConfirm}>
        Confirm Delete
      </button>
    ) : null
  ),
}));

function renderFileManager(overrides = {}) {
  const adapter = {
    tree: [BINARY_FILE],
    readContent: vi.fn(),
    writeContent: vi.fn(),
    upload: vi.fn().mockResolvedValue({ path: 'plugins/foo.so' }),
    deleteFile: vi.fn().mockResolvedValue(undefined),
    renameFile: vi.fn(),
    refreshTree: vi.fn(),
    loading: false,
    error: null,
    ...overrides,
  };
  const view = render(
    <FileManager
      adapter={adapter}
      capabilities={PLUGIN_CAPS}
      getBinaryMeta={overrides.getBinaryMeta}
      saveBinaryMeta={overrides.saveBinaryMeta}
    />,
  );
  return { adapter, ...view };
}

describe('FileManager binary file handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.editorProps = null;
    mocks.rowMenuHandlers = null;
  });

  it('does not delete the selected file when replacement uploads to the same path', async () => {
    const upload = vi.fn().mockResolvedValue({ path: 'plugins/foo.so' });
    const deleteFile = vi.fn().mockResolvedValue(undefined);

    renderFileManager({ upload, deleteFile });

    fireEvent.click(screen.getByRole('button', { name: /select file/i }));
    await waitFor(() => expect(screen.getByRole('button', { name: /replace binary/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /replace binary/i }));

    await waitFor(() => expect(upload).toHaveBeenCalledWith(expect.any(File), 'plugins'));
    expect(deleteFile).not.toHaveBeenCalled();
  });

  it('fetches and passes binary description when a .so file is selected', async () => {
    const getBinaryMeta = vi.fn().mockResolvedValue({ description: 'Speed hook' });

    renderFileManager({ getBinaryMeta, saveBinaryMeta: vi.fn() });

    fireEvent.click(screen.getByRole('button', { name: /select file/i }));

    await waitFor(() => expect(getBinaryMeta).toHaveBeenCalledWith('plugins/foo.so'));
    await waitFor(() => {
      expect(screen.getByTestId('binary-description')).toHaveTextContent('Speed hook');
    });
    expect(mocks.editorProps.onSaveBinaryDescription).toEqual(expect.any(Function));
  });

  it('saves binary description for the selected .so file', async () => {
    const saveBinaryMeta = vi.fn().mockResolvedValue({ description: 'Saved description' });

    renderFileManager({
      getBinaryMeta: vi.fn().mockResolvedValue({ description: '' }),
      saveBinaryMeta,
    });

    fireEvent.click(screen.getByRole('button', { name: /select file/i }));
    await waitFor(() => {
      expect(mocks.editorProps.onSaveBinaryDescription).toEqual(expect.any(Function));
    });
    fireEvent.click(screen.getByRole('button', { name: /save description/i }));

    await waitFor(() => {
      expect(saveBinaryMeta).toHaveBeenCalledWith('plugins/foo.so', 'Saved description');
    });
    await waitFor(() => {
      expect(screen.getByTestId('binary-description')).toHaveTextContent('Saved description');
    });
  });

  it('passes null description save callback when metadata callbacks are absent', async () => {
    renderFileManager();

    fireEvent.click(screen.getByRole('button', { name: /select file/i }));

    await waitFor(() => expect(mocks.editorProps.onSaveBinaryDescription).toBeNull());
    expect(screen.getByTestId('description-save-state')).toHaveTextContent('hidden');
  });

  it('clears selected binary details after deleting a .so file', async () => {
    const deleteFile = vi.fn().mockResolvedValue(undefined);

    renderFileManager({
      getBinaryMeta: vi.fn().mockResolvedValue({ description: 'Temporary hook' }),
      saveBinaryMeta: vi.fn(),
      deleteFile,
    });

    fireEvent.click(screen.getByRole('button', { name: /select file/i }));
    await waitFor(() => {
      expect(screen.getByTestId('binary-description')).toHaveTextContent('Temporary hook');
    });

    // Trigger delete via the row menu handler (exposed through FileTree mock)
    await waitFor(() => expect(mocks.rowMenuHandlers?.onDelete).toBeDefined());
    act(() => {
      mocks.rowMenuHandlers.onDelete(BINARY_FILE);
    });

    fireEvent.click(await screen.findByRole('button', { name: /confirm delete/i }));

    await waitFor(() => expect(deleteFile).toHaveBeenCalledWith('plugins/foo.so'));
    expect(screen.getByText(/select a file to view or edit/i)).toBeInTheDocument();
    expect(screen.queryByText('Temporary hook')).not.toBeInTheDocument();
  });
});
