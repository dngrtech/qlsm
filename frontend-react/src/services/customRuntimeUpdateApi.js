import apiClient from './api';

export async function getCustomRuntimeUpdate(hostId) {
  const response = await apiClient.get(`/hosts/${hostId}/custom-runtime-update`);
  return response.data.data;
}

export async function startCustomRuntimeUpdate(hostId, { fingerprint, target_sha256, action }) {
  const response = await apiClient.post(`/hosts/${hostId}/custom-runtime-update`, {
    fingerprint,
    target_sha256,
    action,
  });
  return response.data.data;
}
