import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import AppFooter from '../AppFooter';

describe('AppFooter', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows the current app version without a negative update state', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        latest: '1.8.5',
        releaseNotesUrl: 'https://example.test/not-used',
      }),
    })));

    render(
      <MemoryRouter>
        <AppFooter />
      </MemoryRouter>
    );

    expect(screen.getByRole('link', { name: 'v1.9.0' })).toHaveAttribute('href', 'https://dngrtech.github.io/qlsm/releases/');
    await waitFor(() => {
      expect(screen.queryByText(/available/i)).not.toBeInTheDocument();
    });
  });

  it('links to release notes when a newer version is available', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        latest: '2.0.0',
        releaseNotesUrl: 'https://example.test/qlsm/releases/',
      }),
    })));

    render(
      <MemoryRouter>
        <AppFooter />
      </MemoryRouter>
    );

    const updateLink = await screen.findByRole('link', { name: 'v2.0.0 available' });
    expect(updateLink).toHaveAttribute('href', 'https://example.test/qlsm/releases/');
  });

  it('falls back to the current version when the latest check fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new Error('network unavailable');
    }));

    render(
      <MemoryRouter>
        <AppFooter />
      </MemoryRouter>
    );

    expect(screen.getByRole('link', { name: 'v1.9.0' })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText(/available/i)).not.toBeInTheDocument();
    });
  });
});
