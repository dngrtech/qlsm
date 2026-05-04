import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  requestUse: vi.fn(),
  responseUse: vi.fn(),
  create: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    create: mocks.create.mockReturnValue({
      get: mocks.get,
      post: mocks.post,
      put: mocks.put,
      interceptors: {
        request: { use: mocks.requestUse },
        response: { use: mocks.responseUse },
      },
    }),
  },
}));

import { getSelfHostDefaults, resizeHost, updateInstanceConfig } from '../api';

describe('getSelfHostDefaults', () => {
  beforeEach(() => {
    mocks.get.mockReset();
  });

  it('fetches self-host defaults', async () => {
    mocks.get.mockResolvedValue({
      data: {
        data: {
          ssh_user: 'rage',
          host_ip: '203.0.113.10',
          provider_capabilities: { vultr: { configured: false } },
        },
      },
    });

    await expect(getSelfHostDefaults()).resolves.toEqual({
      ssh_user: 'rage',
      host_ip: '203.0.113.10',
      provider_capabilities: { vultr: { configured: false } },
    });
    expect(mocks.get).toHaveBeenCalledWith('/hosts/self/defaults');
  });
});

describe('updateInstanceConfig', () => {
  beforeEach(() => {
    mocks.put.mockReset();
  });

  it('keeps draft and LAN-rate fields at the top level of the payload', async () => {
    mocks.put.mockResolvedValue({ data: { message: 'ok' } });

    await updateInstanceConfig(
      7,
      {
        'server.cfg': 'set sv_hostname "Test"',
        draft_id: 'draft-123',
        checked_plugins: [],
        lan_rate_enabled: false,
        factories: { 'base.factories': 'factory contents' },
      },
      false,
    );

    expect(mocks.put).toHaveBeenCalledWith('/instances/7/config', {
      configs: { 'server.cfg': 'set sv_hostname "Test"' },
      restart: false,
      draft_id: 'draft-123',
      checked_plugins: [],
      lan_rate_enabled: false,
      factories: { 'base.factories': 'factory contents' },
    });
  });

  it('passes explicit config maps and metadata through unchanged', async () => {
    mocks.put.mockResolvedValue({ data: { message: 'ok' } });

    await updateInstanceConfig(
      7,
      {
        name: 'Arena 7',
        hostname: 'Arena Host',
        configs: {
          'server.cfg': 'server',
          'custom.cfg': 'custom',
        },
        factories: { 'base.factories': 'factory contents' },
        draft_id: 'draft-456',
        checked_plugins: ['balance.py'],
        lan_rate_enabled: true,
      },
      true,
    );

    expect(mocks.put).toHaveBeenCalledWith('/instances/7/config', {
      name: 'Arena 7',
      hostname: 'Arena Host',
      configs: {
        'server.cfg': 'server',
        'custom.cfg': 'custom',
      },
      restart: true,
      draft_id: 'draft-456',
      checked_plugins: ['balance.py'],
      lan_rate_enabled: true,
      factories: { 'base.factories': 'factory contents' },
    });
  });
});

describe('resizeHost', () => {
  beforeEach(() => {
    mocks.post.mockReset();
  });

  it('posts the target plan to the resize endpoint', async () => {
    mocks.post.mockResolvedValue({ data: { message: 'queued' } });

    await expect(resizeHost(4, 'vc2-2c-4gb')).resolves.toEqual({ message: 'queued' });
    expect(mocks.post).toHaveBeenCalledWith('/hosts/4/resize', { new_plan: 'vc2-2c-4gb' });
  });
});
