import { act, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../services/notifications', () => ({
  listNotifications: vi.fn(),
  markNotificationRead: vi.fn(),
  markAllNotificationsRead: vi.fn(),
}));

import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '../../services/notifications';
import NotificationBell, { POLL_INTERVAL_MS } from '../NotificationBell';

const ITEMS = [
  { id: 3, source: 'sample-addon', severity: 'critical', title: 'Host down', body: 'No answer for 5 min',
    link: '/servers', resolved_at: null, read_at: null, updated_at: '2026-10-15T10:00:00' },
  { id: 2, source: 'core', severity: 'warning', title: 'Disk almost full', body: '',
    link: null, resolved_at: '2026-10-15T09:30:00', read_at: null, updated_at: '2026-10-15T09:00:00' },
  { id: 1, source: 'core', severity: 'info', title: 'Backup finished', body: '',
    link: null, resolved_at: null, read_at: '2026-10-15T08:10:00', updated_at: '2026-10-15T08:00:00' },
];

function setHidden(hidden) {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
}

function renderBell() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route path="/" element={<NotificationBell />} />
        <Route path="/servers" element={<><NotificationBell /><p>servers page</p></>} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  setHidden(false);
  listNotifications.mockImplementation(async ({ unread } = {}) => (
    unread ? { notifications: ITEMS.slice(0, 1), unread_count: 2 } : { notifications: ITEMS, unread_count: 2 }
  ));
  markNotificationRead.mockResolvedValue({});
  markAllNotificationsRead.mockResolvedValue({ updated: 2 });
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('NotificationBell badge and polling', () => {
  it('shows the unread count from a limit=1 unread poll', async () => {
    renderBell();
    expect(await screen.findByText('2')).toBeInTheDocument();
    expect(listNotifications).toHaveBeenCalledWith({ unread: true, limit: 1 });
    expect(screen.getByRole('button', { name: /notifications, 2 unread/i })).toBeInTheDocument();
  });

  it('shows no badge when nothing is unread', async () => {
    listNotifications.mockResolvedValue({ notifications: [], unread_count: 0 });
    renderBell();
    await waitFor(() => expect(listNotifications).toHaveBeenCalled());
    expect(screen.getByRole('button', { name: /^notifications$/i })).toBeInTheDocument();
    expect(screen.queryByTestId('notification-badge')).not.toBeInTheDocument();
  });

  it('polls every 30 seconds while the tab is visible and skips while hidden', async () => {
    vi.useFakeTimers();
    renderBell();
    await act(async () => {});
    expect(listNotifications).toHaveBeenCalledTimes(1);

    await act(async () => { vi.advanceTimersByTime(POLL_INTERVAL_MS); });
    expect(listNotifications).toHaveBeenCalledTimes(2);
    expect(POLL_INTERVAL_MS).toBe(30000);

    setHidden(true);
    await act(async () => { vi.advanceTimersByTime(POLL_INTERVAL_MS * 3); });
    expect(listNotifications).toHaveBeenCalledTimes(2);
  });

  it('refreshes when the window regains focus', async () => {
    renderBell();
    await waitFor(() => expect(listNotifications).toHaveBeenCalledTimes(1));
    await act(async () => { window.dispatchEvent(new Event('focus')); });
    expect(listNotifications).toHaveBeenCalledTimes(2);
  });

  it('keeps the bell quiet when the request fails', async () => {
    listNotifications.mockRejectedValue(new Error('offline'));
    renderBell();
    await waitFor(() => expect(listNotifications).toHaveBeenCalled());
    expect(screen.getByRole('button', { name: /^notifications$/i })).toBeInTheDocument();
  });
});

describe('NotificationBell dropdown', () => {
  it('lists the last 20 with severity and resolved state', async () => {
    const user = userEvent.setup();
    renderBell();
    await screen.findByText('2');
    await user.click(screen.getByRole('button', { name: /notifications/i }));

    expect(listNotifications).toHaveBeenCalledWith({ limit: 20 });
    const critical = (await screen.findByText('Host down')).closest('[data-severity]');
    expect(critical).toHaveAttribute('data-severity', 'critical');
    expect(critical.className).toContain('notification-bell-item-unread');

    const resolved = screen.getByText('Disk almost full').closest('[data-severity]');
    expect(resolved.className).toContain('notification-bell-item-resolved');
    expect(screen.getByText('Resolved')).toBeInTheDocument();
  });

  it('opens the link through the router and marks the item read', async () => {
    const user = userEvent.setup();
    renderBell();
    await screen.findByText('2');
    await user.click(screen.getByRole('button', { name: /notifications/i }));
    await user.click(await screen.findByText('Host down'));

    expect(markNotificationRead).toHaveBeenCalledWith(3);
    expect(await screen.findByText('servers page')).toBeInTheDocument();
  });

  it('marks everything read', async () => {
    const user = userEvent.setup();
    renderBell();
    await screen.findByText('2');
    await user.click(screen.getByRole('button', { name: /notifications/i }));
    listNotifications.mockResolvedValue({ notifications: [], unread_count: 0 });
    await user.click(await screen.findByText('Mark all read'));

    expect(markAllNotificationsRead).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.queryByTestId('notification-badge')).not.toBeInTheDocument());
  });

  it('keeps the unread count when marking everything read fails', async () => {
    markAllNotificationsRead.mockRejectedValue(new Error('offline'));
    const user = userEvent.setup();
    renderBell();
    await screen.findByText('2');
    await user.click(screen.getByRole('button', { name: /notifications/i }));
    await user.click(await screen.findByText('Mark all read'));

    await waitFor(() => expect(markAllNotificationsRead).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId('notification-badge')).toHaveTextContent('2');
  });

  it('says so when there are none', async () => {
    listNotifications.mockResolvedValue({ notifications: [], unread_count: 0 });
    const user = userEvent.setup();
    renderBell();
    await waitFor(() => expect(listNotifications).toHaveBeenCalled());
    await user.click(screen.getByRole('button', { name: /notifications/i }));
    expect(await screen.findByText('No notifications.')).toBeInTheDocument();
  });
});
