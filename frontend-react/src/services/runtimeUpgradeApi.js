import apiClient from './api';

// Compatibility dry-run for upgrading a host from minqlx to minqlxtended.
export async function getRuntimeUpgrade(hostId) {
  const response = await apiClient.get(`/hosts/${hostId}/runtime-upgrade`);
  return response.data.data;
}

// Confirm and queue the upgrade. `accepted_replacements` is {instanceId: [paths]}.
export async function startRuntimeUpgrade(hostId, { fingerprint, accepted_replacements }) {
  const response = await apiClient.post(`/hosts/${hostId}/runtime-upgrade`, { fingerprint, accepted_replacements });
  return response.data;
}
