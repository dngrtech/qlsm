import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import ChangePasswordPage from '../ChangePasswordPage';

const mocks = vi.hoisted(() => ({
  navigate: vi.fn(),
  clearPasswordChangeRequired: vi.fn(),
  showSuccess: vi.fn(),
  changePassword: vi.fn(),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => mocks.navigate,
}));

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ clearPasswordChangeRequired: mocks.clearPasswordChangeRequired }),
}));

vi.mock('../../components/NotificationProvider', () => ({
  useNotification: () => ({ showSuccess: mocks.showSuccess }),
}));

vi.mock('../../services/auth', () => ({
  changePassword: mocks.changePassword,
}));

describe('ChangePasswordPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.changePassword.mockResolvedValue({});
  });

  it('navigates to /servers with openAddHost state on success', async () => {
    render(<ChangePasswordPage />);

    fireEvent.change(screen.getByLabelText(/new password/i), {
      target: { value: 'newpassword123' },
    });
    fireEvent.change(screen.getByLabelText(/confirm password/i), {
      target: { value: 'newpassword123' },
    });
    fireEvent.submit(screen.getByRole('button', { name: /save password/i }));

    await waitFor(() => {
      expect(mocks.navigate).toHaveBeenCalledWith('/servers', {
        replace: true,
        state: { openAddHost: true },
      });
    });

    expect(window.sessionStorage.getItem('qlsm:auto-open-add-host')).toBe('1');
  });
});
