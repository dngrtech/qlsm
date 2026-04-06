import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AddInstanceModal from '../AddInstanceModal';

const mocks = vi.hoisted(() => ({
  consumeDraft: vi.fn(),
  createInstance: vi.fn(),
  getHosts: vi.fn(),
  getPresets: vi.fn(),
  getDefaultConfigFile: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

vi.mock('../../../services/api', () => ({
  getHosts: mocks.getHosts,
  getPresets: mocks.getPresets,
  getDefaultConfigFile: mocks.getDefaultConfigFile,
  createInstance: mocks.createInstance,
}));

vi.mock('../../NotificationProvider', () => ({
  useNotification: () => ({
    showSuccess: mocks.showSuccess,
    showError: mocks.showError,
  }),
}));

vi.mock('../../ConfirmationModal', () => ({
  default: () => null,
}));

vi.mock('../../addInstance/AddInstanceForm', () => ({
  default: ({ onSubmit }) => (
    <button
      type="button"
      onClick={() => onSubmit({ name: 'test-instance' }, { consumeDraft: mocks.consumeDraft })}
    >
      Submit Instance
    </button>
  ),
}));

describe('AddInstanceModal draft handoff', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getHosts.mockResolvedValue([]);
    mocks.getPresets.mockResolvedValue([]);
    mocks.getDefaultConfigFile.mockResolvedValue('');
  });

  it('consumes the draft before closing when instance creation succeeds', async () => {
    mocks.createInstance.mockResolvedValue({ message: 'queued' });
    const onClose = vi.fn();
    const onInstanceAdded = vi.fn();

    render(
      <AddInstanceModal
        isOpen={true}
        onClose={onClose}
        onInstanceAdded={onInstanceAdded}
        initialHostId={null}
      />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /submit instance/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /submit instance/i }));

    await waitFor(() => expect(mocks.createInstance).toHaveBeenCalledTimes(1));
    expect(mocks.consumeDraft).toHaveBeenCalledTimes(1);
    expect(onInstanceAdded).toHaveBeenCalledTimes(1);
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(mocks.showSuccess).toHaveBeenCalledWith('queued');
  });

  it('does not consume the draft when instance creation fails', async () => {
    mocks.createInstance.mockRejectedValue({ error: { message: 'boom' } });
    const onClose = vi.fn();

    render(
      <AddInstanceModal
        isOpen={true}
        onClose={onClose}
        onInstanceAdded={vi.fn()}
        initialHostId={null}
      />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /submit instance/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /submit instance/i }));

    await waitFor(() => expect(mocks.showError).toHaveBeenCalledWith('boom'));
    expect(mocks.consumeDraft).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });
});
