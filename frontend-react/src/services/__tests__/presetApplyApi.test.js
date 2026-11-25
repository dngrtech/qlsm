import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  create: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    create: mocks.create.mockReturnValue({
      get: mocks.get,
      post: mocks.post,
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() },
      },
    }),
  },
}));

import { applyPresetToInstance, getPresetKeepCvars, previewPresetApply } from '../api';

describe('preset apply API helpers', () => {
  beforeEach(() => {
    mocks.get.mockReset();
    mocks.post.mockReset();
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  it('getPresetKeepCvars asks for the preset by query parameter', async () => {
    mocks.get.mockResolvedValueOnce({ data: { data: [{ cvar: 'sv_tags', sources: ['launch args'] }] } });

    await expect(getPresetKeepCvars(3, 9)).resolves.toEqual([{ cvar: 'sv_tags', sources: ['launch args'] }]);
    expect(mocks.get).toHaveBeenCalledWith('/instances/3/preset-keep-cvars?preset_id=9');
  });

  it('previewPresetApply posts the body and returns the preview', async () => {
    const preview = { needs_decision: false, target: { hostname: 'h' }, preview_hash: 'x' };
    mocks.post.mockResolvedValueOnce({ data: { data: preview } });

    await expect(previewPresetApply(3, { preset_id: 9, keep_draft: true })).resolves.toEqual(preview);
    expect(mocks.post).toHaveBeenCalledWith('/instances/3/preset-preview', { preset_id: 9, keep_draft: true });
  });

  it('applyPresetToInstance posts the body and returns the whole response body', async () => {
    mocks.post.mockResolvedValueOnce({ data: { message: 'queued', data: { task_id: 't' } } });

    await expect(applyPresetToInstance(3, { preset_id: 9, restart: true, preview_hash: 'x' }))
      .resolves.toEqual({ message: 'queued', data: { task_id: 't' } });
    expect(mocks.post).toHaveBeenCalledWith(
      '/instances/3/apply-preset', { preset_id: 9, restart: true, preview_hash: 'x' });
  });

  it('rethrows the server error body', async () => {
    const body = { error: { message: 'Preset or server changed since the preview. Preview again.' } };
    mocks.post.mockRejectedValueOnce({ response: { data: body } });

    await expect(applyPresetToInstance(3, { preset_id: 9 })).rejects.toEqual(body);
  });

  it('applyPresetToInstance rethrows the status with the error body', async () => {
    const body = { error: { message: 'Another operation is running on instance "x". Please wait for it to complete.' } };
    mocks.post.mockRejectedValueOnce({ response: { status: 409, data: body } });

    await expect(applyPresetToInstance(3, { preset_id: 9 })).rejects.toEqual({ ...body, status: 409 });
  });
});
