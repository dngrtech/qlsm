import { render, screen } from '@testing-library/react';
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
