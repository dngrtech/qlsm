// Stored notifications (the navbar bell).
import apiClient from './api';

// Returns { notifications, unread_count }; unread_count is the total, not the
// length of the page, so the bell can poll with { unread: true, limit: 1 }.
export const listNotifications = async ({ unread = false, limit = 20 } = {}) => {
  const params = { limit };
  if (unread) params.unread = 1;
  const response = await apiClient.get('/notifications', { params });
  return response.data.data;
};

export const markNotificationRead = async (id) => {
  const response = await apiClient.post(`/notifications/${id}/read`);
  return response.data.data;
};

export const markAllNotificationsRead = async () => {
  const response = await apiClient.post('/notifications/read-all');
  return response.data.data;
};
