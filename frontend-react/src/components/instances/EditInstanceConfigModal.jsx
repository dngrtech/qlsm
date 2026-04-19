import React, { useState, useEffect, useRef, Fragment, useCallback } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { X, LoaderCircle, Zap, AlertTriangle, Settings, Code2, LayoutGrid, Save, FolderOpen } from 'lucide-react';
import { python } from '@codemirror/lang-python';
import { getInstanceConfig, updateInstanceConfig, getInstanceById, getPresets, getPresetById, createPreset, updateInstance } from '../../services/api';
import { useDraftWorkspace } from '../../hooks/useDraftWorkspace';
import ConfigEditorTabs from '../config/ConfigEditorTabs';
import ExpandedEditorModal from '../ExpandedEditorModal';
import ConfirmationModal from '../ConfirmationModal';
import LoadPresetModal from '../addInstance/LoadPresetModal';
import SavePresetModal from '../addInstance/SavePresetModal';
import { ScriptManager } from '../addInstance/ScriptManager';
import FactoryManager from '../addInstance/FactoryManager/FactoryManager';
import { useNotification } from '../NotificationProvider';
import InfoTooltip from '../common/InfoTooltip';
import { qlcfgLanguage, createQlCfgLinter, stripManagedCvars } from '../../codemirror-lang-qlcfg';
import { qlmappoolLanguage } from '../../codemirror-lang-qlmappool';
import { qlaccessLanguage } from '../../codemirror-lang-qlaccess';
import { qlworkshopLanguage } from '../../codemirror-lang-qlworkshop';
import {
  canEnableLanRate,
  getLanRateUnsupportedReason,
} from '../../utils/lanRateCompatibility';

const CONFIG_FILES_ORDER = ['server.cfg', 'mappool.txt', 'access.txt', 'workshop.txt'];

const LANGUAGE_MAP = {
  'server.cfg': qlcfgLanguage,
  'mappool.txt': qlmappoolLanguage,
  'access.txt': qlaccessLanguage,
  'workshop.txt': qlworkshopLanguage,
};
const getLanguageForFile = (fileName) => LANGUAGE_MAP[fileName] || null;

// Mapping between frontend config keys and backend preset API keys
const CONFIG_KEY_MAP = {
  'server.cfg': 'server_cfg',
  'mappool.txt': 'mappool_txt',
  'access.txt': 'access_txt',
  'workshop.txt': 'workshop_txt'
};

