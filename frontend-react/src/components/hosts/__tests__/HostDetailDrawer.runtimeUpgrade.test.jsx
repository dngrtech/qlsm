import React from 'react';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import HostDetailDrawer from '../HostDetailDrawer';
import apiClient, { getHostById } from '../../../services/api';

vi.mock('../../../services/api', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  getHostById: vi.fn(),
  deleteHost: vi.fn(),
  updateHost: vi.fn(),
}));
vi.mock('../../NotificationProvider', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), addNotification: vi.fn() }),
}));
vi.mock('../../StatusIndicator', () => ({ default: () => null }));
vi.mock('../../common/InfoTooltip', () => ({
  default: ({ text }) => <span data-testid="upgrade-tooltip">{text}</span>,
}));

const baseHost = {
  id: 7, name: 'h', ip_address: '10.0.0.7', provider: 'standalone', status: 'active',
  qlfilter_status: 'not_installed', instances: [], runtime: 'minqlx', is_standalone: true,
};

async function renderDrawer(runtimeUpgrade) {
  getHostById.mockResolvedValue({ ...baseHost, runtime_upgrade: runtimeUpgrade });
  const onOpenRuntimeUpgrade = vi.fn();
  render(
    <HostDetailDrawer host={7} open onClose={vi.fn()} onOpenRuntimeUpgrade={onOpenRuntimeUpgrade}
      onQlfilterAction={vi.fn()} onRequestRestart={vi.fn()} />
  );
  await screen.findByRole('button', { name: /restart/i });
  return { onOpenRuntimeUpgrade };
}

describe('HostDetailDrawer runtime upgrade button', () => {
  beforeEach(() => vi.clearAllMocks());

  it('is hidden when not visible', async () => {
    await renderDrawer({ visible: false, enabled: false, reason: null });
    expect(screen.queryByText('Upgrade to minqlxtended')).toBeNull();
  });

  it('is disabled with the reason tooltip', async () => {
    const { onOpenRuntimeUpgrade } = await renderDrawer({ visible: true, enabled: false, reason: 'needs Ubuntu 24.04' });
    const button = screen.getByRole('button', { name: /upgrade to minqlxtended/i });
    expect(button).toHaveAttribute('aria-disabled', 'true');
    expect(within(button).getByTestId('upgrade-tooltip')).toHaveTextContent('needs Ubuntu 24.04');
    fireEvent.click(button);
    expect(onOpenRuntimeUpgrade).not.toHaveBeenCalled();
  });

  it('calls onOpenRuntimeUpgrade when enabled', async () => {
    const { onOpenRuntimeUpgrade } = await renderDrawer({ visible: true, enabled: true, reason: null });
    fireEvent.click(screen.getByRole('button', { name: /upgrade to minqlxtended/i }));
    await waitFor(() => expect(onOpenRuntimeUpgrade).toHaveBeenCalledWith(7));
  });
});


const releasePlatform = { os_id: 'ubuntu', os_version: '24.04', arch: 'x86_64', python: [3, 12] };
const currentRelease = {
  provider_id: 'arena', label: 'Arena Runtime', build: '2.0.0', sha256: '2'.repeat(64),
  plugin_api: 'minqlx', platform: releasePlatform,
};
const preview = {
  eligibility: { enabled: true, reason: null },
  current: currentRelease,
  target: { ...currentRelease, build: '3.0.0', sha256: '3'.repeat(64) },
  rollback: { ...currentRelease, build: '1.0.0', sha256: '1'.repeat(64) },
  instances: [
    { id: 12, name: 'Duel', status: 'running' },
    { id: 23, name: 'Practice', status: 'stopped' },
  ],
  fingerprint: 'first-preview',
  reason: null,
};

const updateUrl = '/hosts/7/custom-runtime-update';
const response = (data) => ({ data: { data } });
const conflict = (message) => ({ response: { status: 409, data: { error: { message } } } });

function renderCustomDrawer({ provider = 'standalone', status = 'active', pinMetadata = {} } = {}) {
  const onHostUpdated = vi.fn();
  const onClose = vi.fn();
  render(
    <HostDetailDrawer
      host={{
        ...baseHost, provider, status, is_standalone: provider === 'standalone', runtime: 'custom',
        runtime_provider_id: 'arena', runtime_provider_label: 'Arena Runtime',
        runtime_build: '2.0.0', runtime_release_sha256: currentRelease.sha256,
        runtime_upgrade: { visible: false, enabled: false, reason: null },
        ...pinMetadata,
      }}
      open onClose={onClose} onHostUpdated={onHostUpdated}
    />
  );
  return { onHostUpdated, onClose };
}

