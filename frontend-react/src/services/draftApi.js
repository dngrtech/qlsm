import apiClient from './api';

export const createDraft = async ({ source, preset, host, instanceId }) => {
  const body = { source };
  if (preset) body.preset = preset;
  if (host) body.host = host;
  if (instanceId) body.instance_id = instanceId;
  const response = await apiClient.post('/drafts/', body);
  return response.data.data;
};

export const discardDraft = async (draftId) => {
  const response = await apiClient.delete(`/drafts/${draftId}`);
  return response.data.data;
};

export const touchDraft = async (draftId) => {
  const response = await apiClient.post(`/drafts/${draftId}/touch`);
  return response.data.data;
};

export const getDraftTree = async (draftId) => {
  const response = await apiClient.get(`/drafts/${draftId}/tree`);
  return response.data.data;
};

export const getDraftContent = async (draftId, path) => {
  const params = new URLSearchParams({ path });
  const response = await apiClient.get(`/drafts/${draftId}/content?${params}`);
  return response.data.data;
};

export const saveDraftContent = async (draftId, path, content) => {
  const response = await apiClient.put(`/drafts/${draftId}/content`, { path, content });
  return response.data.data;
};

export const uploadToDraft = async (draftId, file, targetPath = '') => {
  const formData = new FormData();
  formData.append('file', file);
  if (targetPath) formData.append('target_path', targetPath);
  const response = await apiClient.post(`/drafts/${draftId}/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  });
  return response.data.data;
};

export const deleteDraftFile = async (draftId, path) => {
  const params = new URLSearchParams({ path });
  const response = await apiClient.delete(`/drafts/${draftId}/file?${params}`);
  return response.data.data;
};

export const commitDraft = async (draftId, target) => {
  const response = await apiClient.post(`/drafts/${draftId}/commit`, target);
  return response.data.data;
};
