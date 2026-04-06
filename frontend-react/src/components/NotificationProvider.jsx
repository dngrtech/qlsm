import React, { createContext, useContext, useState, useCallback } from 'react';
import Notification from './Notification';

// Create a context for notifications
const NotificationContext = createContext();

function createNotificationId() {
  if (globalThis.crypto?.randomUUID) {
    return globalThis.crypto.randomUUID();
  }

  return `notification-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

// Custom hook to use the notification context
export function useNotification() {
  const context = useContext(NotificationContext);
  if (!context) {
    throw new Error('useNotification must be used within a NotificationProvider');
  }
  return context;
}

export function NotificationProvider({ children }) {
  const [notifications, setNotifications] = useState([]);

  // Add a new notification
  const addNotification = useCallback((message, variant = 'info', autoClose = true, autoCloseDelay = 6000) => { // Reverted autoClose and autoCloseDelay to defaults
    const id = createNotificationId();
    setNotifications(prev => [...prev, { id, message, variant, autoClose, autoCloseDelay }]);
    return id;
  }, []);

  // Remove a notification by ID
  const removeNotification = useCallback((id) => {
    setNotifications(prev => prev.filter(notification => notification.id !== id));
  }, []);

  // Convenience methods for different notification types
  const showSuccess = useCallback((message, autoClose = true, autoCloseDelay = 6000) => { // Restored autoClose and autoCloseDelay params
    return addNotification(message, 'success', autoClose, autoCloseDelay);
  }, [addNotification]);

  const showError = useCallback((message, autoClose = true, autoCloseDelay = 6000) => { // Restored autoClose and autoCloseDelay params
    return addNotification(message, 'error', autoClose, autoCloseDelay);
  }, [addNotification]);

  const showInfo = useCallback((message, autoClose = true, autoCloseDelay = 6000) => { // Restored autoClose and autoCloseDelay params
    return addNotification(message, 'info', autoClose, autoCloseDelay);
  }, [addNotification]);

  const value = {
    addNotification,
    removeNotification,
    showSuccess,
    showError,
    showInfo
  };

  return (
    <NotificationContext.Provider value={value}>
      {children}
      {/* Position notifications at top-right */}
      <div className="fixed top-16 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
        {notifications.map((notification, index) => (
          <div
            key={notification.id}
            className="pointer-events-auto"
            style={{
              animationDelay: `${index * 50}ms`,
            }}
          >
            <Notification
              message={notification.message}
              variant={notification.variant}
              autoClose={notification.autoClose}
              autoCloseDelay={notification.autoCloseDelay}
              onClose={() => removeNotification(notification.id)}
            />
          </div>
        ))}
      </div>
    </NotificationContext.Provider>
  );
}
