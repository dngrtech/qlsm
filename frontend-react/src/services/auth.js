import apiClient from './api';

export const login = async (username, password) => {
  try {
    const response = await apiClient.post('/auth/login', { username, password });
    return response.data;
  } catch (error) {
    console.error('Login failed:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Login failed');
  }
};

export const getAuthStatus = async () => {
  const response = await apiClient.get('/auth/status');
  return response.data;
};

export const logout = async () => {
  const response = await apiClient.post('/auth/logout');
  return response.data;
};

export const changePassword = async (password, confirmPassword) => {
  try {
    const response = await apiClient.post('/auth/change-password', {
      password,
      confirmPassword,
    });
    return response.data;
  } catch (error) {
    console.error(
      'Change password failed:',
      error.response ? error.response.data : error.message
    );
    throw error.response ? error.response.data : new Error('Failed to change password');
  }
};
