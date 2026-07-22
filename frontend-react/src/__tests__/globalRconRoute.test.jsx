import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const auth = vi.hoisted(() => ({ isAuthenticated: true, currentUser: { id: 1 }, isLoadingAuth: false }));
vi.mock('../contexts/AuthContext', () => ({
  AuthProvider: ({ children }) => children,
  useAuth: () => ({ ...auth, login: vi.fn(), logoutContext: vi.fn() }),
}));
vi.mock('../components/ThemeToggleButton', () => ({ default: () => <button type="button">Theme</button> }));
vi.mock('../pages/GlobalRconPage', () => ({ default: () => <div data-testid="global-rcon-page" /> }));

import App from '../App';

beforeEach(() => {
  auth.isAuthenticated = true;
  auth.currentUser = { id: 1 };
  auth.isLoadingAuth = false;
});

function renderAt(path) {
  return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
}

describe('/global-rcon route', () => {
  it('renders the Global RCON page for an authenticated user', () => {
    renderAt('/global-rcon');
    expect(screen.getByTestId('global-rcon-page')).toBeInTheDocument();
  });

  it('does not render the Global RCON page without authentication', () => {
    auth.isAuthenticated = false;
    auth.currentUser = null;
    renderAt('/global-rcon');
    expect(screen.queryByTestId('global-rcon-page')).not.toBeInTheDocument();
  });
});
