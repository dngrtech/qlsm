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
    refreshTree: draft.refreshTree,
    hasChanges: draft.hasChanges,
    loading: draft.loading,
    error: draft.error,
    commit: draft.commit,
    consume: draft.consume,
    discard: draft.discard,
  };
}
