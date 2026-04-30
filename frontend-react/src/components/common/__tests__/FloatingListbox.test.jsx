import React from 'react';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import FloatingListbox from '../FloatingListbox';

describe('FloatingListbox', () => {
  it('renders an option badge beside the selected option', () => {
    render(
      <FloatingListbox
        label="Plan"
        value="vhf-1c-1gb"
        onChange={vi.fn()}
        options={[
          {
            id: 'vhf-1c-1gb',
            name: 'High Frequency - 1 vCPU / 1 GB RAM / $6/mo',
            badgeLabel: 'Recommended',
          },
          {
            id: 'vc2-1c-1gb',
            name: 'Cloud Compute - 1 vCPU / 1 GB RAM / $5/mo',
          },
        ]}
        getOptionBadge={(option) => option.badgeLabel}
      />
    );

    const button = screen.getByRole('button');
    expect(within(button).getByText('Recommended')).toBeInTheDocument();

    expect(button).toHaveTextContent('High Frequency - 1 vCPU / 1 GB RAM / $6/mo');
  });
});
