import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api', // Placeholder, will be proxied by Vite dev server / Nginx in prod
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true, // Send cookies with requests
});

apiClient.interceptors.request.use((config) => {
  const csrfToken = document.cookie
    .split('; ')
    .find(row => row.startsWith('csrf_access_token='))
    ?.split('=').slice(1).join('=');
  if (csrfToken) {
    config.headers['X-CSRF-TOKEN'] = csrfToken;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      if (!window.location.pathname.endsWith('/login')) {
        // Clear the HttpOnly JWT cookie server-side before redirecting.
        // Use native fetch to avoid re-triggering this interceptor.
        fetch('/api/auth/logout', { method: 'POST', credentials: 'include' })
          .finally(() => { window.location.href = '/login'; });
      }
    }
    return Promise.reject(error);
  }
);

// Authentication API
export const login = async (username, password) => {
  try {
    const response = await apiClient.post('/auth/login', { username, password });
    // Token is now set as an HttpOnly cookie by the backend, no need to store it in localStorage.
    // if (response.data.data && response.data.data.token) { // This part is no longer relevant
    // localStorage.setItem('jwt_token', response.data.data.token); // REMOVED
    // You might want to set user info in a global state here as well
    // }
    // The response from the backend might change, e.g., just a success message.
    // Assuming it still returns some data, like user info or a success message.
    return response.data;
  } catch (error) {
    // Handle or throw error to be caught by the caller
    console.error('Login failed:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Login failed');
  }
};


// Host APIs
export const getHosts = async () => {
  try {
    // Reverted to use apiClient
    const response = await apiClient.get('/hosts/'); // Added trailing slash for consistency
    return response.data.data;
  } catch (error) {
    console.error('Failed to fetch hosts:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to fetch hosts');
  }
};

export const createHost = async (hostData) => {
  try {
    const response = await apiClient.post('/hosts/', hostData); // Added trailing slash
    return response.data; // Assuming API returns { "data": {...}, "message": "..." } or similar
  } catch (error) {
    console.error('Failed to create host:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to create host');
  }
};

export const getSelfHostDefaults = async () => {
  try {
    const response = await apiClient.get('/hosts/self/defaults');
    return response.data.data;
  } catch (error) {
    console.error('Failed to fetch self-host defaults:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to fetch self-host defaults');
  }
};

export const getHostById = async (hostId) => {
  try {
    const response = await apiClient.get(`/hosts/${hostId}`);
    return response.data.data; // Assuming API returns { "data": {...} }
  } catch (error) {
    console.error(`Failed to fetch host ${hostId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to fetch host ${hostId}`);
  }
};

export const getHostLogs = async (hostId) => {
  try {
    const response = await apiClient.get(`/hosts/${hostId}/logs`);
    return response.data.data; // Assuming API returns { "data": { "logs": "..." } }
  } catch (error) {
    console.error(`Failed to fetch logs for host ${hostId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to fetch logs for host ${hostId}`);
  }
};

export const deleteHost = async (hostId) => {
  try {
    const response = await apiClient.delete(`/hosts/${hostId}`);
    return response.data; // Assuming API returns a message like { "message": "..." }
  } catch (error) {
    console.error(`Failed to delete host ${hostId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to delete host ${hostId}`);
  }
};

export const updateHost = async (hostId, hostData) => {
  try {
    const response = await apiClient.put(`/hosts/${hostId}`, hostData);
    return response.data;
  } catch (error) {
    console.error(`Failed to update host ${hostId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to update host ${hostId}`);
  }
};

// Add this new function for restarting a host
export const restartHost = async (hostId) => {
  try {
    const response = await apiClient.post(`/hosts/${hostId}/restart`);
    return response.data; // Assuming API returns { "message": "..." }
  } catch (error) {
    console.error(`Failed to restart host ${hostId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to restart host ${hostId}`);
  }
};

export const updateWorkshopItem = async (hostId, data) => {
  try {
    const response = await apiClient.post(`/hosts/${hostId}/update-workshop`, data);
    return response.data; // Assuming API returns { "message": "..." }
  } catch (error) {
    console.error(`Failed to update workshop item for host ${hostId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to update workshop item for host ${hostId}`);
  }
};

