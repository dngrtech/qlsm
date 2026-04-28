import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import BinaryDetailsPanel from '../ScriptManager/BinaryDetailsPanel';

const BASE_PROPS = {
  filePath: 'plugins/hook.so',
  fileName: 'hook.so',
  size: 16800,
  lastModified: 1743340050,
  onReplace: vi.fn(),
  onDelete: vi.fn(),
  isDeleting: false,
  description: '',
  onDescriptionSave: null,
};

describe('BinaryDetailsPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders file name and metadata', () => {
    render(<BinaryDetailsPanel {...BASE_PROPS} />);
    expect(screen.getByText('hook.so')).toBeInTheDocument();
    expect(screen.getByText('Native shared library (.so)')).toBeInTheDocument();
  });

  it('does not render description input when onDescriptionSave is null', () => {
    render(<BinaryDetailsPanel {...BASE_PROPS} onDescriptionSave={null} />);
    expect(screen.queryByPlaceholderText(/short label/i)).not.toBeInTheDocument();
  });

  it('renders description input when onDescriptionSave is provided', () => {
    render(<BinaryDetailsPanel {...BASE_PROPS} onDescriptionSave={vi.fn()} />);
    expect(screen.getByPlaceholderText(/short label/i)).toBeInTheDocument();
  });

  it('shows the current description value in the input', () => {
    render(
      <BinaryDetailsPanel
        {...BASE_PROPS}
        description="Speed hook"
        onDescriptionSave={vi.fn()}
      />,
    );
    expect(screen.getByPlaceholderText(/short label/i)).toHaveValue('Speed hook');
  });

  it('calls onDescriptionSave with trimmed value on blur', () => {
    const onDescriptionSave = vi.fn();
    render(<BinaryDetailsPanel {...BASE_PROPS} onDescriptionSave={onDescriptionSave} />);
    const input = screen.getByPlaceholderText(/short label/i);
    fireEvent.change(input, { target: { value: '  trimmed  ' } });
    fireEvent.blur(input);
    expect(onDescriptionSave).toHaveBeenCalledWith('trimmed');
  });

  it('does not save when the trimmed value did not change', () => {
    const onDescriptionSave = vi.fn();
    render(
      <BinaryDetailsPanel
        {...BASE_PROPS}
        description="Speed hook"
        onDescriptionSave={onDescriptionSave}
      />,
    );
    const input = screen.getByPlaceholderText(/short label/i);
    fireEvent.change(input, { target: { value: '  Speed hook  ' } });
    fireEvent.blur(input);
    expect(onDescriptionSave).not.toHaveBeenCalled();
  });

  it('calls onDescriptionSave with trimmed value on Enter', () => {
    const onDescriptionSave = vi.fn();
    render(<BinaryDetailsPanel {...BASE_PROPS} onDescriptionSave={onDescriptionSave} />);
    const input = screen.getByPlaceholderText(/short label/i);
    fireEvent.change(input, { target: { value: 'my label' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onDescriptionSave).toHaveBeenCalledWith('my label');
  });

  it('shows validation error and does not save when description exceeds 100 chars', () => {
    const onDescriptionSave = vi.fn();
    render(<BinaryDetailsPanel {...BASE_PROPS} onDescriptionSave={onDescriptionSave} />);
    const input = screen.getByPlaceholderText(/short label/i);
    fireEvent.change(input, { target: { value: 'x'.repeat(101) } });
    fireEvent.blur(input);
    expect(onDescriptionSave).not.toHaveBeenCalled();
    expect(screen.getByText(/max 100/i)).toBeInTheDocument();
  });

  it.each(['<', '>', '{', '}', '"'])(
    'shows validation error and does not save when description contains "%s"',
    (char) => {
      const onDescriptionSave = vi.fn();
      render(<BinaryDetailsPanel {...BASE_PROPS} onDescriptionSave={onDescriptionSave} />);
      const input = screen.getByPlaceholderText(/short label/i);
      fireEvent.change(input, { target: { value: `bad ${char} char` } });
      fireEvent.blur(input);
      expect(onDescriptionSave).not.toHaveBeenCalled();
      expect(screen.getByText(/cannot contain/i)).toBeInTheDocument();
    },
  );

  it('shows character counter when input is focused', () => {
    render(
      <BinaryDetailsPanel
        {...BASE_PROPS}
        description="hi"
        onDescriptionSave={vi.fn()}
      />,
    );
    const input = screen.getByPlaceholderText(/short label/i);
    fireEvent.focus(input);
    expect(screen.getByText('2/100')).toBeInTheDocument();
  });

  it('reverts to original description on Escape', () => {
    render(
      <BinaryDetailsPanel
        {...BASE_PROPS}
        description="original"
        onDescriptionSave={vi.fn()}
      />,
    );
    const input = screen.getByPlaceholderText(/short label/i);
    fireEvent.change(input, { target: { value: 'changed' } });
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(input).toHaveValue('original');
  });

  it('syncs description prop when filePath changes', () => {
    const { rerender } = render(
      <BinaryDetailsPanel
        {...BASE_PROPS}
        description="first"
        onDescriptionSave={vi.fn()}
      />,
    );
    expect(screen.getByPlaceholderText(/short label/i)).toHaveValue('first');

    rerender(
      <BinaryDetailsPanel
        {...BASE_PROPS}
        filePath="plugins/other.so"
        fileName="other.so"
        description="second"
        onDescriptionSave={vi.fn()}
      />,
    );
    expect(screen.getByPlaceholderText(/short label/i)).toHaveValue('second');
  });
});
