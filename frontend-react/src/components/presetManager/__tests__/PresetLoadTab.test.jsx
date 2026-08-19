import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import PresetLoadTab from '../PresetLoadTab';

// Headless UI v2 menus don't open under fireEvent.click in JSDOM, so render the
// menu items inline and pass the disabled flag through Menu.Item's render prop.
vi.mock('@headlessui/react', () => {
  const Menu = ({ children }) => <div>{children}</div>;
  Menu.Button = ({ children, ...props }) => <button {...props}>{children}</button>;
  Menu.Items = ({ children }) => <div>{children}</div>;
  Menu.Item = ({ children, disabled }) =>
    typeof children === 'function' ? children({ active: false, disabled }) : children;
  const Transition = ({ children }) => <>{children}</>;
  Transition.Child = ({ children }) => <>{children}</>;
  return { Menu, Transition };
});

const presets = [
  { id: 1, name: 'duel-cfg', description: 'Comp duel', is_builtin: false },
  { id: 2, name: 'no-desc', description: '', is_builtin: false },
  { id: 3, name: 'stock', description: 'builtin', is_builtin: true },
];

const noop = {
  onSelect: vi.fn(),
  onRequestDelete: vi.fn(),
  onRequestRename: vi.fn(),
  onDownload: vi.fn(),
};

describe('PresetLoadTab', () => {
  it('renders rows with description fallback', () => {
    render(<PresetLoadTab presets={presets} isLoading={false} selectedId={null} {...noop} />);
    expect(screen.getByText('duel-cfg')).toBeInTheDocument();
    expect(screen.getByText('No description')).toBeInTheDocument();
  });

  it('calls onSelect when a row is clicked', () => {
    const onSelect = vi.fn();
    render(<PresetLoadTab presets={presets} isLoading={false} selectedId={null} {...noop} onSelect={onSelect} />);
    fireEvent.click(screen.getByText('duel-cfg'));
    expect(onSelect).toHaveBeenCalledWith(1);
  });

  it('invokes download, rename, and delete from the actions menu', () => {
    const onDownload = vi.fn();
    const onRequestRename = vi.fn();
    const onRequestDelete = vi.fn();
    render(
      <PresetLoadTab
        presets={[presets[0]]}
        isLoading={false}
        selectedId={1}
        {...noop}
        onDownload={onDownload}
        onRequestRename={onRequestRename}
        onRequestDelete={onRequestDelete}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: /^download$/i }));
    expect(onDownload).toHaveBeenCalledWith(presets[0]);
    fireEvent.click(screen.getByRole('button', { name: /^rename$/i }));
    expect(onRequestRename).toHaveBeenCalledWith(presets[0]);
    fireEvent.click(screen.getByRole('button', { name: /^delete$/i }));
    expect(onRequestDelete).toHaveBeenCalledWith(presets[0]);
  });

  it('disables rename and delete for builtin presets', () => {
    render(<PresetLoadTab presets={[presets[2]]} isLoading={false} selectedId={3} {...noop} />);
    expect(screen.getByRole('button', { name: /^rename$/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /^delete$/i })).toBeDisabled();
  });

  it('shows empty state when no presets', () => {
    render(<PresetLoadTab presets={[]} isLoading={false} selectedId={null} {...noop} />);
    expect(screen.getByText(/no presets available/i)).toBeInTheDocument();
  });

  it('blocks selecting a preset from the other runtime', async () => {
    const onSelect = vi.fn();
    render(
      <PresetLoadTab
        presets={[{ id: 1, name: 'minqlx-preset', runtime: 'minqlx', description: 'd' }]}
        host={{ runtime: 'minqlxtended' }}
        onSelect={onSelect}
        onRequestDelete={vi.fn()}
        onRequestRename={vi.fn()}
        onDownload={vi.fn()}
      />
    );

    await userEvent.click(screen.getByText('minqlx-preset'));
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByText(/not interchangeable/i)).toBeInTheDocument();
  });

  it('still allows a matching preset', async () => {
    const onSelect = vi.fn();
    render(
      <PresetLoadTab
        presets={[{ id: 2, name: 'tended-preset', runtime: 'minqlxtended', description: 'd' }]}
        host={{ runtime: 'minqlxtended' }}
        onSelect={onSelect}
        onRequestDelete={vi.fn()}
        onRequestRename={vi.fn()}
        onDownload={vi.fn()}
      />
    );

    await userEvent.click(screen.getByText('tended-preset'));
    expect(onSelect).toHaveBeenCalledWith(2);
  });

  it('is invisible when a minqlx preset meets a minqlx host: selectable, no mismatch message', async () => {
    const onSelect = vi.fn();
    render(
      <PresetLoadTab
        presets={[{ id: 4, name: 'minqlx-preset', runtime: 'minqlx', description: 'Comp duel' }]}
        host={{ runtime: 'minqlx' }}
        onSelect={onSelect}
        onRequestDelete={vi.fn()}
        onRequestRename={vi.fn()}
        onDownload={vi.fn()}
      />
    );

    expect(screen.queryByText(/not interchangeable/i)).not.toBeInTheDocument();
    expect(screen.getByText('Comp duel')).toBeInTheDocument();
    await userEvent.click(screen.getByText('minqlx-preset'));
    expect(onSelect).toHaveBeenCalledWith(4);
  });

  it('is invisible when a legacy preset with no runtime meets a legacy host with no runtime', async () => {
    const onSelect = vi.fn();
    render(
      <PresetLoadTab
        presets={[{ id: 5, name: 'legacy-preset', description: 'Legacy cfg' }]}
        host={{}}
        onSelect={onSelect}
        onRequestDelete={vi.fn()}
        onRequestRename={vi.fn()}
        onDownload={vi.fn()}
      />
    );

    expect(screen.queryByText(/not interchangeable/i)).not.toBeInTheDocument();
    expect(screen.getByText('Legacy cfg')).toBeInTheDocument();
    await userEvent.click(screen.getByText('legacy-preset'));
    expect(onSelect).toHaveBeenCalledWith(5);
  });
});