async function openCustomDialog() {
  fireEvent.click(await screen.findByRole('button', { name: 'Update Custom runtime' }));
  return screen.findByRole('dialog', { name: /update custom runtime/i });
}

describe('HostDetailDrawer Custom runtime release changes', () => {
  beforeEach(() => vi.resetAllMocks());

  it('shows the pinned release, candidates and the affected instance statuses', async () => {
    apiClient.get.mockResolvedValue(response(preview));
    const { onClose } = renderCustomDrawer();

    const dialog = within(await openCustomDialog());
    const update = await dialog.findByRole('radio', { name: /approved update/i });
    expect(update).toBeChecked();
    expect(apiClient.get).toHaveBeenCalledWith(updateUrl);
    expect(dialog.getByText('Arena Runtime')).toBeVisible();
    expect(dialog.getByText('2.0.0')).toBeVisible();
    expect(dialog.getByText('2'.repeat(64))).toBeVisible();
    expect(dialog.getByText('3'.repeat(64))).toBeVisible();
    expect(dialog.getByText('Duel').closest('li')).toHaveTextContent(/running/i);
    expect(dialog.getByText('Practice').closest('li')).toHaveTextContent(/stopped/i);

    const previous = dialog.getByRole('radio', { name: /previous release/i });
    fireEvent.mouseDown(previous);
    fireEvent.click(previous);
    expect(onClose).not.toHaveBeenCalled();
    expect(previous).toBeChecked();
    expect(dialog.getByText('1'.repeat(64))).toBeVisible();
    expect(dialog.queryByText('3'.repeat(64))).not.toBeInTheDocument();
  });

  it.each([
    ['update', /approved update/i, '3'],
    ['rollback', /previous release/i, '1'],
  ])('submits the chosen %s digest and refreshes the host only on acceptance', async (action, choice, digest) => {
    apiClient.get.mockResolvedValue(response(preview));
    let accept;
    apiClient.post.mockImplementation(() => new Promise((resolve) => { accept = resolve; }));
    const { onHostUpdated } = renderCustomDrawer();

    const dialog = within(await openCustomDialog());
    fireEvent.click(await dialog.findByRole('radio', { name: choice }));
    const confirm = dialog.getByRole('button', { name: /confirm/i });
    fireEvent.click(confirm);
    expect(confirm).toBeDisabled();
    fireEvent.click(confirm);
    expect(apiClient.post).toHaveBeenCalledExactlyOnceWith(updateUrl, {
      fingerprint: 'first-preview', target_sha256: digest.repeat(64), action,
    });
    expect(onHostUpdated).not.toHaveBeenCalled();

    accept(response({ operation_id: 41, status: 'configuring' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(onHostUpdated).toHaveBeenCalledWith(7);
  });

  it('keeps the action off non-Standalone hosts', () => {
    renderCustomDrawer({ provider: 'self' });
    expect(screen.queryByRole('button', { name: 'Update Custom runtime' })).not.toBeInTheDocument();
  });

  it('shows an ineligible preview reason and disallows confirmation', async () => {
    apiClient.get.mockResolvedValue(response({
      ...preview, eligibility: { enabled: false, reason: 'Host must be active.' },
    }));
    renderCustomDrawer({ status: 'error' });

    const dialog = within(await openCustomDialog());
    expect(await dialog.findByText('Host must be active.')).toBeVisible();
    expect(dialog.getByRole('button', { name: /confirm/i })).toBeDisabled();
    expect(apiClient.post).not.toHaveBeenCalled();
  });

  it.each([
    [undefined, /build unavailable/i],
    ['2.0.0', '2.0.0'],
  ])('shows the recorded digest when the pinned bundle is unavailable (stored build: %s)', async (build, displayedBuild) => {
    const reason = 'The pinned release bundle is unavailable.';
    apiClient.get.mockResolvedValue(response({
      ...preview,
      eligibility: { enabled: false, reason },
      current: null, target: null, rollback: null, fingerprint: null,
    }));
    renderCustomDrawer({ pinMetadata: { runtime_build: build, runtime_provider_label: undefined } });

    const dialog = within(await openCustomDialog());
    expect(await dialog.findByText(reason)).toBeVisible();
    expect(dialog.getByText('2'.repeat(64))).toBeVisible();
    expect(dialog.getByText(displayedBuild)).toBeVisible();
    expect(dialog.getByRole('button', { name: /confirm/i })).toBeDisabled();
  });

  it('shows why no approved update is available while allowing an offered rollback', async () => {
    apiClient.get.mockResolvedValue(response({
      ...preview, target: null, reason: 'The approved release is already pinned.',
    }));
    renderCustomDrawer();

    const dialog = within(await openCustomDialog());
    expect(await dialog.findByText('The approved release is already pinned.')).toBeVisible();
    expect(dialog.queryByRole('radio', { name: /approved update/i })).not.toBeInTheDocument();
    expect(dialog.getByRole('radio', { name: /previous release/i })).toBeChecked();
    expect(dialog.getByRole('button', { name: /confirm rollback/i })).toBeEnabled();
  });

  it('reloads an ineligible busy preview and enables confirmation after the host is available', async () => {
    const reason = 'The host must be ACTIVE and available for runtime maintenance.';
    apiClient.get.mockResolvedValueOnce(response({
      ...preview, eligibility: { enabled: false, reason },
      target: null, rollback: null, fingerprint: null,
    })).mockResolvedValueOnce(response(preview));
    renderCustomDrawer({ status: 'configuring' });

    const dialog = within(await openCustomDialog());
    expect(await dialog.findByText(reason)).toBeVisible();
    expect(dialog.getByRole('button', { name: /confirm/i })).toBeDisabled();
    fireEvent.click(dialog.getByRole('button', { name: /reload preview/i }));
    expect(await dialog.findByRole('radio', { name: /approved update/i })).toBeChecked();
    expect(dialog.getByRole('button', { name: /confirm update/i })).toBeEnabled();
  });

  it('invalidates a stale confirmation and submits only the reviewed replacement preview', async () => {
    const replacement = { ...preview.target, build: '4.0.0', sha256: '4'.repeat(64) };
    apiClient.get.mockResolvedValueOnce(response(preview))
      .mockResolvedValueOnce(response({ ...preview, target: replacement, fingerprint: 'second-preview' }));
    apiClient.post.mockRejectedValueOnce(conflict('The runtime preview is stale.'))
      .mockResolvedValueOnce(response({ operation_id: 47, status: 'configuring' }));
    const { onHostUpdated } = renderCustomDrawer();

    const dialog = within(await openCustomDialog());
    await dialog.findByRole('radio', { name: /approved update/i });
    fireEvent.click(dialog.getByRole('button', { name: /confirm update/i }));
    expect(await dialog.findByRole('alert')).toHaveTextContent('The runtime preview is stale.');
    expect(dialog.getByRole('button', { name: /confirm/i })).toBeDisabled();
    expect(onHostUpdated).not.toHaveBeenCalled();

    fireEvent.click(dialog.getByRole('button', { name: /reload preview/i }));
    expect(await dialog.findByText('4'.repeat(64))).toBeVisible();
    fireEvent.click(dialog.getByRole('button', { name: /confirm update/i }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(apiClient.post).toHaveBeenLastCalledWith(updateUrl, {
      fingerprint: 'second-preview', target_sha256: '4'.repeat(64), action: 'update',
    });
  });

  it('keeps the preview and shows a confirmation error when the request fails', async () => {
    apiClient.get.mockResolvedValue(response(preview));
    apiClient.post.mockRejectedValue({
      response: { status: 500, data: { error: { message: 'Could not queue runtime maintenance.' } } },
    });
    const { onHostUpdated } = renderCustomDrawer();

    const dialog = within(await openCustomDialog());
    await dialog.findByRole('radio', { name: /approved update/i });
    fireEvent.click(dialog.getByRole('button', { name: /confirm update/i }));
    expect(await dialog.findByRole('alert')).toHaveTextContent('Could not queue runtime maintenance.');
    expect(dialog.getByRole('button', { name: /confirm update/i })).toBeEnabled();
    expect(onHostUpdated).not.toHaveBeenCalled();
  });
});
