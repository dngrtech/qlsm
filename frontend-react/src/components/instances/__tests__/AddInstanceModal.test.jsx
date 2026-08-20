import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import AddInstanceModal from '../AddInstanceModal';

const mocks = vi.hoisted(() => ({
  // Captures the props the modal hands the form, so seed wiring can be asserted
  // without rendering the real 1200-line form.
  formProps: { current: null },
  consumeDraft: vi.fn(),
  createInstance: vi.fn(),
  getHosts: vi.fn(),
  getPresets: vi.fn(),
  getPresetById: vi.fn(),
  getDefaultConfigFile: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
}));

vi.mock('../../../services/api', () => ({
  getHosts: mocks.getHosts,
  getPresets: mocks.getPresets,
  getPresetById: mocks.getPresetById,
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
  default: (props) => {
    mocks.formProps.current = props;
    return (
      <button
        type="button"
        onClick={() => props.onSubmit({ name: 'test-instance' }, { consumeDraft: mocks.consumeDraft })}
      >
        Submit Instance
      </button>
    );
  },
}));

describe('AddInstanceModal draft handoff', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.formProps.current = null;
    mocks.getHosts.mockResolvedValue([]);
    mocks.getPresets.mockResolvedValue([]);
    mocks.getPresetById.mockResolvedValue({});
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

  // Seeds are per-runtime: a minqlxtended host must never be handed the minqlx
  // plugin list, so the modal resolves both builtin presets up front.
  it('fetches the builtin preset details for both runtimes', async () => {
    mocks.getPresets.mockResolvedValue([
      { id: 1, name: 'default', is_builtin: true, runtime: 'minqlx' },
      { id: 2, name: 'default-minqlxtended', is_builtin: true, runtime: 'minqlxtended' },
    ]);
    mocks.getPresetById.mockImplementation((id) => Promise.resolve(
      id === 1
        ? { checked_plugins: ['balance.py'], user_hooks: [], enabled_hooks: [] }
        : { checked_plugins: ['essentials.py'], user_hooks: [], enabled_hooks: [] }
    ));

    render(
      <AddInstanceModal
        isOpen={true}
        onClose={() => {}}
        onInstanceAdded={() => {}}
        initialHostId={null}
      />
    );

    await waitFor(() => {
      expect(mocks.getPresetById).toHaveBeenCalledWith(1);
      expect(mocks.getPresetById).toHaveBeenCalledWith(2);
    });

    expect(mocks.formProps.current.initialData.defaultSeedsByRuntime).toEqual({
      minqlx: { checkedPlugins: ['balance.py'], availableHooks: [], enabledHooks: [] },
      minqlxtended: { checkedPlugins: ['essentials.py'], availableHooks: [], enabledHooks: [] },
    });
  });

  it('leaves the minqlxtended seed empty when its builtin preset is missing', async () => {
    // Only minqlx has a safe hardcoded fallback -- guessing a minqlxtended
    // plugin list from memory is how wrong files get shipped.
    mocks.getPresets.mockResolvedValue([
      { id: 1, name: 'default', is_builtin: true, runtime: 'minqlx' },
    ]);
    mocks.getPresetById.mockRejectedValue(new Error('boom'));

    render(
      <AddInstanceModal
        isOpen={true}
        onClose={() => {}}
        onInstanceAdded={() => {}}
        initialHostId={null}
      />
    );

    await waitFor(() => expect(
      mocks.formProps.current?.initialData?.defaultSeedsByRuntime?.minqlx?.checkedPlugins,
    ).toContain('balance.py'));
    const seeds = mocks.formProps.current.initialData.defaultSeedsByRuntime;
    expect(seeds.minqlxtended).toEqual({ checkedPlugins: [], availableHooks: [], enabledHooks: [] });
  });
});
