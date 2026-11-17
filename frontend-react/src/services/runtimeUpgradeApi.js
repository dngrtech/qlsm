import apiClient from './api';

// Compatibility dry-run for upgrading a host from minqlx to minqlxtended.
export async function getRuntimeUpgrade(hostId) {
  const response = await apiClient.get(`/hosts/${hostId}/runtime-upgrade`);
  return response.data.data;
}

// Check one uploaded plugin file. Rejects with the axios error; the server's
// `error.message` and `error.reasons` explain why a file was refused.
export async function validateRuntimeUploadPlugin(hostId, { path, text }) {
  const response = await apiClient.post(`/hosts/${hostId}/runtime-upgrade/validate-plugin`, { path, text });
  return response.data.data;
}

// Confirm and queue the upgrade. `accepted_replacements` is {instanceId: [paths]}.
// `uploaded_files` / `uploaded_file_ids` are sent only when non-empty.
export async function startRuntimeUpgrade(hostId, {
  fingerprint, accepted_replacements, uploaded_files, uploaded_file_ids,
}) {
  const body = { fingerprint, accepted_replacements };
  if (uploaded_files && Object.keys(uploaded_files).length > 0) body.uploaded_files = uploaded_files;
  if (uploaded_file_ids && Object.keys(uploaded_file_ids).length > 0) body.uploaded_file_ids = uploaded_file_ids;
  const response = await apiClient.post(`/hosts/${hostId}/runtime-upgrade`, body);
  return response.data;
}
