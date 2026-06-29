import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import PresetLoadTab from '../PresetLoadTab';

const presets = [
  { id: 1, name: 'duel-cfg', description: 'Comp duel', is_builtin: false },
  { id: 2, name: 'no-desc', description: '', is_builtin: false },
  { id: 3, name: 'stock', description: 'builtin', is_builtin: true },
];

describe('PresetLoadTab', () => {
  it('renders rows with description fallback', () => {
    render(<PresetLoadTab presets={presets} isLoading={false} selectedId={null} onSelect={vi.fn()} onRequestDelete={vi.fn()} onDownload={vi.fn()} />);
    expect(screen.getByText('duel-cfg')).toBeInTheDocument();
    expect(screen.getByText('No description')).toBeInTheDocument();
  });

  it('calls onSelect when a row is clicked', () => {
    const onSelect = vi.fn();
    render(<PresetLoadTab presets={presets} isLoading={false} selectedId={null} onSelect={onSelect} onRequestDelete={vi.fn()} onDownload={vi.fn()} />);
    fireEvent.click(screen.getByText('duel-cfg'));
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it('disables delete for builtin presets', () => {
    render(<PresetLoadTab presets={presets} isLoading={false} selectedId={3} onSelect={vi.fn()} onRequestDelete={vi.fn()} onDownload={vi.fn()} />);
    const deleteBtn = screen.getByRole('button', { name: /delete stock/i });
    expect(deleteBtn).toBeDisabled();
  });

  it('shows empty state when no presets', () => {
    render(<PresetLoadTab presets={[]} isLoading={false} selectedId={null} onSelect={vi.fn()} onRequestDelete={vi.fn()} onDownload={vi.fn()} />);
    expect(screen.getByText(/no presets available/i)).toBeInTheDocument();
  });
});
