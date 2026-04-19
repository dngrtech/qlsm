import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { LoaderCircle, Save, FolderOpen, RefreshCw, Settings, Code2, LayoutGrid, CheckCircle } from 'lucide-react';
import { getAvailablePortsForHost, getPresetById, savePreset, updatePreset } from '../../services/api';
import { useDraftWorkspace } from '../../hooks/useDraftWorkspace';
import InstanceBasicInfoForm from './InstanceBasicInfoForm';
import InstanceConfigTabs from './InstanceConfigTabs';
import SavePresetModal from './SavePresetModal';
import LoadPresetModal from './LoadPresetModal';
import UpdatePresetModal from './UpdatePresetModal';
import FullScreenConfigEditorModal from '../config/FullScreenConfigEditorModal';
import { ScriptManager } from './ScriptManager';
import FactoryManager from './FactoryManager/FactoryManager';
import {
  qlcfgLanguage,
  createQlCfgLinter,
  stripManagedCvars
} from '../../codemirror-lang-qlcfg';
import { qlmappoolLanguage } from '../../codemirror-lang-qlmappool';
import { qlaccessLanguage } from '../../codemirror-lang-qlaccess';
import { qlworkshopLanguage } from '../../codemirror-lang-qlworkshop';
import {
  getLanRateUnsupportedReason,
  isLanRateSupported,
} from '../../utils/lanRateCompatibility';

const CONFIG_FILES = ['server.cfg', 'mappool.txt', 'access.txt', 'workshop.txt'];
const NET_PORT_REGEX = /^(set\s+net_port\s+").*(".*)/m;

// Mapping from internal config keys to API keys
const CONFIG_TO_API_MAP = {
  'server.cfg': 'server_cfg',
  'mappool.txt': 'mappool_txt',
  'access.txt': 'access_txt',
  'workshop.txt': 'workshop_txt'
};

// Reverse mapping from API keys to internal config keys
const API_TO_CONFIG_MAP = {
  'server_cfg': 'server.cfg',
  'mappool_txt': 'mappool.txt',
  'access_txt': 'access.txt',
  'workshop_txt': 'workshop.txt'
};

