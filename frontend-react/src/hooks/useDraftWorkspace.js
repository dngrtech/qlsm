import { useState, useEffect, useRef, useCallback } from 'react';
import {
  createDraft,
  discardDraft,
  touchDraft,
  getDraftTree,
  getDraftContent,
  saveDraftContent,
  uploadToDraft,
  deleteDraftFile,
  commitDraft,
} from '../services/draftApi';

const HEARTBEAT_INTERVAL_MS = 15 * 60 * 1000;

export function useDraftWorkspace({ source, preset, host, instanceId, active }) {
  const [draftId, setDraftId] = useState(null);
  const [tree, setTree] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const heartbeatRef = useRef(null);
  const ownedDraftIdRef = useRef(null);

  const stopHeartbeat = useCallback(() => {
    if (heartbeatRef.current) {
      clearInterval(heartbeatRef.current);
      heartbeatRef.current = null;
    }
  }, []);

  const clearDraftState = useCallback(() => {
    setDraftId(null);
    setTree([]);
  }, []);

  useEffect(() => {
    if (!active) return;
    let cancelled = false;
    clearDraftState();

    const init = async () => {
      setLoading(true);
      setError(null);
      try {
        const { draft_id } = await createDraft({ source, preset, host, instanceId });
        if (cancelled) {
          discardDraft(draft_id).catch(() => {});
          return;
        }
        ownedDraftIdRef.current = draft_id;
        setDraftId(draft_id);
        const treeData = await getDraftTree(draft_id);
        if (cancelled) return;
        setTree(treeData);
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to create draft');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    init();
    return () => {
      cancelled = true;
      stopHeartbeat();
      clearDraftState();
      const ownedDraftId = ownedDraftIdRef.current;
      if (ownedDraftId) {
        ownedDraftIdRef.current = null;
        discardDraft(ownedDraftId).catch(() => {});
      }
    };
  }, [active, source, preset, host, instanceId, stopHeartbeat, clearDraftState]);

  useEffect(() => {
    if (!draftId || !active) return;

    heartbeatRef.current = setInterval(() => {
      touchDraft(draftId).catch(() => {});
    }, HEARTBEAT_INTERVAL_MS);

    return () => {
      stopHeartbeat();
    };
  }, [draftId, active, stopHeartbeat]);

  const refreshTree = useCallback(async () => {
    if (!draftId) return;
    try {
      const treeData = await getDraftTree(draftId);
      setTree(treeData);
    } catch (err) {
      setError(err.message || 'Failed to refresh tree');
    }
  }, [draftId]);

  const readContent = useCallback(async (path) => {
    if (!draftId) return null;
    const result = await getDraftContent(draftId, path);
    return result.content;
  }, [draftId]);

  const writeContent = useCallback(async (path, content) => {
    if (!draftId) return;
    await saveDraftContent(draftId, path, content);
  }, [draftId]);

  const upload = useCallback(async (file, targetPath = '') => {
    if (!draftId) return;
    const result = await uploadToDraft(draftId, file, targetPath);
    await refreshTree();
    return result;
  }, [draftId, refreshTree]);

  const deleteFile = useCallback(async (path) => {
    if (!draftId) return;
    await deleteDraftFile(draftId, path);
    await refreshTree();
  }, [draftId, refreshTree]);

  const commit = useCallback(async (target) => {
    if (!draftId) return;
    await commitDraft(draftId, target);
    ownedDraftIdRef.current = null;
    stopHeartbeat();
    clearDraftState();
  }, [draftId, stopHeartbeat, clearDraftState]);

  const discard = useCallback(async () => {
    if (!draftId) return;
    const currentDraftId = draftId;
    ownedDraftIdRef.current = null;
    stopHeartbeat();
    try {
      await discardDraft(currentDraftId);
    } catch {
      // Draft may already be gone
    }
    clearDraftState();
  }, [draftId, stopHeartbeat, clearDraftState]);

  const consume = useCallback(() => {
    ownedDraftIdRef.current = null;
    stopHeartbeat();
    clearDraftState();
  }, [stopHeartbeat, clearDraftState]);

  return {
    draftId, tree, loading, error,
    refreshTree, readContent, writeContent, upload, deleteFile, commit, discard, consume,
  };
}
