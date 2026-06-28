import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  downloadPreset: vi.fn(),
}));

vi.mock('../../services/api', () => ({
  downloadPreset: mocks.downloadPreset,
}));

import { safePresetDownloadName, triggerPresetDownload } from '../presetDownload';

describe('safePresetDownloadName', () => {
  it('replaces unsafe characters and collapses separators', () => {
    expect(safePresetDownloadName('Unsafe Name/With:Spaces')).toBe('Unsafe-Name-With-Spaces');
  });

  it('falls back to "preset" for empty or stripped names', () => {
    expect(safePresetDownloadName('')).toBe('preset');
    expect(safePresetDownloadName('...')).toBe('preset');
    expect(safePresetDownloadName(null)).toBe('preset');
  });
});

describe('triggerPresetDownload', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.downloadPreset.mockResolvedValue(new Blob(['zip-bytes'], { type: 'application/zip' }));
    window.URL.createObjectURL = vi.fn(() => 'blob:preset');
    window.URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    delete window.URL.createObjectURL;
    delete window.URL.revokeObjectURL;
  });

  it('does nothing when the preset has no id', async () => {
    await triggerPresetDownload({ name: 'no-id' });
    expect(mocks.downloadPreset).not.toHaveBeenCalled();
  });

  it('downloads the archive with a sanitized filename', async () => {
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    await triggerPresetDownload({ id: 7, name: 'My Preset' });

    expect(mocks.downloadPreset).toHaveBeenCalledWith(7);
    const anchor = clickSpy.mock.instances[0];
    expect(anchor.download).toBe('My-Preset.zip');
    expect(window.URL.revokeObjectURL).toHaveBeenCalledWith('blob:preset');

    clickSpy.mockRestore();
  });

  it('propagates download errors to the caller', async () => {
    mocks.downloadPreset.mockRejectedValue({ error: { message: 'Preset not found.' } });
    await expect(triggerPresetDownload({ id: 9, name: 'x' })).rejects.toEqual({
      error: { message: 'Preset not found.' },
    });
  });
});
