import { Fragment, useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Menu, Transition } from '@headlessui/react';
import { Bell } from 'lucide-react';
import {
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '../services/notifications';

export const POLL_INTERVAL_MS = 30000;
const LIST_LIMIT = 20;

function formatTime(iso) {
  if (!iso) return '';
  // The API sends naive UTC timestamps.
  const date = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString();
}

/**
 * Navbar bell for stored notifications (written by core and by addons through
 * ctx.notify). The badge polls a single unread row every 30 s and whenever the
 * window regains focus, and not at all while the tab is hidden; the list is
 * only fetched when the dropdown is opened.
 */
function NotificationBell() {
  const navigate = useNavigate();
  const [unreadCount, setUnreadCount] = useState(0);
  const [items, setItems] = useState(null);

  const refreshCount = useCallback(async () => {
    try {
      const data = await listNotifications({ unread: true, limit: 1 });
      setUnreadCount(data.unread_count || 0);
    } catch {
      // A failed poll leaves the last known count; the next one retries.
    }
  }, []);

  const loadList = useCallback(async () => {
    try {
      const data = await listNotifications({ limit: LIST_LIMIT });
      setItems(data.notifications || []);
      setUnreadCount(data.unread_count || 0);
    } catch {
      setItems((current) => current || []);
    }
  }, []);

  useEffect(() => {
    refreshCount();
    const timer = setInterval(() => {
      if (!document.hidden) refreshCount();
    }, POLL_INTERVAL_MS);
    const onFocus = () => refreshCount();
    window.addEventListener('focus', onFocus);
    return () => {
      clearInterval(timer);
      window.removeEventListener('focus', onFocus);
    };
  }, [refreshCount]);

  const openItem = async (item) => {
    if (!item.read_at) {
      try {
        await markNotificationRead(item.id);
      } catch {
        // Still follow the link; the item just stays unread.
      }
      refreshCount();
    }
    if (item.link) navigate(item.link);
  };

  const markAllRead = async () => {
    try {
      await markAllNotificationsRead();
    } catch {
      // The reload below shows what is still unread.
    } finally {
      await loadList();
    }
  };

  const label = unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications';

  return (
    <Menu as="div" className="navbar-dropdown-wrapper">
      <Menu.Button className="notification-bell-trigger" aria-label={label} title={label} onClick={loadList}>
        <Bell size={18} strokeWidth={2} />
        {unreadCount > 0 && (
          <span className="notification-bell-badge" data-testid="notification-badge">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </Menu.Button>

      <Transition
        as={Fragment}
        enter="navbar-dropdown-enter"
        enterFrom="navbar-dropdown-enter-from"
        enterTo="navbar-dropdown-enter-to"
        leave="navbar-dropdown-leave"
        leaveFrom="navbar-dropdown-leave-from"
        leaveTo="navbar-dropdown-leave-to"
      >
        <Menu.Items className="navbar-dropdown-menu notification-bell-menu">
          <div className="navbar-dropdown-accent" />
          <div className="notification-bell-header">
            <span>Notifications</span>
            {unreadCount > 0 && (
              <Menu.Item>
                {({ active }) => (
                  <button
                    type="button"
                    onClick={markAllRead}
                    className={`notification-bell-mark-all ${active ? 'notification-bell-mark-all-active' : ''}`}
                  >
                    Mark all read
                  </button>
                )}
              </Menu.Item>
            )}
          </div>
          <div className="notification-bell-list">
            {items === null && <p className="notification-bell-empty">Loading...</p>}
            {items !== null && items.length === 0 && <p className="notification-bell-empty">No notifications.</p>}
            {items?.map((item) => (
              <Menu.Item key={item.id}>
                {({ active }) => (
                  <button
                    type="button"
                    onClick={() => openItem(item)}
                    data-severity={item.severity}
                    className={[
                      'notification-bell-item',
                      `notification-bell-item-${item.severity}`,
                      item.read_at ? '' : 'notification-bell-item-unread',
                      item.resolved_at ? 'notification-bell-item-resolved' : '',
                      active ? 'notification-bell-item-active' : '',
                    ].filter(Boolean).join(' ')}
                  >
                    <span className="notification-bell-dot" aria-hidden="true" />
                    <span className="notification-bell-text">
                      <span className="notification-bell-title">{item.title}</span>
                      {item.body && <span className="notification-bell-body">{item.body}</span>}
                      <span className="notification-bell-meta">
                        {item.source} · {formatTime(item.updated_at)}
                        {item.resolved_at && <span className="notification-bell-resolved-tag">Resolved</span>}
                      </span>
                    </span>
                  </button>
                )}
              </Menu.Item>
            ))}
          </div>
        </Menu.Items>
      </Transition>
    </Menu>
  );
}

export default NotificationBell;