function EditInstanceConfigModal({
  isOpen,
  onClose,
  instanceId,
  instanceName: initialInstanceName, // Rename prop to avoid conflict
  onConfigSaved,
}) {
  const [currentInstanceName, setCurrentInstanceName] = useState(initialInstanceName || '');
  const [configs, setConfigs] = useState(
    CONFIG_FILES_ORDER.reduce((acc, fileName) => {
      acc[fileName] = '';
      return acc;
    }, {})
  );
  const [presets, setPresets] = useState([]);
  const [selectedPresetId, setSelectedPresetId] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadingPresets, setLoadingPresets] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [presetError, setPresetError] = useState(null);
  const [saveError, setSaveError] = useState(null);
  const [activeTabIndex, setActiveTabIndex] = useState(0);

  // LAN Rate state
  const [lanRateEnabled, setLanRateEnabled] = useState(false);
  const [originalLanRateEnabled, setOriginalLanRateEnabled] = useState(false);
  const [hostOsType, setHostOsType] = useState(null);

  // Restart on Save state
  const [restartAfterSave, setRestartAfterSave] = useState(true);

  // Unsaved changes state
  const [isDirty, setIsDirty] = useState(false);
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);

  // New state for synced hostname
  const isUpdatingFromServerCfg = React.useRef(false);
  const [serverHostname, setServerHostname] = useState('');

  // State for ExpandedEditorModal
  const [isExpandedEditorOpen, setIsExpandedEditorOpen] = useState(false);
  const [expandedFileName, setExpandedFileName] = useState('');
  const [expandedFileContent, setExpandedFileContent] = useState('');
  const [expandedFileLanguage, setExpandedFileLanguage] = useState(null);
  const [expandedFileLinterSource, setExpandedFileLinterSource] = useState(null);
  const [expandedPluginPath, setExpandedPluginPath] = useState(null);

  // State for preset modals
  const [isLoadPresetModalOpen, setIsLoadPresetModalOpen] = useState(false);
  const [isSavePresetModalOpen, setIsSavePresetModalOpen] = useState(false);
  const [isSavingPreset, setIsSavingPreset] = useState(false);

  // Scripts tab state
  const [activeMainTab, setActiveMainTab] = useState('config'); // 'config' | 'scripts' | 'factories'
  const [checkedPlugins, setCheckedPlugins] = useState(new Set());
  const [scriptHostName, setScriptHostName] = useState(null);
  const [rawQlxPlugins, setRawQlxPlugins] = useState([]); // bare plugin names from instance
  const scriptManagerRef = useRef(null);
  const pluginsSyncedRef = useRef(false);

  // Factories tab state
  const [factories, setFactories] = useState({});

  const { showSuccess, showError } = useNotification(); // Get notification functions

  const draft = useDraftWorkspace({
    source: 'instance',
    host: scriptHostName,
    instanceId,
    active: isOpen && scriptHostName != null,
  });

  // Resolve raw qlx_plugins names to full tree paths once on initial load
  useEffect(() => {
    if (pluginsSyncedRef.current) return;
    if (rawQlxPlugins.length === 0 || draft.tree.length === 0) return;
    const fullPaths = [];
    const collectPaths = (node) => {
      if (node.type === 'file' && node.name.endsWith('.py') && node.name !== '__init__.py') {
        const basename = node.name.replace('.py', '');
        if (rawQlxPlugins.includes(basename)) {
          fullPaths.push(node.path);
        }
      } else if (node.type === 'folder' && node.children) {
        node.children.forEach(collectPaths);
      }
    };
    draft.tree.forEach(collectPaths);
    pluginsSyncedRef.current = true;
    if (fullPaths.length > 0) {
      setCheckedPlugins(new Set(fullPaths));
    }
  }, [rawQlxPlugins, draft.tree]);

  // Linter for server.cfg — no port validation in edit mode, but shows managed-cvar info tooltips
  const qlCfgLinterSource = useCallback(() => createQlCfgLinter([], () => {}), []);
  const getLinterSource = (fileName) => (fileName === 'server.cfg' ? qlCfgLinterSource : null);

  // Configure plugins based on checkboxes
  const togglePluginSelection = useCallback((filename) => {
    setCheckedPlugins(prev => {
      const newSet = new Set(prev);
      if (newSet.has(filename)) {
        newSet.delete(filename);
      } else {
        newSet.add(filename);
      }
      return newSet;
    });
    setIsDirty(true);
  }, []);


  useEffect(() => {
    if (isOpen && instanceId) {
      setCurrentInstanceName(initialInstanceName || `Instance ${instanceId}`);
      const fetchInitialData = async () => {
        setLoading(true);
        setLoadingPresets(true);
        setError(null);
        setPresetError(null);
        setSaveError(null);
        setSelectedPresetId(''); // Reset preset selection
        setActiveTabIndex(0); // Reset to first tab
        // Reset scripts state
        setActiveMainTab('config');
        setScriptHostName(null);
        pluginsSyncedRef.current = false;

        // Reset restart toggle to default (true) when opening
        setRestartAfterSave(true);

        try {
          const [instanceDetails, configData, presetsData] = await Promise.all([
            getInstanceById(instanceId),
            getInstanceConfig(instanceId),
            getPresets(),
          ]);

          // Store raw plugin names — they'll be resolved to full tree paths
          // once the draft tree loads (via the effect below).
          const configuredPlugins = instanceDetails.qlx_plugins
            ? instanceDetails.qlx_plugins.split(',').map(p => p.trim()).filter(Boolean)
            : [];
          setRawQlxPlugins(configuredPlugins);
          setCheckedPlugins(new Set());

          setCurrentInstanceName(instanceDetails.name || `Instance ${instanceId}`);
          // Store host name for Scripts and Factories tabs
          setScriptHostName(instanceDetails.host_name || null);
          setHostOsType(instanceDetails.host_os_type || null);
          const fetchedConfigs = {};
          CONFIG_FILES_ORDER.forEach(file => {
            const raw = configData[file] || '';
            fetchedConfigs[file] = file === 'server.cfg' ? stripManagedCvars(raw) : raw;
          });
          setConfigs(fetchedConfigs);
          setLanRateEnabled(instanceDetails.lan_rate_enabled || false);
          setOriginalLanRateEnabled(instanceDetails.lan_rate_enabled || false);
          setIsDirty(false); // Reset dirty state
          setPresets(presetsData || []);
          setFactories(configData.factories || {});
        } catch (err) {
          setError(err.message || `Failed to fetch initial data for instance ${instanceId}`);
          console.error("EditInstanceConfigModal: Initial data fetch error:", err);
        } finally {
          setLoading(false);
          setLoadingPresets(false);
        }
      };
      fetchInitialData();
    }
  }, [isOpen, instanceId, initialInstanceName]);

  // Sync effect: Update serverHostname when server.cfg changes (unless it's an internal update)
  useEffect(() => {
    if (!isUpdatingFromServerCfg.current && configs['server.cfg']) {
      const match = configs['server.cfg'].match(/set sv_hostname "([^"]*)"/);
      if (match && match[1] !== serverHostname) {
        setServerHostname(match[1]);
      }
    }
  }, [configs, serverHostname]);

  const handleHostnameChange = (e) => {
    const newHostname = e.target.value;
    setServerHostname(newHostname);

    // Update server.cfg
    isUpdatingFromServerCfg.current = true;
    setConfigs(prev => {
      const cfg = prev['server.cfg'] || '';
      const regex = /set sv_hostname "([^"]*)"/;
      let newCfg;
      if (regex.test(cfg)) {
        newCfg = cfg.replace(regex, `set sv_hostname "${newHostname}"`);
      } else {
        newCfg = cfg + `\nset sv_hostname "${newHostname}"`;
      }
      return { ...prev, 'server.cfg': newCfg };
    });

    setIsDirty(true);
    setTimeout(() => { isUpdatingFromServerCfg.current = false; }, 0);
  };

  const handleConfigChange = (filename, value) => {
    setConfigs(prev => ({ ...prev, [filename]: value }));
    setIsDirty(true);
  };

  const lanRateChanged = lanRateEnabled !== originalLanRateEnabled;
  const canToggleLanRate = canEnableLanRate({
    osType: hostOsType,
    currentEnabled: originalLanRateEnabled,
  });
  const lanRateUnsupportedReason = !canToggleLanRate && !lanRateEnabled
    ? getLanRateUnsupportedReason(hostOsType)
    : null;

  const handleLanRateToggle = () => {
    if (!canToggleLanRate) return;
    setLanRateEnabled(prev => {
      const next = !prev;
      if (next !== originalLanRateEnabled) setRestartAfterSave(true);
      return next;
    });
    setIsDirty(true);
  };

  const handleRestartToggle = () => {
    if (lanRateChanged) return;
    setRestartAfterSave(prev => !prev);
  }

  const handleConfigFileUpload = useCallback((content, fileName, error) => {
    if (error) {
      setSaveError(`Error uploading ${fileName}: ${error}`); // Use existing saveError state for simplicity
      return;
    }
    setSaveError(null); // Clear any previous errors
    setConfigs(prev => ({ ...prev, [fileName]: content }));
    setIsDirty(true);
  }, []);

  const handleLoadPreset = useCallback(async (presetId) => {
    setPresetError(null);
    try {
      const presetData = await getPresetById(presetId);
      const newConfigs = {};
      CONFIG_FILES_ORDER.forEach(file => {
        const presetKey = CONFIG_KEY_MAP[file] || file;
        const raw = presetData[presetKey] || '';
        newConfigs[file] = file === 'server.cfg' ? stripManagedCvars(raw) : raw;
      });
      setConfigs(newConfigs);
      setSelectedPresetId(presetId);
      setIsDirty(true);

      // Load factories from preset
      if (presetData.factories && Object.keys(presetData.factories).length > 0) {
        setFactories(presetData.factories);
      } else {
        setFactories({});
      }

      setIsLoadPresetModalOpen(false);
      showSuccess(`Preset "${presetData.name}" loaded successfully.`);
    } catch (err) {
      setPresetError(err.message || `Failed to load preset ${presetId}.`);
    }
  }, [showSuccess]);

  const handleSavePreset = useCallback(async ({ name, description }) => {
    setIsSavingPreset(true);
    setPresetError(null);
    try {
      const presetData = {
        name: name.trim(),
        description: description?.trim() || null,
        server_cfg: configs['server.cfg'] || '',
        mappool_txt: configs['mappool.txt'] || '',
        access_txt: configs['access.txt'] || '',
        workshop_txt: configs['workshop.txt'] || '',
      };

      // Include all current factory files
      if (Object.keys(factories).length > 0) {
        presetData.factories = factories;
      }

      // Flush any in-progress editor content to the draft before saving preset
      if (scriptManagerRef.current) {
        await scriptManagerRef.current.flushEdits();
      }

      // Include draft_id so the backend can snapshot draft files into the preset
      if (draft.draftId) {
        presetData.draft_id = draft.draftId;
        presetData.checked_plugins = Array.from(checkedPlugins);
      }

      const response = await createPreset(presetData);

      // Update presets list
      const updatedPresets = await getPresets();
      setPresets(updatedPresets || []);

      setIsSavePresetModalOpen(false);
      showSuccess(response.message || `Preset "${name}" saved successfully.`);
    } catch (err) {
      setPresetError(err.error?.message || err.message || 'Failed to save preset.');
      showError('Failed to save preset.');
    } finally {
      setIsSavingPreset(false);
    }
  }, [configs, factories, checkedPlugins, draft.draftId, showSuccess, showError]);

  const handlePresetDeleted = useCallback((deletedPresetId) => {
    setPresets(prevPresets => prevPresets.filter(p => p.id !== deletedPresetId));
    if (selectedPresetId === deletedPresetId.toString()) {
      setSelectedPresetId('');
    }
    showSuccess('Preset deleted successfully.');
  }, [selectedPresetId, showSuccess]);

  // Handle main tab change
  const handleMainTabChange = useCallback((tab) => {
    setActiveMainTab(tab);
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setSaveError(null);
    try {
      const lanRateChanged = lanRateEnabled !== originalLanRateEnabled;

      // Update Instance Details (Database - Name/Hostname)
      // Name is preserved (using currentInstanceName which is synced with prop/API), Hostname is updated
      const instanceUpdateData = {
        name: currentInstanceName,
        hostname: serverHostname
      };
      await updateInstance(instanceId, instanceUpdateData);

      // Flush any in-progress editor content to the draft
      if (scriptManagerRef.current) {
        await scriptManagerRef.current.flushEdits();
      }

      // Update config files
      const configPayload = { ...configs };

      // Include factories in payload (send all factories state)
      // The backend will sync the directory to match this map exactly (modifications, additions, deletions)
      if (factories) {
        configPayload.factories = factories;
      }

      if (lanRateChanged) {
        configPayload.lan_rate_enabled = lanRateEnabled;
      }

      // Send draft_id so the backend commits draft files alongside config
      if (draft.draftId) {
        configPayload.draft_id = draft.draftId;
        configPayload.checked_plugins = Array.from(checkedPlugins)
          .filter(p => p.endsWith('.py'))
          .map(p => p.replace(/\.py$/, '').replace(/^.*\//, ''));
      }

      // Pass restart parameter to updateInstanceConfig
      const response = await updateInstanceConfig(instanceId, configPayload, restartAfterSave);

      const successMsg = lanRateChanged
        ? `Configuration and LAN rate saved successfully. Task queued.`
        : (response.message || 'Configuration saved successfully. Task queued.');

      // Append info about restart status if not implicit in the message
      const restartMsg = restartAfterSave ? " (Restarting)" : " (Restart skipped)";
      showSuccess(successMsg + restartMsg);

      draft.consume();
      if (onConfigSaved) {
        onConfigSaved();
      }
      setIsDirty(false); // Reset dirty state on successful submission
      onClose(); // Close modal on success
    } catch (err) {
      const errorMessage = err.error?.message || err.message || 'Failed to save configuration.';
      setSaveError(errorMessage);
      showError(errorMessage); // Show error notification
      console.error('Save configuration error:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleExpandEditor = (fileNameToExpand) => {
    setExpandedPluginPath(null);
    setExpandedFileName(fileNameToExpand);
    setExpandedFileContent(configs[fileNameToExpand] || '');
    setExpandedFileLanguage(getLanguageForFile(fileNameToExpand));
    setExpandedFileLinterSource(getLinterSource(fileNameToExpand));
    setIsExpandedEditorOpen(true);
  };

  const handleExpandPluginEditor = useCallback((selectedFile, content) => {
    setExpandedPluginPath(selectedFile.path);
    setExpandedFileName(selectedFile.name);
    setExpandedFileContent(content);
    setExpandedFileLanguage(selectedFile.name.endsWith('.py') ? python() : null);
    setExpandedFileLinterSource(null);
    setIsExpandedEditorOpen(true);
  }, []);

  const handleExpandedEditorContentChange = (newContent) => {
    setExpandedFileContent(newContent);
    if (expandedPluginPath) {
      if (scriptManagerRef.current?.updateContent) {
        scriptManagerRef.current.updateContent(expandedPluginPath, newContent);
      }
    } else {
      setConfigs(prev => ({ ...prev, [expandedFileName]: newContent }));
    }
    setIsDirty(true);
  };

  const handleCloseExpandedEditor = () => {
    // Potentially add unsaved changes check for expanded modal here if needed
    setIsExpandedEditorOpen(false);
  };

  const handleAttemptClose = () => {
    if (isDirty) {
      setShowCloseConfirm(true);
    } else {
      draft.discard();
      onClose(); // Call original onClose if not dirty
    }
  };

  const confirmModalClose = () => {
    setShowCloseConfirm(false);
    setIsDirty(false); // Reset dirty state as we are discarding changes
    draft.discard();
    onClose(); // Call original onClose
  };

  const cancelModalClose = () => {
    setShowCloseConfirm(false);
  };

  // Reset dirty state when modal is truly closed (not just confirmation hidden)
  useEffect(() => {
    if (!isOpen) {
      setIsDirty(false);
      setShowCloseConfirm(false);
      // Other states like configs, selectedPresetId are reset by fetchInitialData
      // when isOpen becomes true again.
    }
  }, [isOpen]);

  const effectiveInstanceName = currentInstanceName || initialInstanceName || `Instance ${instanceId}`;


  return (
    <>
      <Transition appear show={isOpen} as={Fragment}>
        <Dialog as="div" className="relative z-50" onClose={handleAttemptClose}>
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-300"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-200"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="modal-backdrop fixed inset-0" aria-hidden="true" />
          </Transition.Child>

          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-center justify-center p-4 text-center">
              <Transition.Child
                as={Fragment}
                enter="ease-out duration-300"
                enterFrom="opacity-0 translate-y-4 scale-95"
                enterTo="opacity-100 translate-y-0 scale-100"
                leave="ease-in duration-200"
                leaveFrom="opacity-100 scale-100"
                leaveTo="opacity-0 scale-95"
              >
                <Dialog.Panel className="modal-panel w-full max-w-6xl transform p-4 lg:p-6 text-left align-middle transition-all h-[90vh] max-h-[90vh] flex flex-col">
                  {/* Accent line decoration (dark mode only) */}
                  <div className="accent-line-top" />

                  {/* Header */}
                  <Dialog.Title
                    as="h3"
                    className="relative z-10 flex items-center justify-between gap-3 mb-2 lg:mb-4 flex-shrink-0"
                  >
                    <div className="flex items-center gap-3">
                      <span className="status-pulse status-pulse-active" />
                      <span className="font-display text-xl font-semibold tracking-wider uppercase text-theme-primary">
                        Edit Configuration: {effectiveInstanceName}
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={handleAttemptClose}
                      className="logs-modal-close-btn"
                      aria-label="Close editor"
                    >
                      <X size={16} />
                    </button>
                  </Dialog.Title>

                  {/* Content area */}
                  <div className="relative z-10 flex flex-col flex-grow min-h-0">
                    {loading ? (
                      <div className="flex flex-col items-center justify-center h-full gap-4">
                        {/* Light mode: simple spinner, Dark mode: tech loader */}
                        <div className="hidden dark:block">
                          <div className="loader-tech" />
                        </div>
                        <div className="dark:hidden">
                          <LoaderCircle size={48} className="animate-spin text-emerald-600" />
                        </div>
                        <span className="font-mono text-sm text-theme-secondary tracking-wide">
                          LOADING CONFIGURATION<span className="animate-pulse">...</span>
                        </span>
                      </div>
                    ) : error ? (
                      <div className="alert-error flex items-start gap-3">
                        <AlertTriangle className="w-5 h-5 text-red-600 dark:text-[#FF3366] flex-shrink-0 mt-0.5" />
                        <div>
                          <p className="font-medium text-red-700 dark:text-[#FF3366]">Failed to Load Configuration</p>
                          <p className="text-sm text-theme-secondary mt-1">{error}</p>
                        </div>
                      </div>
                    ) : (
                      <form onSubmit={handleSubmit} className="flex flex-col flex-grow min-h-0">
                        {/* Server Hostname Input */}
                        <div className="mb-2 lg:mb-4 flex-shrink-0">
                          <label htmlFor="serverHostname" className="label-tech mb-1.5 block">
                            Server Hostname
                          </label>
                          <div className="relative">
                            <input
                              type="text"
                              name="serverHostname"
                              id="serverHostname"
                              value={serverHostname}
                              onChange={handleHostnameChange}
                              className="input-base pr-16"
                              placeholder="Enter server hostname"
                            />
                            <span className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none">
                              <span className="font-mono text-[10px] font-bold tracking-wider uppercase px-1.5 py-0.5 rounded bg-[var(--surface-elevated)] border border-[var(--surface-border)] text-[var(--text-muted)]">
                                AUTO
                              </span>
                            </span>
                          </div>
                          <p className="mt-1 text-sm text-[var(--text-muted)] hidden lg:block">
                            Synced with <code className="text-xs bg-[var(--surface-elevated)] px-1 py-0.5 rounded font-mono text-[var(--text-secondary)]">sv_hostname</code> in server.cfg.
                          </p>
                        </div>

                        <div className="mb-2 lg:mb-4 flex-shrink-0 flex flex-wrap items-end gap-4">
                          {presetError && (
                            <p className="text-sm font-medium text-theme-danger">{presetError}</p>
                          )}

                          {/* Toggle Switches Container */}
                          <div className="flex items-center gap-6 pb-1">
                            {/* LAN Rate Toggle */}
                            <div className="flex items-center gap-3">
                              <button
                                type="button"
                                onClick={handleLanRateToggle}
                                disabled={saving || loading || !canToggleLanRate}
                                className="neu-toggle"
                                aria-pressed={lanRateEnabled}
                              >
                                <span className="sr-only">Toggle 99k LAN Rate</span>
                                <span className={`neu-toggle__track ${lanRateEnabled ? 'neu-toggle__track--on' : 'neu-toggle__track--off'}`}>
                                  <span className={`neu-toggle__knob ${lanRateEnabled ? 'neu-toggle__knob--on' : 'neu-toggle__knob--off'}`} />
                                </span>
                              </button>
                              <span className="flex items-center gap-1.5 text-sm font-medium text-[var(--text-primary)]">
                                <Zap size={16} className={`mr-1 ${lanRateEnabled ? 'text-[var(--accent-warning)]' : 'text-[var(--text-muted)]'}`} />
                                <span>99k LAN Rate</span>
                                {lanRateUnsupportedReason && (
                                  <InfoTooltip text={lanRateUnsupportedReason} variant="danger" size={14} />
                                )}
                              </span>
                            </div>

                            {/* Restart Toggle */}
                            <div className="flex items-center gap-3 border-l border-[var(--surface-border)] pl-6">
                              <button
                                type="button"
                                onClick={handleRestartToggle}
                                disabled={saving || loading || lanRateChanged}
                                className="neu-toggle"
                                aria-pressed={restartAfterSave}
                              >
                                <span className="sr-only">Toggle Restart after Save</span>
                                <span className={`neu-toggle__track ${restartAfterSave ? 'neu-toggle__track--on' : 'neu-toggle__track--off'}`}>
                                  <span className={`neu-toggle__knob ${restartAfterSave ? 'neu-toggle__knob--on' : 'neu-toggle__knob--off'}`} />
                                </span>
                              </button>
                              <span className={`flex items-center text-sm font-medium ${lanRateChanged ? 'text-[var(--text-muted)]' : 'text-[var(--text-primary)]'}`}>
                                <span className={`mr-1 ${restartAfterSave ? 'text-[var(--accent-primary)]' : 'text-[var(--text-muted)]'}`}>
                                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-rotate-cw"><path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" /><path d="M21 3v5h-5" /></svg>
                                </span>
                                Restart after saving
                              </span>
                              {lanRateChanged && (
                                <InfoTooltip text="Changing 99k LAN Rate requires an instance restart" variant="warning" size={14} />
                              )}
                            </div>
                          </div>
                        </div>

                        {saveError && (
                          <div className="alert-error flex items-start gap-3 mb-4 flex-shrink-0">
                            <AlertTriangle className="w-5 h-5 text-red-600 dark:text-[#FF3366] flex-shrink-0 mt-0.5" />
                            <div>
                              <p className="font-medium text-red-700 dark:text-[#FF3366]">Save Error</p>
                              <p className="text-sm text-theme-secondary mt-1">{saveError}</p>
                            </div>
                          </div>
                        )}

                        {/* Main tabs: Configuration Files | Scripts | Factories */}
                        <div className="flex flex-shrink-0 border border-[var(--surface-border)] bg-[var(--surface-elevated)] rounded-t-lg overflow-hidden mb-0">
                          {[
                            { key: 'config', icon: Settings, label: 'Configuration Files' },
                            { key: 'scripts', icon: Code2, label: 'Plugins' },
                            { key: 'factories', icon: LayoutGrid, label: 'Factories' },
                          ].map((tab) => (
                            <button
                              key={tab.key}
                              type="button"
                              onClick={() => handleMainTabChange(tab.key)}
                              className={`flex items-center gap-2 px-4 py-2.5 lg:px-6 lg:py-3.5 text-[12px] lg:text-[13px] font-display font-semibold tracking-wide uppercase border-b-2 border-r border-r-[var(--surface-border)] transition-all duration-200 ${activeMainTab === tab.key
                                ? 'border-b-[var(--accent-primary)] text-[var(--accent-primary)] bg-[var(--accent-primary)]/5'
                                : 'border-b-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-base)]/50'
                                }`}
                            >
                              {React.createElement(tab.icon, { size: 16 })}
                              {tab.label}
                            </button>
                          ))}
                        </div>

                        {/* Content area */}
                        <div className="flex-grow min-h-0 bg-[var(--surface-base)] border-x border-b border-[var(--surface-border)] rounded-b-xl p-4 flex flex-col">
                          {activeMainTab === 'config' ? (
                            <ConfigEditorTabs
                              configFilesOrder={CONFIG_FILES_ORDER}
                              configs={configs}
                              onConfigChange={handleConfigChange}
                              onExpandEditor={handleExpandEditor}
                              activeTabIndex={activeTabIndex}
                              onTabChange={setActiveTabIndex}
                              getLanguageForFile={getLanguageForFile}
                              getLinterSourceForFile={getLinterSource}
                              onConfigFileUpload={handleConfigFileUpload}
                            />
                          ) : activeMainTab === 'scripts' ? (
                            <ScriptManager
                              ref={scriptManagerRef}
                              draftId={draft.draftId}
                              tree={draft.tree}
                              onTreeRefresh={draft.refreshTree}
                              readContent={draft.readContent}
                              writeContent={draft.writeContent}
                              upload={draft.upload}
                              deleteFile={draft.deleteFile}
                              checkable={true}
                              checkedFiles={checkedPlugins}
                              onCheck={togglePluginSelection}
                              loading={draft.loading}
                              error={draft.error}
                              onExpandEditor={handleExpandPluginEditor}
                            />
                          ) : (
                            <FactoryManager
                              factories={factories}
                              onFactoriesChange={setFactories}
                              isNewInstance={false}
                              preset="default"
                              hostId={scriptHostName}
                              instanceId={instanceId}
                              checkable={true}
                            />
                          )}
                        </div>

                        <div className="mt-2 pt-2 lg:mt-4 lg:pt-4 border-t border-[var(--surface-border)] flex justify-between items-center flex-shrink-0">
                          {/* Left side - Preset management buttons */}
                          <div className="flex gap-2">
                            <button type="button" onClick={() => setIsLoadPresetModalOpen(true)} className="btn btn-secondary">
                              <FolderOpen className="w-4 h-4 mr-2" />
                              Load Preset
                            </button>
                            <button type="button" onClick={() => setIsSavePresetModalOpen(true)} className="btn btn-secondary">
                              <Save className="w-4 h-4 mr-2" />
                              Save Preset
                            </button>
                          </div>

                          {/* Right side - Esc hint + Cancel/Save */}
                          <div className="flex items-center gap-3">
                            <span className="font-mono text-xs text-[var(--text-muted)] tracking-wide hidden sm:inline-flex items-center gap-1.5">
                              <kbd className="px-1.5 py-0.5 rounded bg-[var(--surface-elevated)] border border-[var(--surface-border)] text-[10px] font-bold">Esc</kbd>
                              to close
                            </span>
                            <button type="button" onClick={handleAttemptClose} className="btn btn-secondary">
                              Cancel
                            </button>
                            <button
                              type="submit"
                              disabled={saving || loading}
                              className="btn btn-primary"
                            >
                              {saving ? (
                                <span className="flex items-center">
                                  <LoaderCircle size={16} className="animate-spin mr-2" />
                                  Saving...
                                </span>
                              ) : 'Save Configuration'}
                            </button>
                          </div>
                        </div>
                      </form>
                    )}
                  </div>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </Dialog>
      </Transition>

      {isExpandedEditorOpen && (
        <ExpandedEditorModal
          isOpen={isExpandedEditorOpen}
          onClose={handleCloseExpandedEditor}
          fileName={expandedFileName}
          fileContent={expandedFileContent}
          onContentChange={handleExpandedEditorContentChange}
          language={expandedFileLanguage}
          linterSource={expandedFileLinterSource}
        />
      )}

      <ConfirmationModal
        isOpen={showCloseConfirm}
        onClose={cancelModalClose}
        onConfirm={confirmModalClose}
        title="Discard Changes?"
        message="You have unsaved changes. Are you sure you want to discard them?"
        confirmButtonText="Discard"
        cancelButtonText="Keep Editing"
        confirmButtonVariant="danger"
        zIndexClass="z-[60]"
      />

      {/* Load Preset Modal */}
      <LoadPresetModal
        isOpen={isLoadPresetModalOpen}
        onClose={() => setIsLoadPresetModalOpen(false)}
        onLoad={handleLoadPreset}
        presets={presets}
        isLoading={loadingPresets}
        zIndexClass="z-[60]"
        onPresetDeleted={handlePresetDeleted}
      />

      {/* Save Preset Modal */}
      <SavePresetModal
        isOpen={isSavePresetModalOpen}
        onClose={() => setIsSavePresetModalOpen(false)}
        onSave={handleSavePreset}
        isSaving={isSavingPreset}
        zIndexClass="z-[60]"
        initialDescription=""
      />
    </>
  );
}

export default EditInstanceConfigModal;
