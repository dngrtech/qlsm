import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import FileSidebarActions from '../FileSidebarActions';

function renderActions() {
  render(
    <FileSidebarActions
      capabilities={{
        canCreate: true,
        canUpload: false,
        canCreateFolder: false,
        allowedExtensions: ['.cfg'],
      }}
      onNewFile={vi.fn()}
      onNewFolder={vi.fn()}
      onUpload={vi.fn()}
    />,
  );
}

describe('FileSidebarActions', () => {
  it('does not show the browser focus outline on the New trigger after pointer flows', () => {
    renderActions();

    const newButton = screen.getByRole('button', { name: /new/i });

    expect(newButton).toHaveClass('focus:outline-none');
    expect(newButton.className).toContain('focus-visible:ring-2');
  });
});

const CAPS = {
  canCreate: false,
  canUpload: true,
  canCreateFolder: false,
  allowedExtensions: ['.cfg', '.txt'],
};

describe('FileSidebarActions upload', () => {
  it('marks the upload input as multiple', () => {
    render(<FileSidebarActions capabilities={CAPS} onUpload={vi.fn()} />);
    const input = document.querySelector('input[type="file"]');
    expect(input).not.toBeNull();
    expect(input.multiple).toBe(true);
  });

  it('passes all selected files to onUpload', () => {
    const onUpload = vi.fn();
    render(<FileSidebarActions capabilities={CAPS} onUpload={onUpload} />);
    const input = document.querySelector('input[type="file"]');
    const files = [new File(['a'], 'a.cfg'), new File(['b'], 'b.cfg')];
    fireEvent.change(input, { target: { files } });
    expect(onUpload).toHaveBeenCalledTimes(1);
    const arg = onUpload.mock.calls[0][0];
    expect(Array.from(arg).map(f => f.name)).toEqual(['a.cfg', 'b.cfg']);
  });
});