export const configureAutoRestart = async (hostId, schedule) => {
  try {
    const response = await apiClient.post(`/hosts/${hostId}/auto-restart`, { schedule });
    return response.data; // Assuming API returns { "message": "...", "data": {...} }
  } catch (error) {
    console.error(`Failed to configure auto-restart for host ${hostId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to configure auto-restart for host ${hostId}`);
  }
};

// Test SSH connection for standalone hosts
export const testHostConnection = async (connectionData) => {
  try {
    const response = await apiClient.post('/hosts/test-connection', connectionData);
    return response.data.data; // { success: boolean, message: string }
  } catch (error) {
    console.error('Failed to test host connection:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to test host connection');
  }
};

// Instance APIs
export const getInstances = async () => {
  try {
    // Reverted to use apiClient
    const response = await apiClient.get('/instances/'); // Added trailing slash for consistency
    return response.data.data;
  } catch (error) {
    console.error('Failed to fetch instances:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to fetch instances');
  }
};

export const createInstance = async (instanceData) => {
  try {
    const response = await apiClient.post('/instances/', instanceData); // Added trailing slash
    return response.data; // Assuming API returns { "data": {...}, "message": "..." } or similar
  } catch (error) {
    console.error('Failed to create instance:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to create instance');
  }
};

export const getAvailablePortsForHost = async (hostId, signal) => {
  try {
    // This matches the API endpoint defined in host_routes.py
    const response = await apiClient.get(`/hosts/${hostId}/available-ports`, { signal });
    return response.data.data; // Expects { "data": { "available_ports": [...] } }
  } catch (error) {
    if (error?.name === 'AbortError' || error?.name === 'CanceledError') throw error;
    console.error(`Failed to fetch available ports for host ${hostId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to fetch available ports for host ${hostId}`);
  }
};

export const updateInstance = async (instanceId, instanceData) => {
  try {
    const response = await apiClient.put(`/instances/${instanceId}`, instanceData);
    return response.data;
  } catch (error) {
    console.error(`Failed to update instance ${instanceId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to update instance ${instanceId}`);
  }
};

export const getInstanceById = async (instanceId) => {
  try {
    const response = await apiClient.get(`/instances/${instanceId}`);
    return response.data.data; // Assuming API returns { "data": {...} }
  } catch (error) {
    console.error(`Failed to fetch instance ${instanceId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to fetch instance ${instanceId}`);
  }
};

export const getInstanceLogs = async (instanceId) => {
  try {
    const response = await apiClient.get(`/instances/${instanceId}/logs`);
    return response.data.data; // Assuming API returns { "data": { "logs": "..." } }
  } catch (error) {
    console.error(`Failed to fetch logs for instance ${instanceId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to fetch logs for instance ${instanceId}`);
  }
};

export const restartInstance = async (instanceId) => {
  try {
    const response = await apiClient.post(`/instances/${instanceId}/restart`);
    return response.data; // Assuming API returns { "message": "..." }
  } catch (error) {
    console.error(`Failed to restart instance ${instanceId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to restart instance ${instanceId}`);
  }
};

export const stopInstance = async (instanceId) => {
  try {
    const response = await apiClient.post(`/instances/${instanceId}/stop`);
    return response.data;
  } catch (error) {
    console.error(`Failed to stop instance ${instanceId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to stop instance ${instanceId}`);
  }
};

export const startInstance = async (instanceId) => {
  try {
    const response = await apiClient.post(`/instances/${instanceId}/start`);
    return response.data;
  } catch (error) {
    console.error(`Failed to start instance ${instanceId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to start instance ${instanceId}`);
  }
};

export const deleteInstance = async (instanceId) => {
  try {
    const response = await apiClient.delete(`/instances/${instanceId}`);
    return response.data; // Assuming API returns { "message": "..." }
  } catch (error) {
    console.error(`Failed to delete instance ${instanceId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to delete instance ${instanceId}`);
  }
};

export const getInstanceConfig = async (instanceId) => {
  try {
    const response = await apiClient.get(`/instances/${instanceId}/config`);
    return response.data.data; // Assuming API returns { "data": { "server.cfg": "...", ... } }
  } catch (error) {
    console.error(`Failed to fetch config for instance ${instanceId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to fetch config for instance ${instanceId}`);
  }
};

