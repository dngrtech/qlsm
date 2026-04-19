import React, { useImperativeHandle } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import EditInstanceConfigModal from '../EditInstanceConfigModal';

const mocks = vi.hoisted(() => ({
  createPreset: vi.fn(),
  flushEdits: vi.fn(),
  getInstanceById: vi.fn(),
  getInstanceConfig: vi.fn(),
  getPresetById: vi.fn(),
  getPresets: vi.fn(),
  showError: vi.fn(),
  showSuccess: vi.fn(),
  updateInstance: vi.fn(),
  updateInstanceConfig: vi.fn(),
  useDraftWorkspace: vi.fn(),
}));

vi.mock('@headlessui/react', () => {
  const Dialog = ({ children }) => <div>{children}</div>;
  Dialog.Panel = ({ children, ...props }) => <div {...props}>{children}</div>;
  Dialog.Title = ({ children, ...props }) => <div {...props}>{children}</div>;

  const Transition = ({ show, children }) => (show ? <>{children}</> : null);
  Transition.Child = ({ children }) => <>{children}</>;

  return { Dialog, Transition };
});

vi.mock('../../../services/api', () => ({
  createPreset: mocks.createPreset,
  getInstanceById: mocks.getInstanceById,
  getInstanceConfig: mocks.getInstanceConfig,
  getPresetById: mocks.getPresetById,
  getPresets: mocks.getPresets,
  updateInstance: mocks.updateInstance,
  updateInstanceConfig: mocks.updateInstanceConfig,
}));

vi.mock('../../../hooks/useDraftWorkspace', () => ({
  useDraftWorkspace: mocks.useDraftWorkspace,
}));

vi.mock('../../NotificationProvider', () => ({
  useNotification: () => ({
    showError: mocks.showError,
    showSuccess: mocks.showSuccess,
  }),
}));

vi.mock('../../config/ConfigEditorTabs', () => ({
  default: () => <div>config-tabs</div>,
}));

vi.mock('../../ExpandedEditorModal', () => ({
  default: () => null,
}));

vi.mock('../../ConfirmationModal', () => ({
  default: () => null,
}));

vi.mock('../../addInstance/LoadPresetModal', () => ({
  default: () => null,
}));

vi.mock('../../addInstance/SavePresetModal', () => ({
  default: ({ isOpen, onSave }) => (
    isOpen ? (
      <button
        type="button"
        onClick={() => onSave({ name: 'saved-from-edit', description: 'copy' })}
      >
        Confirm Save Preset
      </button>
    ) : null
  ),
}));

vi.mock('../../addInstance/FactoryManager/FactoryManager', () => ({
  default: () => <div>factory-manager</div>,
}));

vi.mock('../../common/InfoTooltip', () => ({
  default: () => null,
}));

vi.mock('../../addInstance/ScriptManager', () => ({
  ScriptManager: React.forwardRef(function MockScriptManager(_props, ref) {
    useImperativeHandle(ref, () => ({
      flushEdits: mocks.flushEdits,
    }));
    return <div>script-manager</div>;
  }),
}));

vi.mock('../../../codemirror-lang-qlcfg', () => ({
  qlcfgLanguage: {},
  createQlCfgLinter: vi.fn(() => vi.fn()),
  stripManagedCvars: vi.fn((value) => value),
}));

vi.mock('../../../codemirror-lang-qlmappool', () => ({
  qlmappoolLanguage: {},
}));

vi.mock('../../../codemirror-lang-qlaccess', () => ({
  qlaccessLanguage: {},
}));

vi.mock('../../../codemirror-lang-qlworkshop', () => ({
  qlworkshopLanguage: {},
}));

describe('EditInstanceConfigModal preset saving', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.createPreset.mockResolvedValue({ message: 'saved' });
    mocks.flushEdits.mockResolvedValue(undefined);
    mocks.getInstanceById.mockResolvedValue({
      host_name: 'test-host',
      lan_rate_enabled: false,
      name: 'Test123',
      qlx_plugins: 'balance',
    });
    mocks.getInstanceConfig.mockResolvedValue({
      'server.cfg': 'set sv_hostname "Test123"',
      'mappool.txt': '',
      'access.txt': '',
      'workshop.txt': '',
      factories: {},
    });
    mocks.getPresetById.mockResolvedValue(null);
    mocks.getPresets.mockResolvedValue([]);
    mocks.updateInstance.mockResolvedValue({});
    mocks.updateInstanceConfig.mockResolvedValue({ message: 'saved' });
    mocks.useDraftWorkspace.mockReturnValue({
      draftId: 'draft-123',
      tree: [
        {
          type: 'folder',
          name: 'discord_extensions',
          path: 'discord_extensions',
          children: [
            {
              type: 'file',
              name: 'balance.py',
              path: 'discord_extensions/balance.py',
            },
          ],
        },
      ],
      loading: false,
      error: null,
      refreshTree: vi.fn(),
      readContent: vi.fn(),
      writeContent: vi.fn(),
      upload: vi.fn(),
      deleteFile: vi.fn(),
      commit: vi.fn(),
      discard: vi.fn(),
      consume: vi.fn(),
    });
  });

  it('preserves checked plugin file paths when saving a preset from edit mode', async () => {
    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={1}
        instanceName="Test123"
        onConfigSaved={vi.fn()}
      />
    );

    await waitFor(() => expect(screen.getByRole('button', { name: /save preset/i })).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /save preset/i }));
    fireEvent.click(screen.getByRole('button', { name: /confirm save preset/i }));

    await waitFor(() => expect(mocks.createPreset).toHaveBeenCalledTimes(1));
    expect(mocks.createPreset).toHaveBeenCalledWith(
      expect.objectContaining({
        draft_id: 'draft-123',
        checked_plugins: ['discord_extensions/balance.py'],
      })
    );
  });

  it('disables enabling 99k lan rate for ubuntu hosts', async () => {
    mocks.getInstanceById.mockResolvedValue({
      host_name: 'ubuntu-host',
      host_os_type: 'ubuntu',
      lan_rate_enabled: false,
      name: 'UbuntuInst',
      qlx_plugins: '',
    });

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={7}
        instanceName="UbuntuInst"
        onConfigSaved={vi.fn()}
      />
    );

    const toggle = await screen.findByRole('button', { name: /toggle 99k lan rate/i });
    expect(toggle).toBeDisabled();
    expect(screen.getByText('99k LAN rate is not compatible with Ubuntu.')).toBeInTheDocument();
  });

  it('allows disabling an already-enabled ubuntu instance', async () => {
    mocks.getInstanceById.mockResolvedValue({
      host_name: 'ubuntu-host',
      host_os_type: 'ubuntu',
      lan_rate_enabled: true,
      name: 'UbuntuInst',
      qlx_plugins: '',
    });

    render(
      <EditInstanceConfigModal
        isOpen={true}
        onClose={vi.fn()}
        instanceId={8}
        instanceName="UbuntuInst"
        onConfigSaved={vi.fn()}
      />
    );

    const toggle = await screen.findByRole('button', { name: /toggle 99k lan rate/i });
    expect(toggle).not.toBeDisabled();
    expect(toggle).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute('aria-pressed', 'false');
  });
});
