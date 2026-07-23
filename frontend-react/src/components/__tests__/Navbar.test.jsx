import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ isAuthenticated: true, currentUser: { id: 1 }, logoutContext: vi.fn() }),
}));
vi.mock('../ThemeToggleButton', () => ({ default: () => <button type="button">Theme</button> }));

import Navbar from '../Navbar';

function renderNavbar() {
  return render(<MemoryRouter initialEntries={['/servers']}><Navbar /></MemoryRouter>);
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
