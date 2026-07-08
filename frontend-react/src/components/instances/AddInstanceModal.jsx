import React, { useState, useEffect, useCallback } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { AlertTriangle, LoaderCircle, X } from 'lucide-react';
import AddInstanceForm from '../addInstance/AddInstanceForm';
import { getHosts, getPresets, getPresetById, getDefaultConfigFile, createInstance } from '../../services/api';
import { useNotification } from '../NotificationProvider';
import ConfirmationModal from '../ConfirmationModal';

const CONFIG_FILES = ['server.cfg', 'mappool.txt', 'access.txt', 'workshop.txt', 'factory.factories'];

function AddInstanceModal({ isOpen, onClose, onInstanceAdded, initialHostId }) {
  const [loadingInitialData, setLoadingInitialData] = useState(false);
  const [initialDataError, setInitialDataError] = useState(null);
  const [fetchedInitialData, setFetchedInitialData] = useState({
    hosts: [],
    presets: [],
    defaultConfigContents: CONFIG_FILES.reduce((acc, fileName) => ({ ...acc, [fileName]: '' }), {}),
    defaultCheckedPlugins: [],
    defaultAvailableHooks: [],
    defaultEnabledHooks: [],
  });
  const [isLoadingSubmit, setIsLoadingSubmit] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [serverCfgHasLintErrors, setServerCfgHasLintErrors] = useState(false);
  const [isFormDirty, setIsFormDirty] = useState(false);
  const [showCloseConfirmModal, setShowCloseConfirmModal] = useState(false);

  const { showSuccess, showError } = useNotification();

  const fetchModalData = useCallback(async () => {
    if (!isOpen) return;

    setLoadingInitialData(true);
    setInitialDataError(null);
    setSubmitError(null);

    try {
      const [hostsData, presetsData] = await Promise.all([
        getHosts(),
        getPresets(),
      ]);

      const defaultConfigContents = {};
      for (const fileName of CONFIG_FILES) {
        try {
          defaultConfigContents[fileName] = await getDefaultConfigFile(fileName);
        } catch (fetchError) {
          console.error(`Failed to fetch default config for ${fileName}:`, fetchError);
          defaultConfigContents[fileName] = `// Failed to load default ${fileName}`;
        }
      }

      let defaultCheckedPlugins = [];
      let defaultAvailableHooks = [];
      let defaultEnabledHooks = [];
      const defaultPreset = (presetsData || []).find(p => p.is_builtin && p.name === 'default');
      if (defaultPreset) {
        try {
          const detail = await getPresetById(defaultPreset.id);
          if (Array.isArray(detail?.checked_plugins)) {
            defaultCheckedPlugins = detail.checked_plugins;
          }
          if (Array.isArray(detail?.user_hooks)) {
            defaultAvailableHooks = detail.user_hooks;
          }
          if (Array.isArray(detail?.enabled_hooks)) {
            defaultEnabledHooks = detail.enabled_hooks;
          }
        } catch (presetErr) {
          console.error('Failed to fetch default preset details (checked_plugins / hooks):', presetErr);
          defaultCheckedPlugins = [
            'balance.py', 'ban.py', 'clan.py', 'essentials.py', 'log.py',
            'motd.py', 'names.py', 'permission.py', 'plugin_manager.py',
            'silence.py', 'workshop.py',
          ];
        }
      }

      setFetchedInitialData({
        hosts: hostsData || [],
        presets: presetsData || [],
        defaultConfigContents,
        defaultCheckedPlugins,
        defaultAvailableHooks,
        defaultEnabledHooks,
      });
    } catch (error) {
      console.error('Failed to load initial data for AddInstanceModal:', error);
      setInitialDataError('Failed to load necessary data. Please try again.');
      setFetchedInitialData({
        hosts: [],
        presets: [],
        defaultConfigContents: CONFIG_FILES.reduce((acc, fileName) => ({ ...acc, [fileName]: `// Error loading ${fileName}` }), {}),
        defaultCheckedPlugins: [],
      });
    } finally {
      setLoadingInitialData(false);
    }
  }, [isOpen]);

  useEffect(() => {
    fetchModalData();
  }, [fetchModalData]);

  const handleSubmitInstance = async (instanceData, { consumeDraft } = {}) => {
    if (serverCfgHasLintErrors) {
      setSubmitError("Please fix errors in server.cfg before submitting.");
      showError("Please fix errors in server.cfg before submitting.");
      return;
    }
    setIsLoadingSubmit(true);
    setSubmitError(null);
    try {
      const response = await createInstance(instanceData);
      consumeDraft?.();
      showSuccess(response.message || 'Instance added successfully and task queued.');
      if (onInstanceAdded) {
        onInstanceAdded();
      }
      setIsFormDirty(false);
      onClose();
    } catch (err) {
      const errorMessage = err.error?.message || err.message || 'Failed to add instance.';
      setSubmitError(errorMessage);
      showError(errorMessage);
      console.error('Add instance error:', err);
    } finally {
      setIsLoadingSubmit(false);
    }
  };

  const handleAttemptClose = () => {
    if (isFormDirty) {
      setShowCloseConfirmModal(true);
    } else {
      onClose();
    }
  };

  const confirmClose = () => {
    setShowCloseConfirmModal(false);
    setIsFormDirty(false);
    onClose();
  };

  const cancelClose = () => {
    setShowCloseConfirmModal(false);
  };

  useEffect(() => {
    if (!isOpen) {
      setSubmitError(null);
      setServerCfgHasLintErrors(false);
      setIsFormDirty(false);
      setShowCloseConfirmModal(false);
    }
  }, [isOpen]);

  return (
    <>
      <Dialog open={isOpen} as="div" className="relative z-50" onClose={handleAttemptClose}>
        <DialogBackdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0" />

          <div className="fixed inset-0 overflow-y-auto scrollbar-thick">
            <div className="flex min-h-full items-center justify-center p-4 text-center">
                <Dialog.Panel transition className="modal-panel w-full max-w-[87.1rem] transform p-4 lg:p-6 text-left align-middle transition-all h-[90vh] max-h-[90vh] flex flex-col transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:translate-y-4 data-[closed]:scale-95">
                  {/* Accent line decoration (dark mode only) */}
                  <div className="accent-line-top" />

                  {/* Header */}
                  <Dialog.Title
                    as="h3"
                    className="relative z-10 flex items-center gap-3 mb-6 flex-shrink-0"
                  >
                    <span className="status-pulse status-pulse-active" />
                    <span className="font-display text-xl font-semibold tracking-wider uppercase text-theme-primary">
                      Add New QL Instance
                    </span>
                    <button
                      type="button"
                      onClick={handleAttemptClose}
                      className="ml-auto logs-modal-close-btn"
                    >
                      <X size={18} />
                    </button>
                  </Dialog.Title>

                  {/* Content area */}
                  <div className="relative z-10 flex flex-col flex-grow min-h-0">
                    {loadingInitialData ? (
                      <div className="flex flex-col items-center justify-center h-full gap-4">
                        {/* Light mode: simple spinner, Dark mode: tech loader */}
                        <div className="hidden dark:block">
                          <div className="loader-tech" />
                        </div>
                        <div className="dark:hidden">
                          <LoaderCircle size={48} className="animate-spin text-emerald-600" />
                        </div>
                        <span className="font-mono text-sm text-theme-secondary tracking-wide">
                          INITIALIZING<span className="animate-pulse">...</span>
                        </span>
                      </div>
                    ) : initialDataError ? (
                      <div className="alert-error flex items-start gap-3">
                        <AlertTriangle className="w-5 h-5 text-red-600 dark:text-[#FF3366] flex-shrink-0 mt-0.5" />
                        <div>
                          <p className="font-medium text-red-700 dark:text-[#FF3366]">Connection Failed</p>
                          <p className="text-sm text-theme-secondary mt-1">{initialDataError}</p>
                          <button
                            onClick={fetchModalData}
                            className="btn btn-secondary mt-3 text-xs"
                          >
                            Retry Connection
                          </button>
                        </div>
                      </div>
                    ) : (
                      <AddInstanceForm
                        initialData={fetchedInitialData}
                        initialHostId={initialHostId}
                        onSubmit={handleSubmitInstance}
                        onCancel={handleAttemptClose}
                        isLoadingSubmit={isLoadingSubmit}
                        formError={submitError}
                        onServerCfgLintStatusChange={setServerCfgHasLintErrors}
                        onDirtyStateChange={setIsFormDirty}
                      />
                    )}
                  </div>
                </Dialog.Panel>
            </div>
          </div>
      </Dialog>

      <ConfirmationModal
        isOpen={showCloseConfirmModal}
        onClose={cancelClose}
        onConfirm={confirmClose}
        title="Discard Changes?"
        message="You have unsaved changes. Are you sure you want to discard them and close?"
        confirmButtonText="Discard Changes"
        cancelButtonText="Keep Editing"
        confirmButtonVariant="danger"
        zIndexClass="z-[60]"
      />
    </>
  );
}

export default AddInstanceModal;
