import { render, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import FileTreeRowMenu from '../FileTreeRowMenu';

const CAPS = { canCreateFolder: true, allowedExtensions: ['.cfg', '.txt'] };

describe('FileTreeRowMenu folder upload', () => {
  it('marks the folder upload input as multiple', () => {
    const { container } = render(
      <FileTreeRowMenu itemType="folder" capabilities={CAPS} onUploadToFolder={vi.fn()} />,
    );
    const input = container.querySelector('input[type="file"]');
    expect(input).not.toBeNull();
    expect(input.multiple).toBe(true);
  });

  it('passes all selected files to onUploadToFolder', () => {
    const onUploadToFolder = vi.fn();
    const { container } = render(
      <FileTreeRowMenu itemType="folder" capabilities={CAPS} onUploadToFolder={onUploadToFolder} />,
    );
    const input = container.querySelector('input[type="file"]');
    const files = [new File(['a'], 'a.cfg'), new File(['b'], 'b.cfg')];
    fireEvent.change(input, { target: { files } });
    expect(onUploadToFolder).toHaveBeenCalledTimes(1);
    const arg = onUploadToFolder.mock.calls[0][0];
    expect(Array.from(arg).map(f => f.name)).toEqual(['a.cfg', 'b.cfg']);
  });
});
