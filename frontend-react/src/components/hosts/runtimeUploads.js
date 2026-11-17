// Pure state helpers for plugin files the operator uploads in the
// runtime-upgrade dialog. UploadedFile = { name, text }.
// state = { files: {[path]: UploadedFile}, overrides: {[instanceId]: {[path]: UploadedFile | null}} }
// `files` is a host-wide upload; `overrides` is a per-instance replacement
// (a file) or removal (null) that wins over it.

// Same rule as the server's plugin file-name check.
export const isUploadablePath = (path) => /^[A-Za-z_][A-Za-z0-9_]*\.py$/.test(path);

export const emptyUploads = () => ({ files: {}, overrides: {} });

export const addUpload = (state, path, file) => {
  const overrides = {};
  Object.entries(state.overrides).forEach(([id, byPath]) => {
    const { [path]: _dropped, ...rest } = byPath;
    overrides[id] = rest;
  });
  return { files: { ...state.files, [path]: file }, overrides };
};

const setOverride = (state, instanceId, path, value) => ({
  ...state,
  overrides: {
    ...state.overrides,
    [instanceId]: { ...(state.overrides[instanceId] || {}), [path]: value },
  },
});

export const replaceRowUpload = (state, instanceId, path, file) => setOverride(state, instanceId, path, file);
export const removeRowUpload = (state, instanceId, path) => setOverride(state, instanceId, path, null);

export const effectiveUpload = (state, instanceId, path) => {
  const byPath = state.overrides[instanceId];
  if (byPath && Object.prototype.hasOwnProperty.call(byPath, path)) return byPath[path];
  return state.files[path] || null;
};

export const buildUploadPayload = (plan, state) => {
  const uploaded_files = {};
  const uploaded_file_ids = {};
  const ids = new Map();
  (plan?.instances || []).forEach((inst) => {
    (inst.stripped || []).forEach((row) => {
      if (row.kind !== 'unavailable') return;
      const file = effectiveUpload(state, inst.instance_id, row.path);
      if (!file) return;
      const key = JSON.stringify([row.path, file.text]);
      if (!ids.has(key)) {
        const id = `f${ids.size + 1}`;
        ids.set(key, id);
        uploaded_files[id] = { path: row.path, text: file.text };
      }
      uploaded_file_ids[inst.instance_id] = {
        ...(uploaded_file_ids[inst.instance_id] || {}),
        [row.path]: ids.get(key),
      };
    });
  });
  return { uploaded_files, uploaded_file_ids };
};