export const updateInstanceConfig = async (instanceId, configData, restart = true) => {
  try {
    // Extract non-config metadata so the backend receives it at the top level.
    const {
      scripts,
      factories,
      qlx_plugins,
      draft_id,
      checked_plugins,
      lan_rate_enabled,
      ...configs
    } = configData;
    const payload = { configs, restart };
    if (scripts && Object.keys(scripts).length > 0) {
      payload.scripts = scripts;
    }
    if (factories) {
      payload.factories = factories;
    }
    if (qlx_plugins !== undefined) {
      payload.qlx_plugins = qlx_plugins;
    }
    if (draft_id) {
      payload.draft_id = draft_id;
    }
    if (checked_plugins !== undefined) {
      payload.checked_plugins = checked_plugins;
    }
    if (lan_rate_enabled !== undefined) {
      payload.lan_rate_enabled = lan_rate_enabled;
    }
    const response = await apiClient.put(`/instances/${instanceId}/config`, payload);
    return response.data; // Assuming API returns { "message": "..." }
  } catch (error) {
    console.error(`Failed to update config for instance ${instanceId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to update config for instance ${instanceId}`);
  }
};

export const updateInstanceLanRate = async (instanceId, lanRateEnabled) => {
  try {
    const response = await apiClient.put(`/instances/${instanceId}/lan-rate`, { lan_rate_enabled: lanRateEnabled });
    return response.data; // Assuming API returns { "message": "...", "data": {...} }
  } catch (error) {
    console.error(`Failed to update LAN rate for instance ${instanceId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to update LAN rate for instance ${instanceId}`);
  }
};

export const fetchInstanceRemoteLogs = async (instanceId, options = {}) => {
  try {
    const { filterMode = 'lines', since = '1 hour ago', lines = 500 } = options;
    const params = new URLSearchParams({
      filter_mode: filterMode,
      since: since,
      lines: lines.toString()
    });
    const response = await apiClient.get(`/instances/${instanceId}/remote-logs?${params.toString()}`);
    return response.data.data; // { logs, instance_name, port, filter_mode, lines, since }
  } catch (error) {
    console.error(`Failed to fetch remote logs for instance ${instanceId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to fetch remote logs for instance ${instanceId}`);
  }
};

export const fetchInstanceChatLogs = async (instanceId, options = {}) => {
  try {
    const { lines = 500, filename = 'chat.log' } = options;
    const params = new URLSearchParams({
      lines: lines.toString(),
      filename: filename
    });
    const response = await apiClient.get(`/instances/${instanceId}/chat-logs?${params.toString()}`);
    return response.data.data; // { logs, instance_name, port, lines, filename }
  } catch (error) {
    console.error(`Failed to fetch chat logs for instance ${instanceId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to fetch chat logs for instance ${instanceId}`);
  }
};

export const listInstanceChatLogs = async (instanceId) => {
  try {
    const response = await apiClient.get(`/instances/${instanceId}/chat-logs/list`);
    return response.data.data; // { files, instance_name }
  } catch (error) {
    console.error(`Failed to list chat logs for instance ${instanceId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to list chat logs for instance ${instanceId}`);
  }
};

// Config Preset APIs
export const getPresets = async () => {
  try {
    // Relying on the interceptor to add the Authorization header
    const response = await apiClient.get('/presets/'); // Added trailing slash for consistency
    return response.data.data; // Assuming { "data": [...] }
  } catch (error) {
    console.error('Failed to fetch presets:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to fetch presets');
  }
};

export const createPreset = async (presetData) => {
  try {
    const response = await apiClient.post('/presets/', presetData);
    return response.data; // Assuming { "data": {...}, "message": "..." }
  } catch (error) {
    console.error('Failed to create preset:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to create preset');
  }
};

export const getPresetById = async (presetId) => {
  try {
    const response = await apiClient.get(`/presets/${presetId}`);
    return response.data.data; // Assuming { "data": {...} }
  } catch (error) {
    console.error(`Failed to fetch preset ${presetId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to fetch preset ${presetId}`);
  }
};

