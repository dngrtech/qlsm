import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('../api', () => ({
  default: {
    get: mocks.get,
    post: mocks.post,
  },
}));

import { createDraft, downloadDraftFile } from '../draftApi';

describe('downloadDraftFile', () => {
  beforeEach(() => {
    mocks.get.mockReset();
  });

  it('requests a blob and returns the exact response object', async () => {
    const blob = new Blob([new Uint8Array([0, 255, 128, 65])]);
    mocks.get.mockResolvedValue({ data: blob });

    await expect(downloadDraftFile('draft-1', 'fonts/score.ttf')).resolves.toBe(blob);
    expect(mocks.get).toHaveBeenCalledWith(
      '/drafts/draft-1/file?path=fonts%2Fscore.ttf',
      { responseType: 'blob' },
    );
  });
});

describe('createDraft', () => {
  beforeEach(() => {
    mocks.post.mockReset();
    mocks.post.mockResolvedValue({ data: { data: { draft_id: 'd1' } } });
  });

  it('sends target_runtime and accepted_replacements when given', async () => {
    await createDraft({
      source: 'preset', preset: 'p',
      targetRuntime: 'minqlxtended', acceptedReplacements: ['a.py'],
    });
    expect(mocks.post).toHaveBeenCalledWith('/drafts/', {
      source: 'preset', preset: 'p',
      target_runtime: 'minqlxtended', accepted_replacements: ['a.py'],
    });
  });

  it('omits both when absent, so a same-runtime load is unchanged', async () => {
    await createDraft({ source: 'preset', preset: 'p' });
    expect(mocks.post).toHaveBeenCalledWith('/drafts/', { source: 'preset', preset: 'p' });
  });
});
