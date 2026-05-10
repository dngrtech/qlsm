import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import NewFileModal from '../NewFileModal';

describe('NewFileModal', () => {
  it('focuses the filename input when opened in file mode', async () => {
    render(
      <NewFileModal
        isOpen
        onClose={vi.fn()}
        onCreate={vi.fn()}
        allowedExtensions={['.cfg']}
      />,
    );

    const input = screen.getByRole('textbox', { name: /filename/i });

    await waitFor(() => expect(input).toHaveFocus());
  });

  it('focuses the folder name input when opened in folder mode', async () => {
    render(
      <NewFileModal
        isOpen
        onClose={vi.fn()}
        onCreate={vi.fn()}
        mode="folder"
      />,
    );

    const input = screen.getByRole('textbox', { name: /folder name/i });

    await waitFor(() => expect(input).toHaveFocus());
  });
});