export const updatePreset = async (presetId, presetData) => {
  try {
    const response = await apiClient.put(`/presets/${presetId}`, presetData);
    return response.data; // Assuming { "data": {...}, "message": "..." }
  } catch (error) {
    console.error(`Failed to update preset ${presetId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to update preset ${presetId}`);
  }
};

export const deletePreset = async (presetId) => {
  try {
    const response = await apiClient.delete(`/presets/${presetId}`);
    return response.data; // Assuming { "message": "..." }
  } catch (error) {
    console.error(`Failed to delete preset ${presetId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to delete preset ${presetId}`);
  }
};

// Validate preset name availability
export const validatePresetName = async (name) => {
  try {
    const response = await apiClient.get(`/presets/validate-name?name=${encodeURIComponent(name)}`);
    return response.data.data; // { is_valid: boolean, error: string|null }
  } catch (error) {
    console.error(`Failed to validate preset name ${name}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to validate preset name`);
  }
};

// Alias for createPreset - clearer name for the save operation
export const savePreset = createPreset;

// Default Config File API
export const getDefaultConfigFile = async (filename) => {
  try {
    // The backend returns plain text for this endpoint
    const response = await apiClient.get(`/default-config/${filename}`, {
      headers: {
        // Override Content-Type for this request if necessary,
        // but usually GET requests don't send a Content-Type.
        // Accept header might be useful if backend strictly checks it.
      },
      transformResponse: [(data) => data] // Prevent Axios from trying to parse it as JSON
    });
    return response.data; // This will be the plain text content
  } catch (error) {
    console.error(`Failed to fetch default config file ${filename}:`, error.response ? error.response.data : error.message);
    throw error.response ? (error.response.data.error || error.response.data) : new Error(`Failed to fetch default config file ${filename}`);
  }
};

// QLFilter APIs for Hosts
export const installQlfilter = async (hostId) => {
  try {
    const response = await apiClient.post(`/hosts/${hostId}/qlfilter/install`);
    return response.data; // Expects { "message": "..." }
  } catch (error) {
    console.error(`Failed to install QLFilter for host ${hostId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to install QLFilter for host ${hostId}`);
  }
};

export const uninstallQlfilter = async (hostId) => {
  try {
    const response = await apiClient.post(`/hosts/${hostId}/qlfilter/uninstall`);
    return response.data; // Expects { "message": "..." }
  } catch (error) {
    console.error(`Failed to uninstall QLFilter for host ${hostId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to uninstall QLFilter for host ${hostId}`);
  }
};

export const getQlfilterStatus = async (hostId) => {
  try {
    const response = await apiClient.get(`/hosts/${hostId}/qlfilter/status`);
    return response.data.data; // Expects { "data": { "qlfilter_status": "status_value" } }
  } catch (error) {
    console.error(`Failed to get QLFilter status for host ${hostId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to get QLFilter status for host ${hostId}`);
  }
};

export const refreshQlfilterStatus = async (hostId) => {
  try {
    const response = await apiClient.post(`/hosts/${hostId}/qlfilter/refresh-status`);
    return response.data; // Expects { "message": "..." }
  } catch (error) {
    console.error(`Failed to refresh QLFilter status for host ${hostId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to refresh QLFilter status for host ${hostId}`);
  }
};

// User Management APIs
export const getUsers = async () => {
  try {
    const response = await apiClient.get('/users/');
    return response.data.data;
  } catch (error) {
    console.error('Failed to fetch users:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to fetch users');
  }
};

export const createUser = async (userData) => {
  try {
    const response = await apiClient.post('/users/', userData);
    return response.data;
  } catch (error) {
    console.error('Failed to create user:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to create user');
  }
};

export const resetUserPassword = async (userId, newPassword) => {
  try {
    const response = await apiClient.put(`/users/${userId}/password`, { password: newPassword });
    return response.data;
  } catch (error) {
    console.error(`Failed to reset password for user ${userId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to reset password for user ${userId}`);
  }
};

export const deleteUser = async (userId) => {
  try {
    const response = await apiClient.delete(`/users/${userId}`);
    return response.data;
  } catch (error) {
    console.error(`Failed to delete user ${userId}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to delete user ${userId}`);
  }
};

