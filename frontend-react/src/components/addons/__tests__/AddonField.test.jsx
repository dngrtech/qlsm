import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import AddonField from '../AddonField';

const SELECT_FIELD = {
  key: 'display',
  type: 'select',
  label: 'Display',
  options: [
    { value: 'sort_score', label: 'Score (sort_score)' },
    { value: 'rank_label', label: 'Rank label' },
    'plain',
  ],
};

describe('AddonField select', () => {
  it('shows the label of the selected option, not its raw value', () => {
    render(<AddonField field={SELECT_FIELD} value="rank_label" onChange={vi.fn()} />);
    expect(screen.getByRole('button')).toHaveTextContent('Rank label');
  });

  it('reports the picked option value under the field key', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<AddonField field={SELECT_FIELD} value="sort_score" onChange={onChange} />);

    await user.click(screen.getByRole('button'));
    await user.click(await screen.findByRole('option', { name: 'Rank label' }));

    expect(onChange).toHaveBeenCalledWith('display', 'rank_label');
  });

  it('accepts bare string options and falls back to the placeholder with no match', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<AddonField field={{ ...SELECT_FIELD, placeholder: 'Pick one' }} value="" onChange={onChange} />);

    expect(screen.getByRole('button')).toHaveTextContent('Pick one');
    await user.click(screen.getByRole('button'));
    await user.click(await screen.findByRole('option', { name: 'plain' }));

    expect(onChange).toHaveBeenCalledWith('display', 'plain');
  });
});

describe('AddonField ids', () => {
  it('gives two rendered fields with the same key their own id', () => {
    const field = { key: 'server_id', type: 'string', label: 'Server ID' };
    render(
      <>
        <AddonField field={field} value="" onChange={vi.fn()} />
        <AddonField field={field} value="" onChange={vi.fn()} />
      </>,
    );
    const [first, second] = screen.getAllByLabelText('Server ID');
    expect(first.id).not.toBe(second.id);
  });
});