function AddInstanceForm({
  initialData,
  initialHostId,
  onSubmit,
  onCancel,
  isLoadingSubmit,
  formError: submissionError,
  onServerCfgLintStatusChange,
  onDirtyStateChange,
}) {
  const [name, setName] = useState('');
  const [selectedHostId, setSelectedHostId] = useState('');
  const [port, setPort] = useState('');
  const [hostname, setHostname] = useState('');
  const [lanRateEnabled, setLanRateEnabled] = useState(false);
  const [configContents, setConfigContents] = useState(initialData.defaultConfigContents || CONFIG_FILES.reduce((acc, fileName) => ({ ...acc, [fileName]: '' }), {}));
  const [availablePorts, setAvailablePorts] = useState([]);
  const [loadingPorts, setLoadingPorts] = useState(false);
  const [internalFormError, setInternalFormError] = useState(null);
  const [serverCfgHasLintErrors, setServerCfgHasLintErrors] = useState(false);
  const [activeTabIndex, setActiveTabIndex] = useState(0);
  const [isFullScreenEditorOpen, setIsFullScreenEditorOpen] = useState(false);
  const [editingFileDetails, setEditingFileDetails] = useState({ name: '', content: '', language: undefined, linterSource: null });

  // Preset modal states
  const [showSavePresetModal, setShowSavePresetModal] = useState(false);
  const [showLoadPresetModal, setShowLoadPresetModal] = useState(false);
  const [isSavingPreset, setIsSavingPreset] = useState(false);
  const [isLoadingPreset, setIsLoadingPreset] = useState(false);

  // Local presets state (allows filtering after deletion without refetching)
  const [presets, setPresets] = useState(initialData.presets || []);

  // Loaded preset tracking
  const [loadedPreset, setLoadedPreset] = useState(null); // { id, name, description } or null
  const [isPresetModified, setIsPresetModified] = useState(false);
  const [isUpdatingPreset, setIsUpdatingPreset] = useState(false);
  const [showUpdateConfirm, setShowUpdateConfirm] = useState(false);

  // Scripts tab state
  const [activeMainTab, setActiveMainTab] = useState('config'); // 'config' | 'scripts' | 'factories'
  const [checkedPlugins, setCheckedPlugins] = useState(new Set([
    'balance.py', 'ban.py', 'clan.py', 'essentials.py', 'log.py', 'motd.py', 'names.py', 'permission.py', 'plugin_manager.py', 'silence.py', 'workshop.py'
  ]));
  const scriptManagerRef = useRef(null);
  const [draftPreset, setDraftPreset] = useState('default');
  const draft = useDraftWorkspace({
    source: 'preset',
    preset: draftPreset,
    active: true,
  });

  // Factories tab state
  const [factories, setFactories] = useState({}); // { path: content }


  const isUpdatingFromServerCfg = useRef(false);
  const prevHostnameRef = useRef(hostname);
  const hostnameRef = useRef(hostname);
  const isUpdatingPortFromServerCfg = useRef(false);
  const prevPortRef = useRef(port);
  const portRef = useRef(port);
  const availablePortsRef = useRef(availablePorts);
  const portFetchAbortRef = useRef(null);

  const initialNameRef = useRef('');
  const initialSelectedHostIdRef = useRef('');
  const initialPortRef = useRef('');
  const initialHostnameRef = useRef('');
  const initialLanRateEnabledRef = useRef(false);
  const initialConfigContentsRef = useRef(initialData.defaultConfigContents || CONFIG_FILES.reduce((acc, fileName) => ({ ...acc, [fileName]: '' }), {}));
  const loadedPresetConfigRef = useRef(null); // Stores config contents when preset is loaded, for modification detection

  const handleHostChange = useCallback(async (hostId, isInitialLoad = false) => {
    setSelectedHostId(hostId);
    let newAvailablePorts = [];
    if (hostId) {
      try {
        setLoadingPorts(true);
        setInternalFormError(null);
        portFetchAbortRef.current?.abort();
        const controller = new AbortController();
        portFetchAbortRef.current = controller;
        const portsData = await getAvailablePortsForHost(hostId, controller.signal);
        newAvailablePorts = portsData.available_ports || [];
        setAvailablePorts(newAvailablePorts);

        if (isInitialLoad && newAvailablePorts.length > 0) {
          const sortedPorts = [...newAvailablePorts].sort((a, b) => a - b);
          const lowestPort = String(sortedPorts[0]);

          isUpdatingPortFromServerCfg.current = true;
          setPort(lowestPort);
          initialPortRef.current = lowestPort;
          setTimeout(() => isUpdatingPortFromServerCfg.current = false, 0);

          setConfigContents(prev => {
            const currentServerCfg = prev['server.cfg'] || '';
            const portRegex = NET_PORT_REGEX;
            let newCfg = currentServerCfg;
            if (portRegex.test(currentServerCfg)) {
              newCfg = currentServerCfg.replace(portRegex, `$1${lowestPort}$2`);
            } else if (currentServerCfg.trim() !== '') {
              newCfg = `${currentServerCfg}\nset net_port "${lowestPort}"`;
            } else {
              newCfg = `set net_port "${lowestPort}"`;
            }

            initialConfigContentsRef.current = {
              ...initialConfigContentsRef.current,
              'server.cfg': newCfg
            };

            return { ...prev, 'server.cfg': newCfg };
          });
        }
      } catch (err) {
        if (err?.name === 'AbortError' || err?.name === 'CanceledError') return;
        setInternalFormError(err.message || 'Failed to load available ports.');
        setAvailablePorts([]);
      } finally { setLoadingPorts(false); }
    } else { setAvailablePorts([]); }

    if (!isInitialLoad) {
      const currentPortVal = portRef.current;
      if (currentPortVal && (!hostId || (hostId && !newAvailablePorts.includes(parseInt(currentPortVal, 10))))) {
        setPort('');
        setConfigContents(prev => {
          const currentServerCfg = prev['server.cfg'] || '';
          return { ...prev, 'server.cfg': currentServerCfg.replace(NET_PORT_REGEX, `// $1${currentPortVal}$2 (Port removed)`) };
        });
      }
    }
  }, []);

  useEffect(() => {
    const currentDefaultConfigs = initialData.defaultConfigContents || CONFIG_FILES.reduce((acc, fileName) => ({ ...acc, [fileName]: '' }), {});
    setConfigContents(currentDefaultConfigs);
    initialConfigContentsRef.current = currentDefaultConfigs;

    let initialHostnameFromCfg = '';
    const defaultConfigServerCfg = initialData.defaultConfigContents?.['server.cfg'];
    if (defaultConfigServerCfg) {
      const hostnameRegex = /^set\s+sv_hostname\s+"([^"]*)"/m;
      const hnMatch = defaultConfigServerCfg.match(hostnameRegex);
      if (hnMatch && hnMatch[1]) initialHostnameFromCfg = hnMatch[1];
    }

    setHostname(initialHostnameFromCfg);
    prevHostnameRef.current = initialHostnameFromCfg;

    const startHostId = initialHostId ? String(initialHostId) : '';

    initialNameRef.current = '';
    initialSelectedHostIdRef.current = startHostId;
    // Default to empty; overwritten by handleHostChange with the auto-selected port when startHostId is set
    initialPortRef.current = '';
    initialHostnameRef.current = initialHostnameFromCfg;
    initialLanRateEnabledRef.current = false;

    setName('');
    setPort('');
    setLanRateEnabled(false);

    if (startHostId) {
      handleHostChange(startHostId, true);
    } else {
      setSelectedHostId('');
    }

    return () => { portFetchAbortRef.current?.abort(); };
  }, [initialData.defaultConfigContents, initialHostId, handleHostChange]);

  // Sync presets state when initialData.presets changes
  useEffect(() => {
    setPresets(initialData.presets || []);
  }, [initialData.presets]);

  useEffect(() => { hostnameRef.current = hostname; }, [hostname]);
  useEffect(() => { portRef.current = port; }, [port]);
  useEffect(() => { availablePortsRef.current = availablePorts; }, [availablePorts]);

  useEffect(() => {
    const isDirty =
      name !== initialNameRef.current ||
      selectedHostId !== initialSelectedHostIdRef.current ||
      port !== initialPortRef.current ||
      hostname !== initialHostnameRef.current ||
      lanRateEnabled !== initialLanRateEnabledRef.current ||
      JSON.stringify(configContents) !== JSON.stringify(initialConfigContentsRef.current);
    if (onDirtyStateChange) onDirtyStateChange(isDirty);
  }, [name, selectedHostId, port, hostname, lanRateEnabled, configContents, onDirtyStateChange]);

  // Track if loaded preset has been modified
  useEffect(() => {
    if (loadedPreset && loadedPresetConfigRef.current) {
      const modified = JSON.stringify(configContents) !== JSON.stringify(loadedPresetConfigRef.current);
      setIsPresetModified(modified);
    }
  }, [configContents, loadedPreset]);

  useEffect(() => {
    if (hostname !== '' && hostname !== prevHostnameRef.current && !isUpdatingFromServerCfg.current) {
      if (configContents['server.cfg']) {
        const currentServerCfg = configContents['server.cfg'];
        const hostnameRegex = /^(set\s+sv_hostname\s+").*(".*)/m;
        setConfigContents(prev => ({ ...prev, 'server.cfg': hostnameRegex.test(currentServerCfg) ? currentServerCfg.replace(hostnameRegex, `$1${hostname}$2`) : `${currentServerCfg}\nset sv_hostname "${hostname}"` }));
      } else if (!configContents['server.cfg']) {
        setConfigContents(prev => ({ ...prev, 'server.cfg': `set sv_hostname "${hostname}"` }));
      }
    }
    prevHostnameRef.current = hostname;
  }, [hostname, configContents]);

  useEffect(() => {
    if (port !== '' && port !== prevPortRef.current && !isUpdatingPortFromServerCfg.current) {
      // Skip if server.cfg already reflects this port (e.g. set during auto-populate or config edit)
      const currentCfg = configContents['server.cfg'] || '';
      const existingMatch = currentCfg.match(/^set\s+net_port\s+"(\d+)"/m);
      if (!(existingMatch && existingMatch[1] === port)) {
        setConfigContents(prev => {
          const currentServerCfg = prev['server.cfg'] || '';
          return { ...prev, 'server.cfg': NET_PORT_REGEX.test(currentServerCfg) ? currentServerCfg.replace(NET_PORT_REGEX, `$1${port}$2`) : `${currentServerCfg}\nset net_port "${port}"` };
        });
      }
    }
    prevPortRef.current = port;
  }, [port, configContents]);

  // Handle loading a preset
  const handleLoadPreset = useCallback(async (presetId) => {
    setIsLoadingPreset(true);
    try {
      setInternalFormError(null);
      const presetData = await getPresetById(presetId);

      // Map API keys to internal config keys, stripping managed cvars from server.cfg
      const newConfigs = CONFIG_FILES.reduce((acc, fileName) => {
        const apiKey = CONFIG_TO_API_MAP[fileName];
        const raw = presetData[apiKey] || '';
        acc[fileName] = fileName === 'server.cfg' ? stripManagedCvars(raw) : raw;
        return acc;
      }, {});

      // Extract hostname and port from preset server.cfg, patching newConfigs before setting state
      let newInitialHostname = hostnameRef.current;
      let newInitialPort = portRef.current;

      if (newConfigs['server.cfg']) {
        const hostnameMatch = newConfigs['server.cfg'].match(/^set\s+sv_hostname\s+"([^"]*)"/m);
        if (hostnameMatch && hostnameMatch[1]) {
          newInitialHostname = hostnameMatch[1];
          isUpdatingFromServerCfg.current = true;
          setHostname(newInitialHostname);
          setTimeout(() => isUpdatingFromServerCfg.current = false, 0);
        }

        const portMatch = newConfigs['server.cfg'].match(/^set\s+net_port\s+"(\d+)"/m);
        if (portMatch && portMatch[1]) {
          const presetPort = portMatch[1];
          if (availablePortsRef.current.includes(parseInt(presetPort, 10))) {
            newInitialPort = presetPort;
            isUpdatingPortFromServerCfg.current = true;
            setPort(newInitialPort);
            setTimeout(() => isUpdatingPortFromServerCfg.current = false, 0);
          } else {
            // Preset port not available — sync server.cfg to match current port dropdown
            const currentPort = portRef.current;
            if (currentPort) {
              newConfigs['server.cfg'] = newConfigs['server.cfg'].replace(NET_PORT_REGEX, `$1${currentPort}$2`);
            }
          }
        }
      }

      setConfigContents(newConfigs);
      initialConfigContentsRef.current = newConfigs;

      // Track which preset was loaded (for update feature)
      setLoadedPreset({ id: presetId, name: presetData.name, description: presetData.description || '' });
      // Reseed draft workspace with the loaded preset's scripts
      setDraftPreset(presetData.name);
      loadedPresetConfigRef.current = newConfigs;
      setIsPresetModified(false);

      initialHostnameRef.current = newInitialHostname;
      initialPortRef.current = newInitialPort;

      // Load factories from preset
      if (presetData.factories && Object.keys(presetData.factories).length > 0) {
        setFactories(presetData.factories);
      } else {
        setFactories({});
      }

      // Restore checked plugins state saved with the preset.
      // null means the preset pre-dates this feature — keep current defaults.
      if (presetData.checked_plugins != null) {
        setCheckedPlugins(new Set(presetData.checked_plugins));
      }

      setShowLoadPresetModal(false);
    } catch (err) {
      setInternalFormError(err.error?.message || err.message || `Failed to load preset.`);
    } finally {
      setIsLoadingPreset(false);
    }
  }, []);


  // Handle saving current config as a preset
  const handleSavePreset = useCallback(async ({ name, description }) => {
    setIsSavingPreset(true);
    try {
      // Map internal config keys to API keys
      const presetData = {
        name,
        description: description || null,
      };

      for (const [configKey, apiKey] of Object.entries(CONFIG_TO_API_MAP)) {
        presetData[apiKey] = configContents[configKey] || '';
      }

      // Flush any pending script edits before saving
      if (scriptManagerRef.current) {
        await scriptManagerRef.current.flushEdits();
      }

      // Include draft_id so backend can pull scripts from draft workspace
      if (draft.draftId) {
        presetData.draft_id = draft.draftId;
      }

      // Include factories (only checked files in AddInstance mode)
      if (Object.keys(factories).length > 0) {
        presetData.factories = factories;
      }

      // Always persist the checked plugins state so loading the preset
      // restores which plugins were ticked (including newly ticked or uploaded ones)
      presetData.checked_plugins = Array.from(checkedPlugins);

      await savePreset(presetData);
      setShowSavePresetModal(false);
      setInternalFormError(null);
    } catch (err) {
      // Don't close modal on error, let user retry
      setInternalFormError(err.error?.message || err.message || 'Failed to save preset.');
    } finally {
      setIsSavingPreset(false);
    }
  }, [configContents, draft.draftId, factories, checkedPlugins]);

  // Show confirmation dialog before updating preset
  const handleUpdatePresetClick = useCallback(() => {
    setShowUpdateConfirm(true);
  }, []);

  // Actually perform the update after confirmation
  const handleConfirmUpdate = useCallback(async (description) => {
    if (!loadedPreset) return;

    setShowUpdateConfirm(false);
    setIsUpdatingPreset(true);
    try {
      const presetData = {
        description: description,
      };
      for (const [configKey, apiKey] of Object.entries(CONFIG_TO_API_MAP)) {
        presetData[apiKey] = configContents[configKey] || '';
      }

      // Flush any pending script edits before updating
      if (scriptManagerRef.current) {
        await scriptManagerRef.current.flushEdits();
      }

      // Include draft_id so backend can pull scripts from draft workspace
      if (draft.draftId) {
        presetData.draft_id = draft.draftId;
      }

      // Include factories (only checked files in AddInstance mode)
      if (Object.keys(factories).length > 0) {
        presetData.factories = factories;
      }

      // Persist the current checked plugins state
      presetData.checked_plugins = Array.from(checkedPlugins);

      await updatePreset(loadedPreset.id, presetData);

      // Reset modified state after successful save and update loaded preset description
      loadedPresetConfigRef.current = { ...configContents };
      setLoadedPreset(prev => ({ ...prev, description: description || '' }));
      setIsPresetModified(false);
      setInternalFormError(null);
    } catch (err) {
      setInternalFormError(err.error?.message || err.message || 'Failed to update preset.');
    } finally {
      setIsUpdatingPreset(false);
    }
  }, [loadedPreset, configContents, draft.draftId, factories, checkedPlugins]);

  // Handle preset deletion from LoadPresetModal
  const handlePresetDeleted = useCallback((deletedPresetId) => {
    // Remove from local presets list
    setPresets(prev => prev.filter(p => p.id !== deletedPresetId));

    // If deleted preset was the loaded one, clear it
    if (loadedPreset?.id === deletedPresetId) {
      setLoadedPreset(null);
      loadedPresetConfigRef.current = null;
      setIsPresetModified(false);
    }
  }, [loadedPreset]);

  // Handle main tab change
  const handleMainTabChange = useCallback((tab) => {
    setActiveMainTab(tab);
  }, []);

  const handleConfigChange = useCallback((fileName, newContent) => {
    setConfigContents(prev => ({ ...prev, [fileName]: newContent }));
    if (fileName === 'server.cfg') {
      const hostnameMatch = newContent.match(/^set\s+sv_hostname\s+"([^"]*)"/m);
      if (hostnameMatch && hostnameMatch[1] !== hostnameRef.current) { isUpdatingFromServerCfg.current = true; setHostname(hostnameMatch[1]); setTimeout(() => isUpdatingFromServerCfg.current = false, 0); }
      const portMatch = newContent.match(/^set\s+net_port\s+"(\d+)"/m);
      if (portMatch && portMatch[1] !== portRef.current) { const portVal = portMatch[1]; if (availablePortsRef.current.includes(parseInt(portVal, 10))) { isUpdatingPortFromServerCfg.current = true; setPort(portVal); setTimeout(() => isUpdatingPortFromServerCfg.current = false, 0); } }
    }
  }, []);

  const editorOnChangeHandlers = useMemo(() => (CONFIG_FILES.reduce((acc, fileName) => { acc[fileName] = (newContent) => handleConfigChange(fileName, newContent); return acc; }, {})), [handleConfigChange]);
  const handleInternalServerCfgLint = useCallback((hasErrors) => { setServerCfgHasLintErrors(hasErrors); if (onServerCfgLintStatusChange) onServerCfgLintStatusChange(hasErrors); }, [onServerCfgLintStatusChange]);
  const qlCfgLinterSource = useCallback(() => (createQlCfgLinter(availablePorts, handleInternalServerCfgLint)), [availablePorts, handleInternalServerCfgLint]);
  const handleExpandEditor = useCallback((fileName) => {
    let language;
    switch (fileName) {
      case 'server.cfg':
        language = qlcfgLanguage;
        break;
      case 'mappool.txt':
        language = qlmappoolLanguage;
        break;
      case 'access.txt':
        language = qlaccessLanguage;
        break;
      case 'workshop.txt':
        language = qlworkshopLanguage;
        break;
      default:
        language = undefined;
    }
    setEditingFileDetails({
      name: fileName,
      content: configContents[fileName] || '',
      language,
      linterSource: fileName === 'server.cfg' ? qlCfgLinterSource : null,
    });
    setIsFullScreenEditorOpen(true);
  }, [configContents, qlCfgLinterSource]);
  const handleCloseFullScreenEditor = useCallback(() => { setIsFullScreenEditorOpen(false); }, []);
  const handleSaveFullScreenEditor = useCallback((newContent) => { const fileName = editingFileDetails.name; handleConfigChange(fileName, newContent); setIsFullScreenEditorOpen(false); }, [editingFileDetails.name, handleConfigChange]);
  const effectiveHostId = selectedHostId || (initialHostId ? String(initialHostId) : '');
  const selectedHost = (initialData.hosts || []).find((host) => String(host.id) === String(effectiveHostId));
  const selectedHostOsType = selectedHost?.os_type ?? null;
  const hasSelectedHost = Boolean(selectedHost);
  const lanRateSupported = !hasSelectedHost || isLanRateSupported(selectedHostOsType);
  const lanRateUnavailableReason = hasSelectedHost && !lanRateSupported
    ? getLanRateUnsupportedReason(selectedHostOsType)
    : null;

  useEffect(() => {
    if (!lanRateSupported && lanRateEnabled) {
      setLanRateEnabled(false);
    }
  }, [lanRateEnabled, lanRateSupported]);

  const handleFileUpload = useCallback((content, fileName, error) => {
    if (error) {
      setInternalFormError(`Error uploading ${fileName}: ${error}`);
      return;
    }
    setInternalFormError(null);
    setConfigContents(prev => ({ ...prev, [fileName]: content }));
    if (fileName === 'server.cfg') {
      const hostnameMatch = content.match(/^set\s+sv_hostname\s+"([^"]*)"/m);
      if (hostnameMatch && hostnameMatch[1] !== hostnameRef.current) { isUpdatingFromServerCfg.current = true; setHostname(hostnameMatch[1]); setTimeout(() => isUpdatingFromServerCfg.current = false, 0); }
      const portMatch = content.match(/^set\s+net_port\s+"(\d+)"/m);
      if (portMatch && portMatch[1] !== portRef.current) { const portVal = portMatch[1]; if (availablePortsRef.current.includes(parseInt(portVal, 10))) { isUpdatingPortFromServerCfg.current = true; setPort(portVal); setTimeout(() => isUpdatingPortFromServerCfg.current = false, 0); } }
    }
  }, [availablePortsRef, hostnameRef, portRef]);

  const localHandleSubmit = async (e) => {
    e.preventDefault();
    if (serverCfgHasLintErrors) { setInternalFormError("Please fix errors in server.cfg before submitting."); return; }
    setInternalFormError(null);

    // Flush any pending script edits to the draft workspace
    if (scriptManagerRef.current) {
      await scriptManagerRef.current.flushEdits();
    }

    const submitData = {
      name,
      host_id: parseInt(selectedHostId, 10),
      port: parseInt(port, 10),
      hostname,
      lan_rate_enabled: lanRateEnabled,
      configs: configContents
    };

    // Pass draft workspace ID instead of inline scripts
    if (draft.draftId) {
      submitData.draft_id = draft.draftId;
    }

    // Convert checked plugins for qlx_plugins cvar
    submitData.checked_plugins = Array.from(checkedPlugins)
      .filter(p => p.endsWith('.py') && !p.endsWith('__init__.py'))
      .map(p => p.replace(/\.py$/, '').replace(/^.*\//, ''));

    if (submitData.checked_plugins.length > 0) {
      submitData.qlx_plugins = submitData.checked_plugins.join(', ');
    } else {
      submitData.qlx_plugins = '';
    }

    // Include factories - ALWAYS send factories key (even if empty {})
    submitData.factories = factories;

    await onSubmit(submitData, { consumeDraft: draft.consume });
  };

  // Discard draft workspace on cancel/close
  const handleCancel = useCallback(() => {
    draft.discard();
    onCancel();
  }, [draft, onCancel]);

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
  }, []);

  return (
    <form onSubmit={localHandleSubmit} className="flex flex-col flex-grow min-h-0 pt-4">
      <div className="flex-shrink-0 mb-6">
        <InstanceBasicInfoForm name={name} onNameChange={(e) => setName(e.target.value)} selectedHostId={selectedHostId} onHostChange={handleHostChange} hosts={initialData.hosts || []} port={port} onPortChange={setPort} availablePorts={availablePorts} loadingPorts={loadingPorts} hostname={hostname} onHostnameChange={(e) => setHostname(e.target.value)} lanRateEnabled={lanRateEnabled} onLanRateChange={setLanRateEnabled} lanRateDisabled={!lanRateSupported} lanRateUnavailableReason={lanRateUnavailableReason} />
      </div>
      <div className="flex flex-col flex-grow min-h-0 mb-6">
        {/* Show loaded preset indicator */}
        {loadedPreset && (
          <div className="flex items-center text-sm text-[var(--text-secondary)] mb-2 flex-shrink-0">
            <span>Editing preset:</span>
            <span className="font-medium text-[var(--text-primary)] ml-1">{loadedPreset.name}</span>
            {isPresetModified && (
              <span className="text-[var(--accent-warning)] ml-1.5">(modified)</span>
            )}
          </div>
        )}

        {/* Main tabs: Configuration Files | Scripts | Factories */}
        <div className="flex flex-col flex-grow min-h-0">
          {/* Tab bar container */}
          <div className="flex flex-shrink-0 border border-[var(--surface-border)] bg-[var(--surface-elevated)] rounded-t-lg overflow-hidden">
            {[
              { key: 'config', icon: Settings, label: 'Configuration Files' },
              { key: 'scripts', icon: Code2, label: 'Plugins' },
              { key: 'factories', icon: LayoutGrid, label: 'Factories' },
            ].map((tab) => (
              <button
                key={tab.key}
                type="button"
                onClick={() => handleMainTabChange(tab.key)}
                className={`flex items-center gap-2 px-6 py-3.5 text-[13px] font-display font-semibold tracking-wide uppercase border-b-2 border-r border-r-[var(--surface-border)] transition-all duration-200 ${activeMainTab === tab.key
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
          <div
            className="flex-grow min-h-0 bg-[var(--surface-base)] border-x border-b border-[var(--surface-border)] rounded-b-xl p-4 flex flex-col"
          >
            {activeMainTab === 'config' ? (
              <InstanceConfigTabs CONFIG_FILES={CONFIG_FILES} activeTabIndex={activeTabIndex} onTabChange={setActiveTabIndex} configContents={configContents} editorOnChangeHandlers={editorOnChangeHandlers} selectedPresetId={null} serverCfgLinterSource={qlCfgLinterSource} onExpandEditor={handleExpandEditor} onConfigFileUpload={handleFileUpload} />
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
              />
            ) : (
              <FactoryManager
                factories={factories}
                onFactoriesChange={setFactories}
                isNewInstance={true}
                preset="default"
              />
            )}
          </div>
        </div>
      </div>
      {(internalFormError || submissionError) && (
        <div className="alert-error flex-shrink-0 mb-6">
          <p className="text-sm font-medium">{internalFormError || submissionError}</p>
        </div>
      )}
      {/* Footer with Save/Load Preset on left, Cancel/Create Instance on right */}
      <div className="flex justify-between items-center flex-shrink-0 mt-4 pt-4 border-t border-[var(--surface-border)]">
        {/* Left side - Preset buttons + Esc hint */}
        <div className="flex items-center gap-3">
          <div className="flex gap-2">
            {loadedPreset ? (
              <>
                <button
                  type="button"
                  onClick={handleUpdatePresetClick}
                  disabled={!isPresetModified || isUpdatingPreset || loadedPreset.name === 'default'}
                  className="btn btn-secondary"
                >
                  <RefreshCw className={`w-4 h-4 mr-2 ${isUpdatingPreset ? 'animate-spin' : ''}`} />
                  {isUpdatingPreset ? 'Updating...' : `Update "${loadedPreset.name}"`}
                </button>
                <button type="button" onClick={() => setShowSavePresetModal(true)} className="btn btn-secondary">
                  <Save className="w-4 h-4 mr-2" />
                  Save As New
                </button>
              </>
            ) : (
              <button type="button" onClick={() => setShowSavePresetModal(true)} className="btn btn-secondary">
                <Save className="w-4 h-4 mr-2" />
                Save as Preset
              </button>
            )}
            <button type="button" onClick={() => setShowLoadPresetModal(true)} className="btn btn-secondary">
              <FolderOpen className="w-4 h-4 mr-2" />
              Load Preset
            </button>
          </div>
        </div>

        {/* Right side - Esc hint + Cancel/Submit */}
        <div className="flex items-center gap-3">
          <span className="font-mono text-xs text-[var(--text-muted)] tracking-wide hidden sm:inline-flex items-center gap-1.5">
            <kbd className="px-1.5 py-0.5 rounded bg-[var(--surface-elevated)] border border-[var(--surface-border)] text-[10px] font-bold">Esc</kbd>
            to close
          </span>
          <button type="button" onClick={handleCancel} className="btn btn-secondary">
            Cancel
          </button>
          <button
            type="submit"
            disabled={isLoadingSubmit || serverCfgHasLintErrors}
            className="btn btn-primary"
          >
            {isLoadingSubmit ? (
              <span className="flex items-center">
                <LoaderCircle size={18} className="animate-spin mr-2" />
                Creating...
              </span>
            ) : serverCfgHasLintErrors ? (
              'Fix server.cfg Errors'
            ) : (
              <span className="flex items-center">
                <CheckCircle size={16} className="mr-2" />
                Create Instance
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Modals */}
      <SavePresetModal
        isOpen={showSavePresetModal}
        onClose={() => setShowSavePresetModal(false)}
        onSave={handleSavePreset}
        isSaving={isSavingPreset}
        initialDescription={loadedPreset?.description || ''}
      />

      <LoadPresetModal
        isOpen={showLoadPresetModal}
        onClose={() => setShowLoadPresetModal(false)}
        onLoad={handleLoadPreset}
        presets={presets}
        isLoading={isLoadingPreset}
        onPresetDeleted={handlePresetDeleted}
      />

      <UpdatePresetModal
        isOpen={showUpdateConfirm}
        onClose={() => setShowUpdateConfirm(false)}
        onConfirm={handleConfirmUpdate}
        presetName={loadedPreset?.name || ''}
        initialDescription={loadedPreset?.description || ''}
        isUpdating={isUpdatingPreset}
        zIndexClass="z-50"
      />

      <FullScreenConfigEditorModal isOpen={isFullScreenEditorOpen} onClose={handleCloseFullScreenEditor} onSave={handleSaveFullScreenEditor} fileName={editingFileDetails.name} initialContent={editingFileDetails.content} language={editingFileDetails.language} linterSource={editingFileDetails.linterSource} />
    </form>
  );
}

export default AddInstanceForm;
