import { useDraftWorkspace } from '../../../hooks/useDraftWorkspace';

export function useDraftAdapter(workspaceParams) {
  const draft = useDraftWorkspace(workspaceParams);

  return {
    draftId: draft.draftId,
    tree: draft.tree || [],
    readContent: draft.readContent,
    writeContent: draft.writeContent,
    upload: draft.upload,
    deleteFile: draft.deleteFile,
    renameFile: draft.renameFile,
    createFolder: draft.createFolder,
    deleteFolder: draft.deleteFolder,
    renameFolder: draft.renameFolder,
    refreshTree: draft.refreshTree,
    hasChanges: draft.hasChanges,
    loading: draft.loading,
    error: draft.error,
    commit: draft.commit,
    consume: draft.consume,
    discard: draft.discard,
  };
}
