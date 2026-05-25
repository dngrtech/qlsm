import React, { useState, useEffect, useCallback, useRef } from 'react';
import { LoaderCircle, Save, FolderOpen, RefreshCw, Settings, Code2, LayoutGrid, CheckCircle } from 'lucide-react';
import { json, jsonParseLinter } from '@codemirror/lang-json';
import { python } from '@codemirror/lang-python';
import { getAvailablePortsForHost, getFactoryContent, getFactoryTree, getPresetById, savePreset, updatePreset } from '../../services/api';
import { getBinaryMeta, saveBinaryMeta } from '../../services/draftApi';
import InstanceBasicInfoForm from './InstanceBasicInfoForm';
import SavePresetModal from './SavePresetModal';
import LoadPresetModal from './LoadPresetModal';
import UpdatePresetModal from './UpdatePresetModal';
import FullScreenConfigEditorModal from '../config/FullScreenConfigEditorModal';
import {
  CONFIG_CAPS,
  FACTORY_CAPS,
  FileManager,
  PLUGIN_CAPS,
  useDraftAdapter,
  useStateAdapter,
} from '../fileManager';
import {
  qlcfgLanguage,
  createQlCfgLinter,
  stripManagedCvars
} from '../../codemirror-lang-qlcfg';
import { qlmappoolLanguage } from '../../codemirror-lang-qlmappool';
import { qlaccessLanguage } from '../../codemirror-lang-qlaccess';
import { qlworkshopLanguage } from '../../codemirror-lang-qlworkshop';
import { qlentLanguage, qlentLinter } from '../../codemirror-lang-qlent';
import {
  getLanRateUnsupportedMessage,
  isLanRateSupported,
} from '../../utils/lanRateCompatibility';

const CONFIG_FILES = ['server.cfg', 'mappool.txt', 'access.txt', 'workshop.txt'];
const NET_PORT_REGEX = /^(set\s+net_port\s+").*(".*)/m;
const HOSTNAME_REGEX = /^(set\s+sv_hostname\s+").*(".*)/m;

const CONFIG_LANGUAGE_MAP = {
  'server.cfg': qlcfgLanguage,
  'mappool.txt': qlmappoolLanguage,
  'access.txt': qlaccessLanguage,
  'workshop.txt': qlworkshopLanguage,
};
const FACTORY_LANGUAGE = json();
const FACTORY_LINTER_SOURCE = () => jsonParseLinter();
const PYTHON_LANGUAGE = python();

// Mapping from internal config keys to API keys
const CONFIG_TO_API_MAP = {
  'server.cfg': 'server_cfg',
  'mappool.txt': 'mappool_txt',
  'access.txt': 'access_txt',
  'workshop.txt': 'workshop_txt'
};

function createEmptyConfigMap() {
  return CONFIG_FILES.reduce((acc, fileName) => ({ ...acc, [fileName]: '' }), {});
}

function isAllowedConfigFile(fileName) {
  return CONFIG_CAPS.allowedExtensions.some(ext => fileName.toLowerCase().endsWith(ext));
}

function normalizeConfigMap(configs = {}) {
  const normalized = {};
  for (const [fileName, content] of Object.entries(configs || {})) {
    if (isAllowedConfigFile(fileName)) {
      normalized[fileName] = content ?? '';
    }
  }
  for (const fileName of CONFIG_FILES) {
    if (normalized[fileName] === undefined) {
      normalized[fileName] = configs?.[fileName] ?? '';
    }
  }
  return normalized;
}

function extractPresetConfigs(presetData) {
  const legacyConfigs = CONFIG_FILES.reduce((acc, fileName) => {
    acc[fileName] = presetData[CONFIG_TO_API_MAP[fileName]] || '';
    return acc;
  }, {});
  const configs = normalizeConfigMap(presetData.configs || legacyConfigs);
  configs['server.cfg'] = stripManagedCvars(configs['server.cfg'] || '');
  return configs;
}

function getConfigLanguage(fileName) {
  if (fileName?.toLowerCase().endsWith('.cfg')) return qlcfgLanguage;
  if (fileName?.toLowerCase().endsWith('.ent')) return qlentLanguage;
  return CONFIG_LANGUAGE_MAP[fileName] || undefined;
}

