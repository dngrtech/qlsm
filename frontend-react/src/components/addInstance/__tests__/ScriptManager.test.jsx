import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ScriptManager from '../ScriptManager/ScriptManager';

const BINARY_FILE = {
  name: 'foo.so',
  path: 'plugins/foo.so',
  file_type: 'binary',
  type: 'file',
  size: 16,
  last_modified: 1,
};

const mocks = vi.hoisted(() => ({
  selectFile: null,
  binaryDetailsProps: null,
}));

vi.mock('../ScriptManager/PluginFileTree', () => ({
  default: ({ onSelectFile }) => {
    mocks.selectFile = () => onSelectFile(BINARY_FILE);
    return (
      <button type="button" onClick={mocks.selectFile}>
        Select File
      </button>
    );
  },
}));

vi.mock('../ScriptManager/BinaryDetailsPanel', () => ({
  default: (props) => {
    mocks.binaryDetailsProps = props;
    return (
      <div>
        <div data-testid="binary-description">{props.description}</div>
        <div data-testid="description-save-state">
          {props.onDescriptionSave ? 'enabled' : 'hidden'}
        </div>
        <button
          type="button"
          onClick={() => props.onDescriptionSave?.('Saved description')}
        >
          Save Description
        </button>
        <button
          type="button"
          onClick={() => props.onReplace(new File(['elf'], 'foo.so', { type: 'application/octet-stream' }))}
        >
          Replace Binary
        </button>
        <button type="button" onClick={props.onDelete}>
          Delete Binary
        </button>
      </div>
    );
  },
}));

vi.mock('../ScriptManager/TextFileEditor', () => ({
  default: () => null,
}));

vi.mock('../ScriptManager/NewScriptModal', () => ({
  default: () => null,
}));

function renderScriptManager(overrides = {}) {
  const props = {
    tree: [BINARY_FILE],
    onTreeRefresh: vi.fn(),
    readContent: vi.fn(),
    writeContent: vi.fn(),
    upload: vi.fn(),
    deleteFile: vi.fn().mockResolvedValue(undefined),
    checkable: false,
    checkedFiles: new Set(),
    onCheck: vi.fn(),
    loading: false,
    error: null,
    ...overrides,
  };
  return render(<ScriptManager {...props} />);
}

describe('ScriptManager binary file handling', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.selectFile = null;
    mocks.binaryDetailsProps = null;
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('does not delete the selected file when the replacement uploads to the same path', async () => {
    const upload = vi.fn().mockResolvedValue({ path: 'plugins/foo.so' });
    const deleteFile = vi.fn().mockResolvedValue(undefined);

    renderScriptManager({ upload, deleteFile });

    fireEvent.click(screen.getByRole('button', { name: /select file/i }));
    await waitFor(() => expect(screen.getByRole('button', { name: /replace binary/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /replace binary/i }));

    await waitFor(() => expect(upload).toHaveBeenCalledWith(expect.any(File), 'plugins'));
    expect(deleteFile).not.toHaveBeenCalled();
  });

  it('fetches and passes binary description when a .so file is selected', async () => {
    const getBinaryMeta = vi.fn().mockResolvedValue({ description: 'Speed hook' });

    renderScriptManager({ getBinaryMeta, saveBinaryMeta: vi.fn() });

    fireEvent.click(screen.getByRole('button', { name: /select file/i }));

    await waitFor(() => expect(getBinaryMeta).toHaveBeenCalledWith('plugins/foo.so'));
    await waitFor(() => {
      expect(screen.getByTestId('binary-description')).toHaveTextContent('Speed hook');
    });
    expect(mocks.binaryDetailsProps.onDescriptionSave).toEqual(expect.any(Function));
  });

  it('saves binary description for the selected .so file', async () => {
    const saveBinaryMeta = vi.fn().mockResolvedValue({ description: 'Saved description' });

    renderScriptManager({
      getBinaryMeta: vi.fn().mockResolvedValue({ description: '' }),
      saveBinaryMeta,
    });

    fireEvent.click(screen.getByRole('button', { name: /select file/i }));
    await waitFor(() => {
      expect(mocks.binaryDetailsProps.onDescriptionSave).toEqual(expect.any(Function));
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
    renderScriptManager();

    fireEvent.click(screen.getByRole('button', { name: /select file/i }));

    await waitFor(() => expect(mocks.binaryDetailsProps.onDescriptionSave).toBeNull());
    expect(screen.getByTestId('description-save-state')).toHaveTextContent('hidden');
  });

  it('clears selected binary details after deleting a .so file', async () => {
    const deleteFile = vi.fn().mockResolvedValue(undefined);

    renderScriptManager({
      getBinaryMeta: vi.fn().mockResolvedValue({ description: 'Temporary hook' }),
      saveBinaryMeta: vi.fn(),
      deleteFile,
    });

    fireEvent.click(screen.getByRole('button', { name: /select file/i }));
    await waitFor(() => {
      expect(screen.getByTestId('binary-description')).toHaveTextContent('Temporary hook');
    });

    fireEvent.click(screen.getByRole('button', { name: /delete binary/i }));

    await waitFor(() => expect(deleteFile).toHaveBeenCalledWith('plugins/foo.so'));
    expect(screen.getByText(/select a file to view or edit/i)).toBeInTheDocument();
    expect(screen.queryByText('Temporary hook')).not.toBeInTheDocument();
  });
});
