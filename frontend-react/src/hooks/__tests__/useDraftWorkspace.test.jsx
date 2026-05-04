import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useDraftWorkspace } from '../useDraftWorkspace';

const mocks = vi.hoisted(() => ({
  commitDraft: vi.fn(),
  createDraft: vi.fn(),
  deleteDraftFile: vi.fn(),
  discardDraft: vi.fn(),
  getDraftContent: vi.fn(),
  getDraftTree: vi.fn(),
  renameDraftFile: vi.fn(),
  saveDraftContent: vi.fn(),
  touchDraft: vi.fn(),
  uploadToDraft: vi.fn(),
}));

vi.mock('../../services/draftApi', () => ({
  commitDraft: mocks.commitDraft,
  createDraft: mocks.createDraft,
  deleteDraftFile: mocks.deleteDraftFile,
  discardDraft: mocks.discardDraft,
  getDraftContent: mocks.getDraftContent,
  getDraftTree: mocks.getDraftTree,
  renameDraftFile: mocks.renameDraftFile,
  saveDraftContent: mocks.saveDraftContent,
  touchDraft: mocks.touchDraft,
  uploadToDraft: mocks.uploadToDraft,
}));

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe('useDraftWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('clears local draft state immediately while reseeding a new workspace', async () => {
    const firstDraft = deferred();
    const secondDraft = deferred();

    mocks.createDraft
      .mockReturnValueOnce(firstDraft.promise)
      .mockReturnValueOnce(secondDraft.promise);
    mocks.getDraftTree
      .mockResolvedValueOnce([{ type: 'file', name: 'a.py', path: 'a.py' }])
      .mockResolvedValueOnce([{ type: 'file', name: 'b.py', path: 'b.py' }]);
    mocks.discardDraft.mockResolvedValue(undefined);

    const { result, rerender } = renderHook(
      ({ preset }) => useDraftWorkspace({ source: 'preset', preset, active: true }),
      { initialProps: { preset: 'default' } }
    );

    firstDraft.resolve({ draft_id: 'draft-1' });

    await waitFor(() => expect(result.current.draftId).toBe('draft-1'));
    await waitFor(() => expect(result.current.tree).toEqual([{ type: 'file', name: 'a.py', path: 'a.py' }]));

    rerender({ preset: 'alt' });

    await waitFor(() => expect(mocks.discardDraft).toHaveBeenCalledWith('draft-1'));
    await waitFor(() => expect(result.current.draftId).toBeNull());
    expect(result.current.tree).toEqual([]);

    secondDraft.resolve({ draft_id: 'draft-2' });

    await waitFor(() => expect(result.current.draftId).toBe('draft-2'));
    await waitFor(() => expect(result.current.tree).toEqual([{ type: 'file', name: 'b.py', path: 'b.py' }]));
  });

  it('renames files and marks the workspace dirty', async () => {
    mocks.createDraft.mockResolvedValue({ draft_id: 'draft-1' });
    mocks.getDraftTree
      .mockResolvedValueOnce([{ type: 'file', name: 'old.py', path: 'old.py' }])
      .mockResolvedValueOnce([{ type: 'file', name: 'new.py', path: 'new.py' }]);
    mocks.renameDraftFile.mockResolvedValue({ old_path: 'old.py', new_path: 'new.py' });

    const { result } = renderHook(
      () => useDraftWorkspace({ source: 'preset', preset: 'default', active: true })
    );

    await waitFor(() => expect(result.current.draftId).toBe('draft-1'));
    expect(result.current.hasChanges).toBe(false);

    await act(async () => {
      await result.current.renameFile('old.py', 'new.py', {
        contextType: 'preset',
        contextKey: 'default',
      });
    });

    expect(mocks.renameDraftFile).toHaveBeenCalledWith('draft-1', 'old.py', 'new.py', {
      contextType: 'preset',
      contextKey: 'default',
    });
    expect(result.current.hasChanges).toBe(true);
    await waitFor(() => expect(result.current.tree).toEqual([
      { type: 'file', name: 'new.py', path: 'new.py' },
    ]));
  });
});
