import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import PluginUploadControl from '../PluginUploadControl';
import { validateRuntimeUploadPlugin } from '../../../services/runtimeUpgradeApi';

vi.mock('../../../services/runtimeUpgradeApi', () => ({
  validateRuntimeUploadPlugin: vi.fn(),
}));

const pyFile = (name, text = 'print(1)') => new File([text], name, { type: 'text/x-python' });

function setup(props = {}) {
  const handlers = { onUploaded: vi.fn(), onRemove: vi.fn(), onPendingChange: vi.fn() };
  const utils = render(
    <PluginUploadControl hostId={5} path="x76admin.py" upload={null} {...handlers} {...props} />,
  );
  return { ...handlers, ...utils };
}

describe('PluginUploadControl', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('has an accessible py-only file input and labelled button', () => {
    const { container } = setup();
    expect(container.querySelector('input[type="file"]')).toHaveAttribute('accept', '.py');
    expect(screen.getByRole('button', { name: 'Upload x76admin.py' })).toBeInTheDocument();
  });

  it('rejects a file with another name without calling the server', async () => {
    const user = userEvent.setup({ applyAccept: false });
    const { container, onUploaded } = setup();
    await user.upload(container.querySelector('input[type="file"]'), pyFile('other.py'));
    expect(await screen.findByText('Need a file named x76admin.py')).toBeInTheDocument();
    expect(validateRuntimeUploadPlugin).not.toHaveBeenCalled();
    expect(onUploaded).not.toHaveBeenCalled();
  });

  it('reports a valid upload', async () => {
    validateRuntimeUploadPlugin.mockResolvedValue({ path: 'x76admin.py', verdict: 'unknown' });
    const user = userEvent.setup();
    const { container, onUploaded } = setup();
    await user.upload(container.querySelector('input[type="file"]'), pyFile('x76admin.py', 'hello'));
    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith({ name: 'x76admin.py', text: 'hello' }));
    expect(validateRuntimeUploadPlugin).toHaveBeenCalledWith(5, { path: 'x76admin.py', text: 'hello' });
  });

  it('labels an existing upload as manual and unverified', () => {
    setup({ upload: { name: 'x76admin.py', text: 'hello' } });
    expect(screen.getByText('Uploaded manually, not verified on minqlxtended')).toBeInTheDocument();
  });

  it('shows the message and every reason on a validation error', async () => {
    validateRuntimeUploadPlugin.mockRejectedValue({
      response: { data: { error: { message: 'Not valid.', reasons: ['reason one', 'reason two'] } } },
    });
    const user = userEvent.setup();
    const { container, onUploaded } = setup();
    await user.upload(container.querySelector('input[type="file"]'), pyFile('x76admin.py'));
    expect(await screen.findByText('Not valid.')).toBeInTheDocument();
    expect(screen.getByText('reason one')).toBeInTheDocument();
    expect(screen.getByText('reason two')).toBeInTheDocument();
    expect(onUploaded).not.toHaveBeenCalled();
  });

  it('disables the button while validating and reports pending', async () => {
    let resolve;
    validateRuntimeUploadPlugin.mockReturnValue(new Promise((r) => { resolve = r; }));
    const user = userEvent.setup();
    const { container, onPendingChange } = setup();
    await user.upload(container.querySelector('input[type="file"]'), pyFile('x76admin.py'));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Upload x76admin.py' })).toBeDisabled());
    expect(onPendingChange).toHaveBeenCalledWith(true);
    resolve({ path: 'x76admin.py', verdict: 'unknown' });
    await waitFor(() => expect(onPendingChange).toHaveBeenLastCalledWith(false));
    expect(screen.getByRole('button', { name: 'Upload x76admin.py' })).not.toBeDisabled();
  });

  it('shows Replace and Remove for an uploaded file', async () => {
    const user = userEvent.setup();
    const { onRemove } = setup({ upload: { name: 'x76admin.py', text: 'a' } });
    expect(screen.getByRole('button', { name: 'Replace x76admin.py' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Remove uploaded x76admin.py' }));
    expect(onRemove).toHaveBeenCalled();
  });
});
