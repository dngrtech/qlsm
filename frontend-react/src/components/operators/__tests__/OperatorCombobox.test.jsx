import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import OperatorCombobox from '../OperatorCombobox';

describe('OperatorCombobox', () => {
  it('shows the operator name when the value is in the directory', () => {
    render(<OperatorCombobox value="76561198012345678" onChange={() => {}} operators={[
      { id: 1, name: 'Vex', steam_id64: '76561198012345678' },
    ]} />);
    expect(screen.getByDisplayValue('Vex (76561198012345678)')).toBeInTheDocument();
  });

  it('shows the raw SteamID when the value is not in the directory', () => {
    render(<OperatorCombobox value="76561199580544522" onChange={() => {}} operators={[]} />);
    expect(screen.getByDisplayValue('76561199580544522')).toBeInTheDocument();
  });

  it('shows nothing when there is no value', () => {
    render(<OperatorCombobox value="" onChange={() => {}} operators={[]} placeholder="Select owner…" />);
    expect(screen.getByPlaceholderText('Select owner…')).toHaveValue('');
  });
});
