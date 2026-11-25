import React, { useState } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../../services/addons', () => ({
  addonRequest: vi.fn(),
  addonAssetUrl: vi.fn(),
  addonDownload: vi.fn(),
  saveBlob: vi.fn(),
}));

import { addonRequest } from '../../../services/addons';
import AddonAddInstanceTab from '../AddonAddInstanceTab';

const PANEL = {
  kind: 'form',
  load: 'GET add-instance?host_id={host_id}',
  fields: [
    { key: 'telemetry', type: 'bool', label: 'Send telemetry', default: false },
    { key: 'server_id', type: 'string', label: 'Server ID' },
  ],
};

const mount = (panel = PANEL) => ({
  key: 'stats:add_instance_tabs:0',
  addon: { id: 'stats' },
  entry: { panel: 'tab' },
  panel,
  scope: 'host',
});

// The form owns the values; this harness plays the form.
function Harness({ hostId, panel, onValues, onLoadingChange }) {
  const [values, setValues] = useState(undefined);
  return (
    <AddonAddInstanceTab
      mount={mount(panel)}
      hostId={hostId}
      values={values}
      onChange={(next, options) => { setValues(next); onValues(next, options); }}
      onLoadingChange={onLoadingChange}
    />
  );
}

beforeEach(() => vi.clearAllMocks());

describe('AddonAddInstanceTab', () => {
  it('waits for a host before calling the load route, using manifest defaults meanwhile', async () => {
    const onValues = vi.fn();
    render(<Harness hostId="" onValues={onValues} />);
    await waitFor(() => expect(onValues).toHaveBeenCalledWith({ telemetry: false, server_id: '' }, { pristine: true }));
    expect(addonRequest).not.toHaveBeenCalled();
  });

  it('prefills from the load route for the picked host and reloads when it changes', async () => {
    addonRequest.mockResolvedValueOnce({ telemetry: true }).mockResolvedValueOnce({ telemetry: false });
    const onValues = vi.fn();
    const { rerender } = render(<Harness hostId="4" onValues={onValues} />);
    await waitFor(() => expect(screen.getByLabelText('Send telemetry')).toBeChecked());
    expect(addonRequest).toHaveBeenCalledWith('stats', 'GET', 'add-instance?host_id=4');

    rerender(<Harness hostId="5" onValues={onValues} />);
    await waitFor(() => expect(addonRequest).toHaveBeenCalledWith('stats', 'GET', 'add-instance?host_id=5'));
    await waitFor(() => expect(screen.getByLabelText('Send telemetry')).not.toBeChecked());
  });

  it('falls back to the manifest defaults and says so when the load fails', async () => {
    addonRequest.mockRejectedValue({ response: { data: { error: { message: 'hub down' } } } });
    const onValues = vi.fn();
    render(<Harness hostId="4" onValues={onValues} />);
    expect(await screen.findByText(/hub down/)).toBeInTheDocument();
    expect(onValues).toHaveBeenLastCalledWith({ telemetry: false, server_id: '' }, { pristine: true });
  });

  it('reports every edit to the form', async () => {
    addonRequest.mockResolvedValue({ telemetry: true });
    const onValues = vi.fn();
    render(<Harness hostId="4" onValues={onValues} />);
    await waitFor(() => expect(screen.getByLabelText('Send telemetry')).toBeChecked());
    fireEvent.change(screen.getByLabelText('Server ID'), { target: { value: '9' } });
    expect(onValues).toHaveBeenLastCalledWith({ telemetry: true, server_id: '9' }, undefined);
  });

  it('drops the previous host values and reports loading until the new prefill is in', async () => {
    let resolveSecond;
    addonRequest
      .mockResolvedValueOnce({ telemetry: true })
      .mockReturnValueOnce(new Promise((resolve) => { resolveSecond = resolve; }));
    const onValues = vi.fn();
    const onLoadingChange = vi.fn();
    const { rerender } = render(<Harness hostId="4" onValues={onValues} onLoadingChange={onLoadingChange} />);
    await waitFor(() => expect(onLoadingChange).toHaveBeenLastCalledWith(false));

    rerender(<Harness hostId="5" onValues={onValues} onLoadingChange={onLoadingChange} />);
    await waitFor(() => expect(onLoadingChange).toHaveBeenLastCalledWith(true));
    expect(onValues).toHaveBeenLastCalledWith(undefined, { pristine: true });

    resolveSecond({ telemetry: false });
    await waitFor(() => expect(onLoadingChange).toHaveBeenLastCalledWith(false));
    expect(onValues).toHaveBeenLastCalledWith({ telemetry: false, server_id: '' }, { pristine: true });
  });
});