// Script Management APIs
export const getScriptTree = async ({ preset, host, instanceId } = {}) => {
  try {
    const params = new URLSearchParams();
    if (preset) params.append('preset', preset);
    if (host) params.append('host', host);
    if (instanceId) params.append('instance_id', instanceId);
    const response = await apiClient.get(`/scripts/tree?${params}`);
    return response.data.data;
  } catch (error) {
    console.error('Failed to fetch script tree:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to fetch script tree');
  }
};

export const getScriptContent = async (path, { preset, host, instanceId } = {}) => {
  try {
    const params = new URLSearchParams({ path });
    if (preset) params.append('preset', preset);
    if (host) params.append('host', host);
    if (instanceId) params.append('instance_id', instanceId);
    const response = await apiClient.get(`/scripts/content?${params}`);
    return response.data.data;
  } catch (error) {
    console.error(`Failed to fetch script content for ${path}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to fetch script content for ${path}`);
  }
};

export const saveScript = async (host, instanceId, path, content) => {
  try {
    const response = await apiClient.put('/scripts/content', {
      host,
      instance_id: instanceId,
      path,
      content
    });
    return response.data.data;
  } catch (error) {
    console.error(`Failed to save script ${path}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to save script ${path}`);
  }
};

export const validateScript = async (content) => {
  try {
    const response = await apiClient.post('/scripts/validate', { content });
    return response.data.data;
  } catch (error) {
    console.error('Failed to validate script:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to validate script');
  }
};

export const uploadScript = async (file, host, instanceId, targetPath = '') => {
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('host', host);
    formData.append('instance_id', instanceId);
    if (targetPath) formData.append('target_path', targetPath);

    const response = await apiClient.post('/scripts/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    return response.data.data;
  } catch (error) {
    console.error('Failed to upload script:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to upload script');
  }
};

// Factory Management APIs
export const getFactoryTree = async ({ preset, host, instanceId } = {}) => {
  try {
    const params = new URLSearchParams();
    if (preset) params.append('preset', preset);
    if (host) params.append('host', host);
    if (instanceId) params.append('instance_id', instanceId);
    const response = await apiClient.get(`/factories/tree?${params}`);
    return response.data.data;
  } catch (error) {
    console.error('Failed to fetch factory tree:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to fetch factory tree');
  }
};

export const getFactoryContent = async (path, { preset, host, instanceId } = {}) => {
  try {
    const params = new URLSearchParams({ path });
    if (preset) params.append('preset', preset);
    if (host) params.append('host', host);
    if (instanceId) params.append('instance_id', instanceId);
    const response = await apiClient.get(`/factories/content?${params}`);
    return response.data.data;
  } catch (error) {
    console.error(`Failed to fetch factory content for ${path}:`, error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error(`Failed to fetch factory content for ${path}`);
  }
};

// Settings APIs
export const getApiKey = async () => {
  try {
    const response = await apiClient.get('/settings/api-key');
    return response.data.data;
  } catch (error) {
    console.error('Failed to fetch API key:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to fetch API key');
  }
};

export const regenerateApiKey = async () => {
  try {
    const response = await apiClient.post('/settings/api-key');
    return response.data.data;
  } catch (error) {
    console.error('Failed to regenerate API key:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to regenerate API key');
  }
};

export const revokeApiKey = async () => {
  try {
    const response = await apiClient.delete('/settings/api-key');
    return response.data;
  } catch (error) {
    console.error('Failed to revoke API key:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to revoke API key');
  }
};

export const getServerStatus = async () => {
  const response = await apiClient.get('/server-status');
  return response.data.data; // {instanceId: statusData}
};

export const getWorkshopPreview = async (workshopId) => {
  try {
    const response = await apiClient.get(`/server-status/workshop-preview/${workshopId}`);
    return response?.data?.data || { preview_url: null };
  } catch (error) {
    console.error('Failed to fetch workshop preview:', error.response ? error.response.data : error.message);
    throw error.response ? error.response.data : new Error('Failed to fetch workshop preview');
  }
};

export default apiClient;
