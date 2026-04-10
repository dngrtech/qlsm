import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  requestUse: vi.fn(),
  responseUse: vi.fn(),
  create: vi.fn(),
}));

vi.mock('axios', () => ({
  default: {
    create: mocks.create.mockReturnValue({
      get: mocks.get,
      put: mocks.put,
      interceptors: {
        request: { use: mocks.requestUse },
        response: { use: mocks.responseUse },
      },
    }),
  },
}));

import { getSelfHostDefaults, updateInstanceConfig } from '../api';

describe('getSelfHostDefaults', () => {
  beforeEach(() => {
    mocks.get.mockReset();
  });

  it('fetches self-host defaults', async () => {
    mocks.get.mockResolvedValue({
      data: { data: { ssh_user: 'rage', gateway_ip: '172.17.0.1' } },
    });

    await expect(getSelfHostDefaults()).resolves.toEqual({
      ssh_user: 'rage',
      gateway_ip: '172.17.0.1',
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
});
