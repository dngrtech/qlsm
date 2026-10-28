import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ isAuthenticated: true, currentUser: { id: 1 }, logoutContext: vi.fn() }),
}));
vi.mock('../ThemeToggleButton', () => ({ default: () => <button type="button">Theme</button> }));
vi.mock('../../services/notifications', () => ({
  listNotifications: vi.fn().mockResolvedValue({ notifications: [], unread_count: 0 }),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
}));

import Navbar from '../Navbar';
import AddonsContext, { mountEntriesForAddon } from '../../contexts/AddonsContext';

function renderNavbar(path = '/servers', addons = []) {
  const value = {
    addons,
    loading: false,
    error: null,
    reload: () => {},
    mounts: (point) => addons.flatMap((addon) => mountEntriesForAddon(addon, point)),
  };
  return render(
    <AddonsContext.Provider value={value}>
      <MemoryRouter initialEntries={[path]}><Navbar /></MemoryRouter>
    </AddonsContext.Provider>,
  );
}

function pageAddon(id, overrides = {}) {
  return {
    id,
    name: id,
    loaded: true,
    ui_mountable: true,
    enabled: true,
    ui: { page: { component: 'ui/Page.js', nav: { label: `${id} label`, icon: 'activity' } } },
    ...overrides,
  };
}

describe('Navbar Global RCON navigation', () => {
  it('places the desktop Global RCON link between Servers and Docs', () => {
    renderNavbar();
    const links = screen.getAllByRole('link').map((link) => link.textContent.trim());
    expect(links.indexOf('GLOBAL RCON')).toBeGreaterThan(links.indexOf('SERVERS'));
    expect(links.indexOf('GLOBAL RCON')).toBeLessThan(links.indexOf('DOCS'));
    expect(screen.getByRole('link', { name: /global rcon/i })).toHaveAttribute('href', '/global-rcon');
  });

  it('places Global RCON between Servers and Documentation in mobile navigation', async () => {
    const user = userEvent.setup();
    renderNavbar();
    await user.click(screen.getByRole('button', { name: /open navigation menu/i }));
    const documentation = await screen.findByText('Documentation');
    const mobileGlobal = screen.getAllByText('Global RCON').at(-1).closest('a');
    const mobileServers = screen.getByText('Servers').closest('a');
    expect(mobileGlobal).toHaveAttribute('href', '/global-rcon');
    expect(mobileServers.compareDocumentPosition(mobileGlobal) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(mobileGlobal.compareDocumentPosition(documentation) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

describe('Navbar notification bell', () => {
  it('shows the bell for a signed-in user', async () => {
    renderNavbar();
    expect(await screen.findByRole('button', { name: /^notifications$/i })).toBeInTheDocument();
  });
});

describe('Navbar Backup & Restore navigation', () => {
  it('links to the Backup & Restore page from the desktop settings dropdown', async () => {
    const user = userEvent.setup();
    renderNavbar();
    await user.click(screen.getByRole('button', { name: /settings/i }));
    // Headless UI marks the rest of the page aria-hidden while this menu's
    // portal is open, which getByRole('link', ...) correctly excludes —
    // use getByText like the mobile-menu test below, which reads raw text
    // content and isn't affected by that.
    const link = await screen.findByText('Backup & Restore');
    expect(link.closest('a')).toHaveAttribute('href', '/settings/backup');
  });

  it('links to the Backup & Restore page from the mobile settings dropdown', async () => {
    const user = userEvent.setup();
    renderNavbar();
    await user.click(screen.getByRole('button', { name: /open navigation menu/i }));
    const link = await screen.findByText('Backup & Restore');
    expect(link.closest('a')).toHaveAttribute('href', '/settings/backup');
  });
});

describe('Navbar addon page entries', () => {
  it('shows an entry for an enabled, loaded addon page with nav, after the core items and ordered by id', () => {
    renderNavbar('/servers', [pageAddon('zeta'), pageAddon('alpha')]);
    const links = screen.getAllByRole('link').map((link) => link.textContent.trim());
    expect(links.indexOf('ALPHA LABEL')).toBeGreaterThan(links.indexOf('DOCS'));
    expect(links.indexOf('ZETA LABEL')).toBeGreaterThan(links.indexOf('ALPHA LABEL'));
    expect(screen.getByRole('link', { name: /alpha label/i })).toHaveAttribute('href', '/addons/alpha');
  });

  it('shows nothing for a disabled, broken, too-new or nav-less addon', () => {
    renderNavbar('/servers', [
      pageAddon('off', { enabled: false }),
      pageAddon('broken', { loaded: false }),
      pageAddon('newer', { ui_mountable: false }),
      pageAddon('plain', { ui: { page: { component: 'ui/Page.js' } } }),
    ]);
    expect(screen.queryByText(/label/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /plain/i })).not.toBeInTheDocument();
  });

  it('marks the entry active on its own page only', () => {
    renderNavbar('/addons/alpha', [pageAddon('alpha'), pageAddon('alpha-two')]);
    expect(screen.getByRole('link', { name: /^alpha label$/i })).toHaveClass('navbar-nav-link-active');
    expect(screen.getByRole('link', { name: /alpha-two label/i })).not.toHaveClass('navbar-nav-link-active');
  });

  it('lists the entry in the mobile menu, active on its page', async () => {
    const user = userEvent.setup();
    renderNavbar('/addons/alpha', [pageAddon('alpha')]);
    await user.click(screen.getByRole('button', { name: /open navigation menu/i }));
    const item = (await screen.findAllByText('alpha label')).at(-1).closest('a');
    expect(item).toHaveAttribute('href', '/addons/alpha');
    expect(item).toHaveClass('navbar-dropdown-item-active');
  });
});

describe('Navbar Presets navigation', () => {
  it('links to the Presets page from the desktop settings dropdown', async () => {
    const user = userEvent.setup();
    renderNavbar();
    await user.click(screen.getByRole('button', { name: /settings/i }));
    const link = await screen.findByText('Presets');
    expect(link.closest('a')).toHaveAttribute('href', '/presets');
  });

  it('links to the Presets page from the mobile settings dropdown', async () => {
    const user = userEvent.setup();
    renderNavbar();
    await user.click(screen.getByRole('button', { name: /open navigation menu/i }));
    const link = await screen.findByText('Presets');
    expect(link.closest('a')).toHaveAttribute('href', '/presets');
  });
});