function getPluginLanguage(fileName) {
  return fileName?.toLowerCase().endsWith('.py') ? PYTHON_LANGUAGE : null;
}

function getFactoryLanguage(fileName) {
  return fileName?.toLowerCase().endsWith('.factories') ? FACTORY_LANGUAGE : null;
}

function getFactoryLinterSource(fileName) {
  return fileName?.toLowerCase().endsWith('.factories') ? FACTORY_LINTER_SOURCE : null;
}

function areSetsEqual(left, right) {
  if (left.size !== right.size) return false;
  for (const value of left) {
    if (!right.has(value)) return false;
  }
  return true;
}

function getSubmitPluginNames(plugins) {
  return Array.from(plugins)
    .filter(p => p.endsWith('.py') && !p.endsWith('__init__.py'))
    .map(p => p.replace(/\.py$/, '').replace(/^.*\//, ''));
}

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
  const [configContents, setConfigContents] = useState(() => normalizeConfigMap(initialData.defaultConfigContents || createEmptyConfigMap()));
  const [availablePorts, setAvailablePorts] = useState([]);
  const [loadingPorts, setLoadingPorts] = useState(false);
  const [internalFormError, setInternalFormError] = useState(null);
  const [serverCfgHasLintErrors, setServerCfgHasLintErrors] = useState(false);
  const [isFullScreenEditorOpen, setIsFullScreenEditorOpen] = useState(false);
  const [editingFileDetails, setEditingFileDetails] = useState({ name: '', path: '', content: '', language: undefined, linterSource: null, kind: 'config' });

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
  const [checkedPlugins, setCheckedPlugins] = useState(new Set(initialData.defaultCheckedPlugins || []));
  const pluginsManagerRef = useRef(null);
  const [draftPreset, setDraftPreset] = useState('default');
  const [factoryServerTree, setFactoryServerTree] = useState(initialData.defaultFactoryTree || []);

  const isUpdatingFromServerCfg = useRef(false);
  const prevHostnameRef = useRef(hostname);
  const hostnameRef = useRef(hostname);
  const isUpdatingPortFromServerCfg = useRef(false);
  const prevPortRef = useRef(port);
  const portRef = useRef(port);
  const availablePortsRef = useRef(availablePorts);
  const portFetchAbortRef = useRef(null);
  const configContentsRef = useRef(normalizeConfigMap(initialData.defaultConfigContents || createEmptyConfigMap()));

  const initialNameRef = useRef('');
  const initialSelectedHostIdRef = useRef('');
  const initialPortRef = useRef('');
  const initialHostnameRef = useRef('');
  const initialLanRateEnabledRef = useRef(false);
  const initialConfigContentsRef = useRef(normalizeConfigMap(initialData.defaultConfigContents || createEmptyConfigMap()));
  const initialCheckedPluginsRef = useRef(new Set(initialData.defaultCheckedPlugins || []));
  const loadedPresetConfigRef = useRef(null); // Stores config contents when preset is loaded, for modification detection
  const loadedPresetCheckedPluginsRef = useRef(new Set(initialData.defaultCheckedPlugins || []));

  const readFactoryServerContent = useCallback(async (path) => {
    const data = await getFactoryContent(path, { preset: draftPreset || 'default' });
    return data.content || '';
  }, [draftPreset]);

  const handleConfigAdapterFilesChange = useCallback((nextFiles) => {
    const normalized = normalizeConfigMap(nextFiles);
    if (JSON.stringify(configContentsRef.current) !== JSON.stringify(normalized)) {
      configContentsRef.current = normalized;
      setConfigContents(normalized);
    }

    const serverCfg = normalized['server.cfg'] || '';
    const hostnameMatch = serverCfg.match(/^set\s+sv_hostname\s+"([^"]*)"/m);
    if (hostnameMatch && hostnameMatch[1] !== hostnameRef.current) {
      isUpdatingFromServerCfg.current = true;
      setHostname(hostnameMatch[1]);
      setTimeout(() => { isUpdatingFromServerCfg.current = false; }, 0);
    }

    const portMatch = serverCfg.match(/^set\s+net_port\s+"(\d+)"/m);
    if (portMatch && portMatch[1] !== portRef.current) {
      const portVal = portMatch[1];
      if (availablePortsRef.current.includes(parseInt(portVal, 10))) {
        isUpdatingPortFromServerCfg.current = true;
        setPort(portVal);
        setTimeout(() => { isUpdatingPortFromServerCfg.current = false; }, 0);
      }
    }
  }, []);

  const configsAdapter = useStateAdapter({
    initialFiles: configContents,
    initialFolders: [],
    allowedExtensions: CONFIG_CAPS.allowedExtensions,
    protectedFiles: CONFIG_CAPS.protectedFiles,
    reservedFolderNames: CONFIG_CAPS.reservedFolderNames,
    onFilesChange: handleConfigAdapterFilesChange,
  });

  const pluginsAdapter = useDraftAdapter({
    source: 'preset',
    preset: draftPreset || 'default',
    active: true,
  });

  const factoriesAdapter = useStateAdapter({
    initialFiles: initialData.defaultFactories || {},
    serverTree: factoryServerTree,
    readServerContent: readFactoryServerContent,
    allowedExtensions: FACTORY_CAPS.allowedExtensions,
    protectedFiles: FACTORY_CAPS.protectedFiles,
  });
  const pluginDraftId = pluginsAdapter.draftId;
  const pluginConsume = pluginsAdapter.consume;
  const pluginDiscard = pluginsAdapter.discard;
  const configsHaveChanges = configsAdapter.hasChanges;
  const resetConfigs = configsAdapter.reset;
  const serializeConfigs = configsAdapter.serialize;
  const writeConfigContent = configsAdapter.writeContent;
  const checkedFactories = factoriesAdapter.checkedFiles;
  const factoriesHaveChanges = factoriesAdapter.hasChanges;
  const resetFactories = factoriesAdapter.reset;
  const serializeFactories = factoriesAdapter.serialize;
  const setFactoryChecked = factoriesAdapter.setChecked;
  const pluginsHaveChanges = pluginsAdapter.hasChanges;

  const syncConfigState = useCallback((nextConfigs, { resetAdapter = false, markInitial = false } = {}) => {
    const normalized = normalizeConfigMap(nextConfigs);
    configContentsRef.current = normalized;
    setConfigContents(normalized);
    if (resetAdapter) {
      resetConfigs(normalized);
    }
    if (markInitial) {
      initialConfigContentsRef.current = normalized;
    }
    return normalized;
  }, [resetConfigs]);

  const syncConfigFile = useCallback((fileName, content, { markInitial = false } = {}) => {
    const nextConfigs = {
      ...configContentsRef.current,
      [fileName]: content ?? '',
    };
    configContentsRef.current = nextConfigs;
    setConfigContents(nextConfigs);
    writeConfigContent(fileName, content ?? '').catch((err) => {
      setInternalFormError(err.message || `Failed to update ${fileName}.`);
    });
    if (markInitial) {
      initialConfigContentsRef.current = {
        ...initialConfigContentsRef.current,
        [fileName]: content ?? '',
      };
    }
  }, [writeConfigContent]);

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

          const currentServerCfg = configContentsRef.current['server.cfg'] || '';
          let newCfg = currentServerCfg;
          if (NET_PORT_REGEX.test(currentServerCfg)) {
            newCfg = currentServerCfg.replace(NET_PORT_REGEX, `$1${lowestPort}$2`);
          } else if (currentServerCfg.trim() !== '') {
            newCfg = `${currentServerCfg}\nset net_port "${lowestPort}"`;
          } else {
            newCfg = `set net_port "${lowestPort}"`;
          }

          syncConfigState(
            { ...configContentsRef.current, 'server.cfg': newCfg },
            { resetAdapter: true, markInitial: true },
          );
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
        const currentServerCfg = configContentsRef.current['server.cfg'] || '';
        syncConfigFile('server.cfg', currentServerCfg.replace(NET_PORT_REGEX, `// $1${currentPortVal}$2 (Port removed)`));
      }
    }
  }, [syncConfigFile, syncConfigState]);

  useEffect(() => {
    const currentDefaultConfigs = normalizeConfigMap(initialData.defaultConfigContents || createEmptyConfigMap());
    syncConfigState(currentDefaultConfigs, { resetAdapter: true, markInitial: true });

    let initialHostnameFromCfg = '';
    const defaultConfigServerCfg = currentDefaultConfigs['server.cfg'];
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
    setLoadedPreset(null);
    loadedPresetConfigRef.current = null;
    setIsPresetModified(false);

    const defaultCheckedPlugins = new Set(initialData.defaultCheckedPlugins || []);
    setCheckedPlugins(defaultCheckedPlugins);
    initialCheckedPluginsRef.current = defaultCheckedPlugins;
    loadedPresetCheckedPluginsRef.current = defaultCheckedPlugins;
    setDraftPreset('default');
    resetFactories(initialData.defaultFactories || {});
    setFactoryServerTree(initialData.defaultFactoryTree || []);

    if (startHostId) {
      handleHostChange(startHostId, true);
    } else {
      setSelectedHostId('');
    }

    return () => { portFetchAbortRef.current?.abort(); };
  }, [
    handleHostChange,
    initialData.defaultCheckedPlugins,
    initialData.defaultConfigContents,
    initialData.defaultFactories,
    initialData.defaultFactoryTree,
    initialHostId,
    resetFactories,
    syncConfigState,
  ]);

  // Sync presets state when initialData.presets changes
  useEffect(() => {
    setPresets(initialData.presets || []);
  }, [initialData.presets]);

  useEffect(() => {
    configContentsRef.current = configContents;
  }, [configContents]);

  useEffect(() => { hostnameRef.current = hostname; }, [hostname]);
  useEffect(() => { portRef.current = port; }, [port]);
  useEffect(() => { availablePortsRef.current = availablePorts; }, [availablePorts]);

  useEffect(() => {
    let cancelled = false;
    getFactoryTree({ preset: draftPreset || 'default' })
      .then((tree) => {
        if (!cancelled) setFactoryServerTree(tree || []);
      })
      .catch((err) => {
        if (!cancelled) {
          setInternalFormError(err.error?.message || err.message || 'Failed to load factory files.');
        }
      });
    return () => { cancelled = true; };
  }, [draftPreset]);

  useEffect(() => {
    if (initialData.defaultFactories) {
      resetFactories(initialData.defaultFactories);
    }
  }, [initialData.defaultFactories, resetFactories]);

  useEffect(() => {
    const checkedPluginsChanged = !areSetsEqual(checkedPlugins, initialCheckedPluginsRef.current);
    const isDirty =
      name !== initialNameRef.current ||
      selectedHostId !== initialSelectedHostIdRef.current ||
      port !== initialPortRef.current ||
      hostname !== initialHostnameRef.current ||
      lanRateEnabled !== initialLanRateEnabledRef.current ||
      JSON.stringify(configContents) !== JSON.stringify(initialConfigContentsRef.current) ||
      configsHaveChanges ||
      factoriesHaveChanges ||
      pluginsHaveChanges ||
      checkedPluginsChanged;
    if (onDirtyStateChange) onDirtyStateChange(isDirty);
  }, [
    checkedPlugins,
    configContents,
    configsHaveChanges,
    factoriesHaveChanges,
    hostname,
    lanRateEnabled,
    name,
    onDirtyStateChange,
    pluginsHaveChanges,
    port,
    selectedHostId,
  ]);

  // Track if loaded preset has been modified
  useEffect(() => {
    if (loadedPreset && loadedPresetConfigRef.current) {
      const modified =
        JSON.stringify(configContents) !== JSON.stringify(loadedPresetConfigRef.current) ||
        configsHaveChanges ||
        factoriesHaveChanges ||
        pluginsHaveChanges ||
        !areSetsEqual(checkedPlugins, loadedPresetCheckedPluginsRef.current);
      setIsPresetModified(modified);
    }
  }, [
    checkedPlugins,
    configContents,
    configsHaveChanges,
    factoriesHaveChanges,
    loadedPreset,
    pluginsHaveChanges,
  ]);

  useEffect(() => {
    if (hostname !== '' && hostname !== prevHostnameRef.current && !isUpdatingFromServerCfg.current) {
      const currentServerCfg = configContentsRef.current['server.cfg'] || '';
      const nextServerCfg = currentServerCfg
        ? (HOSTNAME_REGEX.test(currentServerCfg) ? currentServerCfg.replace(HOSTNAME_REGEX, `$1${hostname}$2`) : `${currentServerCfg}\nset sv_hostname "${hostname}"`)
        : `set sv_hostname "${hostname}"`;
      if (nextServerCfg !== currentServerCfg) {
        syncConfigFile('server.cfg', nextServerCfg);
      }
    }
    prevHostnameRef.current = hostname;
  }, [hostname, syncConfigFile]);

  useEffect(() => {
    if (port !== '' && port !== prevPortRef.current && !isUpdatingPortFromServerCfg.current) {
      // Skip if server.cfg already reflects this port (e.g. set during auto-populate or config edit)
      const currentCfg = configContentsRef.current['server.cfg'] || '';
      const existingMatch = currentCfg.match(/^set\s+net_port\s+"(\d+)"/m);
      if (!(existingMatch && existingMatch[1] === port)) {
        const nextServerCfg = NET_PORT_REGEX.test(currentCfg)
          ? currentCfg.replace(NET_PORT_REGEX, `$1${port}$2`)
          : `${currentCfg}\nset net_port "${port}"`;
        syncConfigFile('server.cfg', nextServerCfg);
      }
    }
    prevPortRef.current = port;
  }, [port, syncConfigFile]);

  // Handle loading a preset
  const handleLoadPreset = useCallback(async (presetId) => {
    setIsLoadingPreset(true);
    try {
      setInternalFormError(null);
      const presetData = await getPresetById(presetId);
      const newConfigs = extractPresetConfigs(presetData);

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

      const newFolders = Array.isArray(presetData.config_folders) ? presetData.config_folders : [];
      syncConfigState(newConfigs, { markInitial: true });
      resetConfigs(newConfigs, newFolders);
      initialConfigContentsRef.current = newConfigs;

      // Track which preset was loaded (for update feature)
      setLoadedPreset({ id: presetId, name: presetData.name, description: presetData.description || '', is_builtin: !!presetData.is_builtin });
      // Reseed draft workspace with the loaded preset's scripts
      setDraftPreset(presetData.name);
      loadedPresetConfigRef.current = newConfigs;
      // checked_factories: null = legacy preset (use all factory files); [] or [...] = explicit selection
      const factoriesToLoad = presetData.checked_factories != null
        ? Object.fromEntries(
            presetData.checked_factories
              .filter(f => presetData.factories?.[f] !== undefined)
              .map(f => [f, presetData.factories[f]])
          )
        : (presetData.factories || {});
      resetFactories(factoriesToLoad);
      setIsPresetModified(false);

      initialHostnameRef.current = newInitialHostname;
      initialPortRef.current = newInitialPort;

      // Restore checked plugins state saved with the preset.
      // null means the preset pre-dates this feature — keep current defaults.
      let nextCheckedBaseline = new Set(checkedPlugins);
      if (presetData.checked_plugins != null) {
        nextCheckedBaseline = new Set(presetData.checked_plugins);
        setCheckedPlugins(nextCheckedBaseline);
      }
      loadedPresetCheckedPluginsRef.current = nextCheckedBaseline;
      initialCheckedPluginsRef.current = nextCheckedBaseline;

      setShowLoadPresetModal(false);
    } catch (err) {
      setInternalFormError(err.error?.message || err.message || `Failed to load preset.`);
    } finally {
      setIsLoadingPreset(false);
    }
  }, [checkedPlugins, resetConfigs, resetFactories, syncConfigState]);


  // Handle saving current config as a preset
  const handleSavePreset = useCallback(async ({ name, description }) => {
    setIsSavingPreset(true);
    try {
      // Map internal config keys to API keys
      const { files: serializedFactories } = serializeFactories();
      const { files: cfgFiles, folders: cfgFolders } = serializeConfigs();
      const presetData = {
        name,
        description: description || null,
        configs: cfgFiles,
        config_folders: cfgFolders,
        factories: serializedFactories,
        checked_factories: Object.keys(serializedFactories),
      };

      if (pluginsManagerRef.current?.flushEdits) {
        await pluginsManagerRef.current.flushEdits();
      }

      if (pluginDraftId) {
        presetData.draft_id = pluginDraftId;
      }

      if (name !== draftPreset) {
        presetData.binary_meta_source = {
          context_type: 'preset',
          context_key: draftPreset,
        };
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
  }, [checkedPlugins, draftPreset, pluginDraftId, serializeConfigs, serializeFactories]);

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
      const { files: serializedFactoriesUpdate } = serializeFactories();
      const { files: cfgFiles, folders: cfgFolders } = serializeConfigs();
      const presetData = {
        description: description,
        configs: cfgFiles,
        config_folders: cfgFolders,
        factories: serializedFactoriesUpdate,
        checked_factories: Object.keys(serializedFactoriesUpdate),
      };

      if (pluginsManagerRef.current?.flushEdits) {
        await pluginsManagerRef.current.flushEdits();
      }

      if (pluginDraftId) {
        presetData.draft_id = pluginDraftId;
      }

      // Persist the current checked plugins state
      presetData.checked_plugins = Array.from(checkedPlugins);

      await updatePreset(loadedPreset.id, presetData);

      // Reset modified state after successful save and update loaded preset description
      loadedPresetConfigRef.current = serializeConfigs().files;
      loadedPresetCheckedPluginsRef.current = new Set(checkedPlugins);
      setLoadedPreset(prev => ({ ...prev, description: description || '' }));
      setIsPresetModified(false);
      setInternalFormError(null);
    } catch (err) {
      setInternalFormError(err.error?.message || err.message || 'Failed to update preset.');
    } finally {
      setIsUpdatingPreset(false);
    }
  }, [checkedPlugins, loadedPreset, pluginDraftId, serializeConfigs, serializeFactories]);

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

  const handleConfigContentUpdate = useCallback((fileName, newContent) => {
    syncConfigFile(fileName, newContent);
    if (fileName === 'server.cfg') {
      const hostnameMatch = newContent.match(/^set\s+sv_hostname\s+"([^"]*)"/m);
      if (hostnameMatch && hostnameMatch[1] !== hostnameRef.current) { isUpdatingFromServerCfg.current = true; setHostname(hostnameMatch[1]); setTimeout(() => isUpdatingFromServerCfg.current = false, 0); }
      const portMatch = newContent.match(/^set\s+net_port\s+"(\d+)"/m);
      if (portMatch && portMatch[1] !== portRef.current) { const portVal = portMatch[1]; if (availablePortsRef.current.includes(parseInt(portVal, 10))) { isUpdatingPortFromServerCfg.current = true; setPort(portVal); setTimeout(() => isUpdatingPortFromServerCfg.current = false, 0); } }
    }
  }, [syncConfigFile]);

  const handleInternalServerCfgLint = useCallback((hasErrors) => { setServerCfgHasLintErrors(hasErrors); if (onServerCfgLintStatusChange) onServerCfgLintStatusChange(hasErrors); }, [onServerCfgLintStatusChange]);
  const qlCfgLinterSource = useCallback(() => (createQlCfgLinter(availablePorts, handleInternalServerCfgLint)), [availablePorts, handleInternalServerCfgLint]);
  const getLinterSourceForFile = useCallback(
    (fileName) => {
      const lowerName = fileName?.toLowerCase() || '';
      if (lowerName.endsWith('.cfg')) return qlCfgLinterSource;
      if (lowerName.endsWith('.ent')) return qlentLinter;
      return null;
    },
    [qlCfgLinterSource],
  );
  const handleExpandEditor = useCallback((selectedFile, content = '') => {
    const fileName = typeof selectedFile === 'string'
      ? selectedFile
      : (selectedFile?.path || selectedFile?.name || '');
    setEditingFileDetails({
      name: fileName,
      path: fileName,
      content: content || serializeConfigs().files[fileName] || '',
      language: getConfigLanguage(fileName),
      linterSource: getLinterSourceForFile(fileName),
      kind: 'config',
    });
    setIsFullScreenEditorOpen(true);
  }, [getLinterSourceForFile, serializeConfigs]);
  const handleExpandPluginEditor = useCallback((selectedFile, content = '') => {
    const fileName = selectedFile?.name || '';
    const filePath = selectedFile?.path || fileName;
    setEditingFileDetails({
      name: fileName,
      path: filePath,
      content,
      language: getPluginLanguage(fileName),
      linterSource: null,
      kind: 'plugin',
    });
    setIsFullScreenEditorOpen(true);
  }, []);
  const handleExpandFactoryEditor = useCallback((selectedFile, content = '') => {
    const fileName = selectedFile?.name || '';
    const filePath = selectedFile?.path || fileName;
    setEditingFileDetails({
      name: fileName,
      path: filePath,
      content,
      language: getFactoryLanguage(fileName),
      linterSource: getFactoryLinterSource(fileName),
      kind: 'factory',
    });
    setIsFullScreenEditorOpen(true);
  }, []);
  const handleCloseFullScreenEditor = useCallback(() => { setIsFullScreenEditorOpen(false); }, []);
  const handleSaveFullScreenEditor = useCallback((newContent) => {
    if (editingFileDetails.kind === 'plugin') {
      pluginsManagerRef.current?.updateContent(editingFileDetails.path || editingFileDetails.name, newContent);
    } else if (editingFileDetails.kind === 'factory') {
      factoriesAdapter.writeContent(editingFileDetails.path || editingFileDetails.name, newContent);
    } else {
      handleConfigContentUpdate(editingFileDetails.name, newContent);
    }
    setIsFullScreenEditorOpen(false);
  }, [
    editingFileDetails.kind,
    editingFileDetails.name,
    editingFileDetails.path,
    factoriesAdapter,
    handleConfigContentUpdate,
  ]);
  const effectiveHostId = selectedHostId || (initialHostId ? String(initialHostId) : '');
  const selectedHost = (initialData.hosts || []).find((host) => String(host.id) === String(effectiveHostId));
  const selectedHostOsType = selectedHost?.os_type ?? null;
  const hasSelectedHost = Boolean(selectedHost);
  const selectedHostShape = { os_type: selectedHostOsType, lan_rate_uses_hook: selectedHost?.lan_rate_uses_hook ?? false };
  const lanRateSupported = !hasSelectedHost || isLanRateSupported(selectedHostShape);
  const lanRateUnavailableReason = hasSelectedHost && !lanRateSupported
    ? getLanRateUnsupportedMessage(selectedHostShape)
    : null;

  useEffect(() => {
    if (!lanRateSupported && lanRateEnabled) {
      setLanRateEnabled(false);
    }
  }, [lanRateEnabled, lanRateSupported]);

  const localHandleSubmit = async (e) => {
    e.preventDefault();
    if (serverCfgHasLintErrors) { setInternalFormError("Please fix errors in server.cfg before submitting."); return; }
    setInternalFormError(null);

    if (pluginsManagerRef.current?.flushEdits) {
      await pluginsManagerRef.current.flushEdits();
    }

    const checkedPluginNames = getSubmitPluginNames(checkedPlugins);
    const submitData = {
      name,
      host_id: parseInt(selectedHostId, 10),
      port: parseInt(port, 10),
      hostname,
      lan_rate_enabled: lanRateEnabled,
      ...(() => { const { files, folders } = serializeConfigs(); return { configs: files, config_folders: folders }; })(),
      factories: serializeFactories().files,
      checked_plugins: checkedPluginNames,
      qlx_plugins: checkedPluginNames.join(', '),
    };

    if (pluginDraftId) {
      submitData.draft_id = pluginDraftId;
    }

    await onSubmit(submitData, { consumeDraft: pluginConsume });
  };

  // Discard draft workspace on cancel/close
  const handleCancel = useCallback(() => {
    pluginDiscard();
    onCancel();
  }, [onCancel, pluginDiscard]);

  // Configure plugins based on checkboxes
  const togglePluginSelection = useCallback((filename, checked = undefined) => {
    setCheckedPlugins(prev => {
      const newSet = new Set(prev);
      const shouldCheck = checked ?? !newSet.has(filename);
      if (shouldCheck) {
        newSet.add(filename);
      } else {
        newSet.delete(filename);
      }
      return newSet;
    });
  }, []);

  const handleGetBinaryMeta = useCallback(
    (path) => getBinaryMeta(pluginDraftId, path, 'preset', draftPreset),
    [draftPreset, pluginDraftId],
  );

  const handleSaveBinaryMeta = useCallback(
    (path, description) => (
      saveBinaryMeta(pluginDraftId, path, description, 'preset', draftPreset)
    ),
    [draftPreset, pluginDraftId],
  );

  return (
    <form onSubmit={localHandleSubmit} className="flex flex-col flex-grow min-h-0 pt-4">
      <div className="flex-shrink-0 mb-6">
        <InstanceBasicInfoForm name={name} onNameChange={(e) => setName(e.target.value)} selectedHostId={selectedHostId} onHostChange={handleHostChange} hosts={initialData.hosts || []} port={port} onPortChange={setPort} availablePorts={availablePorts} loadingPorts={loadingPorts} hostname={hostname} onHostnameChange={(e) => setHostname(e.target.value)} lanRateEnabled={lanRateEnabled} onLanRateChange={setLanRateEnabled} lanRateDisabled={!lanRateSupported} lanRateUnavailableReason={lanRateUnavailableReason} />
      </div>
      <div className="flex flex-col flex-grow min-h-0 mb-2">
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
          <div className="flex flex-shrink-0 border border-[var(--surface-border)] bg-[var(--surface-elevated)] rounded-t-xl overflow-hidden">
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
            <div className={activeMainTab === 'config' ? 'flex-1 min-h-0' : 'hidden'}>
              <FileManager
                adapter={configsAdapter}
                capabilities={CONFIG_CAPS}
                defaultSelectedPath="server.cfg"
                onExpandEditor={handleExpandEditor}
                getLanguageForFile={getConfigLanguage}
                getLinterSourceForFile={getLinterSourceForFile}
              />
            </div>
            <div className={activeMainTab === 'scripts' ? 'flex-1 min-h-0' : 'hidden'}>
              <FileManager
                ref={pluginsManagerRef}
                adapter={pluginsAdapter}
                capabilities={PLUGIN_CAPS}
                checkable
                checkedFiles={checkedPlugins}
                onCheck={togglePluginSelection}
                onExpandEditor={handleExpandPluginEditor}
                getLanguageForFile={getPluginLanguage}
                getBinaryMeta={handleGetBinaryMeta}
                saveBinaryMeta={handleSaveBinaryMeta}
                binaryContext={{
                  contextType: 'preset',
                  contextKey: draftPreset || 'default',
                }}
              />
            </div>
            <div className={activeMainTab === 'factories' ? 'flex-1 min-h-0' : 'hidden'}>
              <FileManager
                adapter={factoriesAdapter}
                capabilities={FACTORY_CAPS}
                checkable
                checkedFiles={checkedFactories}
                onCheck={setFactoryChecked}
                onExpandEditor={handleExpandFactoryEditor}
                getLanguageForFile={getFactoryLanguage}
                getLinterSourceForFile={getFactoryLinterSource}
              />
            </div>
          </div>
        </div>
      </div>
      {(internalFormError || submissionError) && (
        <div className="alert-error flex-shrink-0 mb-6">
          <p className="text-sm font-medium">{internalFormError || submissionError}</p>
        </div>
      )}
      {/* Footer with Save/Load Preset on left, Cancel/Create Instance on right */}
      <div className="flex justify-between items-center flex-shrink-0 mt-4">
        {/* Left side - Preset buttons + Esc hint */}
        <div className="flex items-center gap-3">
          <div className="flex gap-2">
            {loadedPreset ? (
              <>
                {!loadedPreset.is_builtin && (
                  <button
                    type="button"
                    onClick={handleUpdatePresetClick}
                    disabled={!isPresetModified || isUpdatingPreset}
                    className="btn btn-secondary"
                  >
                    <RefreshCw className={`w-4 h-4 mr-2 ${isUpdatingPreset ? 'animate-spin' : ''}`} />
                    {isUpdatingPreset ? 'Updating...' : `Update "${loadedPreset.name}"`}
                  </button>
                )}
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
