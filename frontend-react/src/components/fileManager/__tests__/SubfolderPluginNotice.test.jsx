import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import SubfolderPluginNotice from '../SubfolderPluginNotice';

describe('SubfolderPluginNotice', () => {
  it('renders nothing when nothing was dropped', () => {
    const { container } = render(<SubfolderPluginNotice count={0} onDismiss={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('uses singular wording for one dropped plugin', () => {
    render(<SubfolderPluginNotice count={1} onDismiss={vi.fn()} />);
    expect(screen.getByRole('status')).toHaveTextContent(
      "1 plugin that can't be enabled was deselected.",
    );
  });

  it('uses plural wording for several dropped plugins', () => {
    render(<SubfolderPluginNotice count={3} onDismiss={vi.fn()} />);
    expect(screen.getByRole('status')).toHaveTextContent(
      "3 plugins that can't be enabled were deselected.",
    );
  });

  it('explains why subfolder plugins are not enabled', () => {
    render(<SubfolderPluginNotice count={2} onDismiss={vi.fn()} />);
    expect(screen.getByRole('status')).toHaveTextContent(
      /libraries referenced by plugins in the root folder, not plugins enabled on their own/,
    );
  });

  it('calls onDismiss when the close button is clicked', () => {
    const onDismiss = vi.fn();
    render(<SubfolderPluginNotice count={2} onDismiss={onDismiss} />);
    fireEvent.click(screen.getByRole('button', { name: /dismiss/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
