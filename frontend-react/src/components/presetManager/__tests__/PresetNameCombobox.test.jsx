import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import PresetNameCombobox from '../PresetNameCombobox';

vi.mock('@headlessui/react', async () => {
  const React = await import('react');
  const ComboboxCtx = React.createContext({ value: '' });
  const Combobox = ({ value, onChange, children }) => (
    <ComboboxCtx.Provider value={{ value, onChange }}>
      <div data-testid="combobox" data-value={value}>
        {typeof children === 'function' ? children({ open: false }) : children}
      </div>
    </ComboboxCtx.Provider>
  );
  function ComboboxInput({ onChange, displayValue, ...props }) {
    const ctx = React.useContext(ComboboxCtx);
    const shown = displayValue ? displayValue(ctx.value) : ctx.value;
    return (
      <input
        aria-label="Preset Name"
        value={shown ?? ''}
        onChange={(e) => onChange?.(e)}
        {...props}
      />
    );
  }
  Combobox.Input = ComboboxInput;
  Combobox.Button = ({ children, ...props }) => <button type="button" {...props}>{children}</button>;
  Combobox.Options = ({ children }) => <ul>{children}</ul>;
  Combobox.Option = ({ value, children }) => (
    <li><button type="button" onClick={() => {}}>{typeof children === 'function' ? children({ active: false }) : children}{value}</button></li>
  );
  const Portal = ({ children }) => <>{children}</>;
  const Transition = ({ children }) => <>{children}</>;
  return { Combobox, Portal, Transition };
});

vi.mock('@floating-ui/react-dom', () => ({
  useFloating: () => ({ x: 0, y: 0, strategy: 'absolute', refs: { setReference: vi.fn(), setFloating: vi.fn(), reference: { current: null } } }),
  offset: vi.fn(), flip: vi.fn(), shift: vi.fn(), autoUpdate: vi.fn(),
}));

describe('PresetNameCombobox', () => {
  const presets = [
    { id: 1, name: 'duel-cfg', description: 'd', is_builtin: false },
    { id: 2, name: 'ffa-cfg', description: '', is_builtin: false },
  ];

  it('renders the current value and forwards typed input to onChange', () => {
    const onChange = vi.fn();
    render(<PresetNameCombobox value="duel" onChange={onChange} presets={presets} />);
    const input = screen.getByLabelText('Preset Name');
    expect(input.value).toBe('duel');
    fireEvent.change(input, { target: { value: 'duelx' } });
    expect(onChange).toHaveBeenCalledWith('duelx');
  });
});
