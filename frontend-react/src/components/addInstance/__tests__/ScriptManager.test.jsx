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
  default: ({ onReplace }) => (
    <button
      type="button"
      onClick={() => onReplace(new File(['elf'], 'foo.so', { type: 'application/octet-stream' }))}
    >
      Replace Binary
    </button>
  ),
}));

vi.mock('../ScriptManager/TextFileEditor', () => ({
  default: () => null,
}));

vi.mock('../ScriptManager/NewScriptModal', () => ({
  default: () => null,
}));

describe('ScriptManager replace flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('does not delete the selected file when the replacement uploads to the same path', async () => {
    const upload = vi.fn().mockResolvedValue({ path: 'plugins/foo.so' });
    const deleteFile = vi.fn().mockResolvedValue(undefined);

    render(
      <ScriptManager
        tree={[BINARY_FILE]}
        onTreeRefresh={vi.fn()}
        readContent={vi.fn()}
        writeContent={vi.fn()}
        upload={upload}
        deleteFile={deleteFile}
        checkable={false}
        checkedFiles={new Set()}
        onCheck={vi.fn()}
        loading={false}
        error={null}
      />
    );

    fireEvent.click(screen.getByRole('button', { name: /select file/i }));
    await waitFor(() => expect(screen.getByRole('button', { name: /replace binary/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /replace binary/i }));

    await waitFor(() => expect(upload).toHaveBeenCalledWith(expect.any(File), 'plugins'));
    expect(deleteFile).not.toHaveBeenCalled();
  });
});
