import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { X, LoaderCircle, Zap, AlertTriangle, Settings, Code2, LayoutGrid, Save, FolderOpen, RotateCw, Webhook } from 'lucide-react';
import { json, jsonParseLinter } from '@codemirror/lang-json';
import { python } from '@codemirror/lang-python';
import { getInstanceConfig, updateInstanceConfig, getInstanceById, getPresets, getPresetById, createPreset, updatePreset, getFactoryTree, getFactoryContent, fetchInstanceHooks } from '../../services/api';
import { getBinaryMeta, saveBinaryMeta } from '../../services/draftApi';
import ExpandedEditorModal from '../ExpandedEditorModal';
import ConfirmationModal from '../ConfirmationModal';
import PresetManagerModal from '../presetManager/PresetManagerModal';
import { FileManager, CONFIG_CAPS, PLUGIN_CAPS, FACTORY_CAPS, useStateAdapter, useDraftAdapter } from '../fileManager';
import { useNotification } from '../NotificationProvider';
import InfoTooltip from '../common/InfoTooltip';
import { qlcfgLanguage, createQlCfgLinter, stripManagedCvars } from '../../codemirror-lang-qlcfg';
import { qlmappoolLanguage } from '../../codemirror-lang-qlmappool';
import { qlaccessLanguage } from '../../codemirror-lang-qlaccess';
import { qlworkshopLanguage } from '../../codemirror-lang-qlworkshop';
import { qlentLanguage, qlentLinter } from '../../codemirror-lang-qlent';
import HooksTab from './HooksTab';
import {
  canEnableLanRate,
  getLanRateUnsupportedMessage,
} from '../../utils/lanRateCompatibility';

const CONFIG_FILES_ORDER = ['server.cfg', 'mappool.txt', 'access.txt', 'workshop.txt'];

const LANGUAGE_MAP = {
  'server.cfg': qlcfgLanguage,
  'mappool.txt': qlmappoolLanguage,
  'access.txt': qlaccessLanguage,
  'workshop.txt': qlworkshopLanguage,
};
const getLanguageForFile = (fileName) => {
  if (fileName?.toLowerCase().endsWith('.cfg')) return qlcfgLanguage;
  if (fileName?.toLowerCase().endsWith('.ent')) return qlentLanguage;
  return LANGUAGE_MAP[fileName] || null;
};
const FACTORY_LANGUAGE = json();
const FACTORY_LINTER_SOURCE = () => jsonParseLinter();
const PYTHON_LANGUAGE = python();
const getPluginLanguage = (fileName) => (
  fileName?.toLowerCase().endsWith('.py') ? PYTHON_LANGUAGE : null
);
const getFactoryLanguage = (fileName) => (
  fileName?.toLowerCase().endsWith('.factories') ? FACTORY_LANGUAGE : null
);
const getFactoryLinterSource = (fileName) => (
  fileName?.toLowerCase().endsWith('.factories') ? FACTORY_LINTER_SOURCE : null
);
const getServerHostname = (serverCfg = '') => serverCfg.match(/set sv_hostname "([^"]*)"/)?.[1] || '';
const enabledHookFilenames = (hooksData) => (hooksData.available || [])
  .filter((hook) => hook.enabled)
  .sort((a, b) => a.order - b.order)
  .map((hook) => hook.filename);
const setsEqual = (a, b) => a.size === b.size && [...a].every(value => b.has(value));

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
  initialTab = 'config',
}) {
  const [currentInstanceName, setCurrentInstanceName] = useState(initialInstanceName || '');
  const [originalInstanceName, setOriginalInstanceName] = useState(initialInstanceName || '');
  const configsAdapter = useStateAdapter({
    initialFiles: CONFIG_FILES_ORDER.reduce((acc, fileName) => {
      acc[fileName] = '';
      return acc;
    }, {}),
    initialFolders: [],
    allowedExtensions: CONFIG_CAPS.allowedExtensions,
    protectedFiles: CONFIG_CAPS.protectedFiles,
    reservedFolderNames: CONFIG_CAPS.reservedFolderNames,
  });
  const [presets, setPresets] = useState([]);
  const [selectedPresetId, setSelectedPresetId] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadingPresets, setLoadingPresets] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [presetError, setPresetError] = useState(null);
  const [saveError, setSaveError] = useState(null);

  // LAN Rate state
  const [lanRateEnabled, setLanRateEnabled] = useState(false);
  const [originalLanRateEnabled, setOriginalLanRateEnabled] = useState(false);
  const [hostOsType, setHostOsType] = useState(null);
  const [hostLanRateUsesHook, setHostLanRateUsesHook] = useState(false);

  // Restart on Save state
  const [restartAfterSave, setRestartAfterSave] = useState(true);

  // Unsaved changes state
  const [isDirty, setIsDirty] = useState(false);
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);

  // New state for synced hostname
  const isUpdatingFromServerCfg = React.useRef(false);
  const [serverHostname, setServerHostname] = useState('');
  const [originalServerHostname, setOriginalServerHostname] = useState('');

  // State for ExpandedEditorModal
  const [isExpandedEditorOpen, setIsExpandedEditorOpen] = useState(false);
  const [expandedFileName, setExpandedFileName] = useState('');
  const [expandedFileContent, setExpandedFileContent] = useState('');
  const [expandedFileLanguage, setExpandedFileLanguage] = useState(null);
  const [expandedFileLinterSource, setExpandedFileLinterSource] = useState(null);
  const [expandedPluginPath, setExpandedPluginPath] = useState(null);
  const [expandedFactoryPath, setExpandedFactoryPath] = useState(null);

  // State for preset manager
  const [isPresetManagerOpen, setIsPresetManagerOpen] = useState(false);
  const [presetManagerTab, setPresetManagerTab] = useState('load');
  const [isSavingPreset, setIsSavingPreset] = useState(false);
  const [savedPresetForDownload, setSavedPresetForDownload] = useState(null);

  // Scripts tab state
  const [activeMainTab, setActiveMainTab] = useState(initialTab); // 'config' | 'scripts' | 'factories' | 'hooks'
  const [checkedPlugins, setCheckedPlugins] = useState(new Set());
  const [initialCheckedPlugins, setInitialCheckedPlugins] = useState(new Set());
  const [scriptHostName, setScriptHostName] = useState(null);
  const [draftPreset, setDraftPreset] = useState(null); // null = seed from instance; string = seed from preset
  const [rawQlxPlugins, setRawQlxPlugins] = useState([]); // bare plugin names from instance
  const pluginFileManagerRef = useRef(null);
  const pluginsSyncedRef = useRef(false);
  const hookLoadSeqRef = useRef(0);

  // Hooks tab state
  const [hookAvailable, setHookAvailable] = useState([]);
  const [hookMissing, setHookMissing] = useState([]);
  const [hookSystem, setHookSystem] = useState([]);
  const [hookEnabledOrder, setHookEnabledOrder] = useState([]);
  const [initialHookEnabledOrder, setInitialHookEnabledOrder] = useState([]);
  const [hookDiskChanged, setHookDiskChanged] = useState(false);
  const [hooksLoaded, setHooksLoaded] = useState(false);
  const [instanceStatus, setInstanceStatus] = useState(null);

  // Factories tab state
  const [factoryServerTree, setFactoryServerTree] = useState([]);

  // When a preset is loaded, read factory content from the preset directory;
  // otherwise read from the instance's deployed factories directory.
  const readFactoryContent = useCallback(async (path) => {
    const params = draftPreset
      ? { preset: draftPreset }
      : { host: scriptHostName, instanceId };
    const data = await getFactoryContent(path, params);
    return data.content || '';
  }, [draftPreset, scriptHostName, instanceId]);

  const factoriesAdapter = useStateAdapter({
    initialFiles: {},
    serverTree: factoryServerTree,
    readServerContent: readFactoryContent,
    allowedExtensions: FACTORY_CAPS.allowedExtensions,
    protectedFiles: FACTORY_CAPS.protectedFiles,
  });

  const { showSuccess, showError } = useNotification(); // Get notification functions

  const pluginsAdapter = useDraftAdapter({
    source: draftPreset ? 'preset' : 'instance',
    preset: draftPreset || undefined,
    host: draftPreset ? undefined : scriptHostName,
    instanceId: draftPreset ? undefined : instanceId,
    active: isOpen && (draftPreset != null || scriptHostName != null),
  });
  const {
    hasChanges: configsHaveChanges,
    readContent: readConfigContent,
    reset: resetConfigs,
    serialize: serializeConfigs,
    writeContent: writeConfigContent,
  } = configsAdapter;
  const {
    checkedFiles: checkedFactories,
    hasChanges: factoriesHaveChanges,
    reset: resetFactories,
    serialize: serializeFactories,
    setChecked: setFactoryChecked,
  } = factoriesAdapter;
  const {
    consume: consumePlugins,
    discard: discardPlugins,
    draftId: pluginDraftId,
    hasChanges: pluginsHaveChanges,
    tree: pluginTree,
  } = pluginsAdapter;
  const { files: serializedConfigFiles } = serializeConfigs();
  const serverCfgContent = serializedConfigFiles['server.cfg'] || '';

  // Resolve raw qlx_plugins names to full tree paths once on initial load
  useEffect(() => {
    if (pluginsSyncedRef.current) return;
    if (rawQlxPlugins.length === 0 || pluginTree.length === 0) return;
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
    pluginTree.forEach(collectPaths);
    pluginsSyncedRef.current = true;
    const nextCheckedPlugins = new Set(fullPaths);
    setInitialCheckedPlugins(nextCheckedPlugins);
    if (fullPaths.length > 0) {
      setCheckedPlugins(nextCheckedPlugins);
    }
  }, [rawQlxPlugins, pluginTree]);

  // Linter for server.cfg — no port validation in edit mode, but shows managed-cvar info tooltips
  const qlCfgLinterSource = useCallback(() => createQlCfgLinter([], () => {}), []);
  const getLinterSource = (fileName) => {
    const lowerName = fileName?.toLowerCase() || '';
    if (lowerName.endsWith('.cfg')) return qlCfgLinterSource;
    if (lowerName.endsWith('.ent')) return qlentLinter;
    return null;
  };

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
    setIsDirty(true);
  }, []);

  const handleGetBinaryMeta = useCallback(
    (path) => getBinaryMeta(pluginDraftId, path, 'instance', String(instanceId)),
    [pluginDraftId, instanceId],
  );

  const handleSaveBinaryMeta = useCallback(
    (path, description) => (
      saveBinaryMeta(pluginDraftId, path, description, 'instance', String(instanceId))
    ),
    [pluginDraftId, instanceId],
  );

  const loadHooks = useCallback(async ({ seedInitial } = {}) => {
    const loadSeq = hookLoadSeqRef.current + 1;
    hookLoadSeqRef.current = loadSeq;
    try {
      const data = await fetchInstanceHooks(instanceId);
      if (hookLoadSeqRef.current !== loadSeq) return;
      const all = data.available || [];
      const available = all.filter((hook) => !hook.missing);
      const missing = all.filter((hook) => hook.missing).map((hook) => hook.filename);
      const present = new Set(available.map((hook) => hook.filename));

      setHookAvailable(available);
      setHookMissing(missing);
      setHookSystem(data.system_hooks_active || []);
      if (seedInitial) {
        const initOrder = available
          .filter((hook) => hook.enabled)
          .sort((a, b) => a.order - b.order)
          .map((hook) => hook.filename);
        setHookEnabledOrder(initOrder);
        setInitialHookEnabledOrder(initOrder);
      } else {
        setHookEnabledOrder((prev) => prev.filter((filename) => present.has(filename)));
      }
      setHooksLoaded(true);
    } catch (err) {
      if (hookLoadSeqRef.current !== loadSeq) return;
      if (seedInitial) setHooksLoaded(false);
      console.error('EditInstanceConfigModal: Hooks fetch error:', err);
    }
  }, [instanceId]);

  useEffect(() => {
    if (isOpen && instanceId) {
      let cancelled = false;
      setCurrentInstanceName(initialInstanceName || `Instance ${instanceId}`);
      const fetchInitialData = async () => {
        setLoading(true);
        setLoadingPresets(true);
        setError(null);
        setPresetError(null);
        setSaveError(null);
        setSelectedPresetId(''); // Reset preset selection
        // Reset scripts state
        setActiveMainTab(initialTab);
        setScriptHostName(null);
        setDraftPreset(null);
        setHookAvailable([]);
        setHookMissing([]);
        setHookSystem([]);
        setHookEnabledOrder([]);
        setInitialHookEnabledOrder([]);
        setHookDiskChanged(false);
        setHooksLoaded(false);
        setInstanceStatus(null);
        pluginsSyncedRef.current = false;
        setFactoryServerTree([]);

        // Reset restart toggle to default (true) when opening
        setRestartAfterSave(true);

        try {
          const [instanceDetails, configData, presetsData] = await Promise.all([
            getInstanceById(instanceId),
            getInstanceConfig(instanceId),
            getPresets(),
          ]);
          if (cancelled) return;

          // Store raw plugin names — they'll be resolved to full tree paths
          // once the draft tree loads (via the effect below).
          const configuredPlugins = instanceDetails.qlx_plugins
            ? instanceDetails.qlx_plugins.split(',').map(p => p.trim()).filter(Boolean)
            : [];
          setRawQlxPlugins(configuredPlugins);
          setCheckedPlugins(new Set());
          setInitialCheckedPlugins(new Set());

          const fetchedInstanceName = instanceDetails.name || `Instance ${instanceId}`;
          setCurrentInstanceName(fetchedInstanceName);
          setOriginalInstanceName(fetchedInstanceName);
          // Store host name for Scripts and Factories tabs
          const fetchedHostName = instanceDetails.host_name || null;
          setScriptHostName(fetchedHostName);
          setHostOsType(instanceDetails.host_os_type || null);
          setHostLanRateUsesHook(instanceDetails.host_lan_rate_uses_hook === true);
          setInstanceStatus(instanceDetails.status || null);
          const incomingFolders = Array.isArray(configData?.config_folders)
            ? configData.config_folders
            : [];
          const fetchedConfigs = {};
          Object.entries(configData || {}).forEach(([file, value]) => {
            if (file === 'factories' || file === 'config_folders' || typeof value !== 'string') return;
            fetchedConfigs[file] = file === 'server.cfg' ? stripManagedCvars(value) : value;
          });
          CONFIG_FILES_ORDER.forEach(file => {
            if (!(file in fetchedConfigs)) fetchedConfigs[file] = '';
            else if (file === 'server.cfg') fetchedConfigs[file] = stripManagedCvars(fetchedConfigs[file]);
          });
          resetConfigs(fetchedConfigs, incomingFolders);
          resetFactories(configData.factories || {});
          if (fetchedHostName) {
            try {
              setFactoryServerTree(await getFactoryTree({
                host: fetchedHostName,
                instanceId,
              }) || []);
            } catch (factoryTreeError) {
              console.error("EditInstanceConfigModal: Factory tree fetch error:", factoryTreeError);
              setFactoryServerTree([]);
            }
          }
          const fetchedServerHostname = getServerHostname(fetchedConfigs['server.cfg']);
          setServerHostname(fetchedServerHostname);
          setOriginalServerHostname(fetchedServerHostname);
          setLanRateEnabled(instanceDetails.lan_rate_enabled || false);
          setOriginalLanRateEnabled(instanceDetails.lan_rate_enabled || false);
          setIsDirty(false); // Reset dirty state
          setPresets(presetsData || []);
          await loadHooks({ seedInitial: true });
        } catch (err) {
          if (!cancelled) {
            setError(err.message || `Failed to fetch initial data for instance ${instanceId}`);
            console.error("EditInstanceConfigModal: Initial data fetch error:", err);
          }
        } finally {
          if (!cancelled) {
            setLoading(false);
            setLoadingPresets(false);
          }
        }
      };
      fetchInitialData();
      return () => {
        cancelled = true;
        hookLoadSeqRef.current += 1;
      };
    }
    return undefined;
  }, [isOpen, instanceId, initialInstanceName, initialTab, resetConfigs, resetFactories, loadHooks]);

  // Sync effect: Update serverHostname when server.cfg changes (unless it's an internal update)
  useEffect(() => {
    if (!isUpdatingFromServerCfg.current && serverCfgContent) {
      const nextHostname = getServerHostname(serverCfgContent);
      if (nextHostname && nextHostname !== serverHostname) {
        setServerHostname(nextHostname);
      }
    }
  }, [serverCfgContent, serverHostname]);

  const handleHostnameChange = (e) => {
    const newHostname = e.target.value;
    setServerHostname(newHostname);

    // Update server.cfg
    isUpdatingFromServerCfg.current = true;
    readConfigContent('server.cfg').then((cfg) => {
      const regex = /set sv_hostname "([^"]*)"/;
      const nextCfg = regex.test(cfg || '')
        ? cfg.replace(regex, `set sv_hostname "${newHostname}"`)
        : `${cfg || ''}\nset sv_hostname "${newHostname}"`;
      return writeConfigContent('server.cfg', nextCfg);
    }).catch((err) => {
      setSaveError(err?.message || 'Failed to update server.cfg with new hostname.');
    }).finally(() => {
      setTimeout(() => { isUpdatingFromServerCfg.current = false; }, 0);
    });

    setIsDirty(true);
  };

  const lanRateChanged = lanRateEnabled !== originalLanRateEnabled;
  const hostShape = { os_type: hostOsType, lan_rate_uses_hook: hostLanRateUsesHook };
  const canToggleLanRate = canEnableLanRate({
    host: hostShape,
    currentEnabled: originalLanRateEnabled && lanRateEnabled,
  });
  const lanRateUnsupportedReason = !canToggleLanRate && !lanRateEnabled
    ? getLanRateUnsupportedMessage(hostShape)
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

  const checkedPluginsChanged = !setsEqual(checkedPlugins, initialCheckedPlugins);
  const hooksDirty = useMemo(
    () => hookDiskChanged
      || hookEnabledOrder.length !== initialHookEnabledOrder.length
      || hookEnabledOrder.some((filename, index) => initialHookEnabledOrder[index] !== filename),
    [hookDiskChanged, hookEnabledOrder, initialHookEnabledOrder],
  );
  const hooksForceRestart = hooksDirty && instanceStatus === 'running';
  const hooksKeepStopped = hooksDirty && instanceStatus === 'stopped' && !lanRateChanged;
  const restartForced = lanRateChanged || hooksForceRestart || hooksKeepStopped;

  useEffect(() => {
    if (hooksForceRestart) setRestartAfterSave(true);
    if (hooksKeepStopped) setRestartAfterSave(false);
  }, [hooksForceRestart, hooksKeepStopped]);

  const handleRestartToggle = () => {
    if (restartForced) return;
    setRestartAfterSave(prev => !prev);
  };

  const metadataChanged =
    currentInstanceName !== originalInstanceName ||
    serverHostname !== originalServerHostname ||
    lanRateEnabled !== originalLanRateEnabled ||
    restartAfterSave !== true ||
    selectedPresetId !== '';

  useEffect(() => {
    if (!isOpen || loading) return;
    setIsDirty(Boolean(
      configsHaveChanges ||
      factoriesHaveChanges ||
      pluginsHaveChanges ||
      checkedPluginsChanged ||
      hooksDirty ||
      metadataChanged
    ));
  }, [
    checkedPluginsChanged,
    configsHaveChanges,
    factoriesHaveChanges,
    hooksDirty,
    isOpen,
    loading,
    metadataChanged,
    pluginsHaveChanges,
  ]);

  const handleLoadPreset = useCallback(async (presetId) => {
    setPresetError(null);
    try {
      const presetData = await getPresetById(presetId);
      const newConfigs = { ...(presetData.configs || {}) };
      CONFIG_FILES_ORDER.forEach(file => {
        const presetKey = CONFIG_KEY_MAP[file] || file;
        const raw = newConfigs[file] ?? presetData[presetKey] ?? '';
        newConfigs[file] = file === 'server.cfg' ? stripManagedCvars(raw) : raw;
      });
      resetConfigs(newConfigs, presetData.config_folders || []);
      // checked_factories: null = legacy preset (use all factory files); [] or [...] = explicit selection
      const factoriesToLoad = presetData.checked_factories != null
        ? Object.fromEntries(
            presetData.checked_factories
              .filter(f => presetData.factories?.[f] !== undefined)
              .map(f => [f, presetData.factories[f]])
          )
        : (presetData.factories || {});
      resetFactories(factoriesToLoad);
      setCheckedPlugins(new Set(presetData.checked_plugins || []));
      setDraftPreset(presetData.name);
      if (presetData.enabled_hooks !== undefined && presetData.enabled_hooks !== null) {
        setHookEnabledOrder(presetData.enabled_hooks);
        setHooksLoaded(true);
      }

      // Refresh the factory tree to show the preset's available factories
      try {
        setFactoryServerTree(await getFactoryTree({ preset: presetData.name }) || []);
      } catch {
        setFactoryServerTree([]);
      }

      const nextHostname = getServerHostname(newConfigs['server.cfg']);
      setServerHostname(nextHostname);
      setSelectedPresetId(presetId);
      setIsDirty(true);

      setIsPresetManagerOpen(false);
      showSuccess(`Preset "${presetData.name}" loaded successfully.`);
    } catch (err) {
      setPresetError(err.message || `Failed to load preset ${presetId}.`);
    }
  }, [resetConfigs, resetFactories, showSuccess]);

  const handleSavePreset = useCallback(async ({ name, description }) => {
    setIsSavingPreset(true);
    setPresetError(null);
    try {
      const { files: serializedFactories } = serializeFactories();
      const { files: cfgFiles, folders: cfgFolders } = serializeConfigs();
      const presetData = {
        name: name.trim(),
        description: description?.trim() || null,
        configs: cfgFiles,
        config_folders: cfgFolders,
        factories: serializedFactories,
        checked_factories: Object.keys(serializedFactories),
      };

      // Flush any in-progress editor content to the draft before saving preset
      if (pluginFileManagerRef.current?.flushEdits) {
        await pluginFileManagerRef.current.flushEdits();
      }

      // Include draft_id so the backend can snapshot draft files into the preset
      if (pluginDraftId) {
        presetData.draft_id = pluginDraftId;
        presetData.checked_plugins = Array.from(checkedPlugins);
      }

      try {
        presetData.enabled_hooks = enabledHookFilenames(await fetchInstanceHooks(instanceId));
      } catch {
        // Best-effort: skip enabled_hooks if the fetch fails, don't block preset save
      }

      presetData.binary_meta_source = {
        context_type: 'instance',
        context_key: String(instanceId),
      };

      const response = await createPreset(presetData);
      const savedPreset = response.data;

      // Update presets list
      const updatedPresets = await getPresets();
      setPresets(updatedPresets || []);

      setSavedPresetForDownload({
        id: savedPreset.id,
        name: savedPreset.name || name.trim(),
      });
      showSuccess(response.message || `Preset "${name}" saved successfully.`);
    } catch (err) {
      setPresetError(err.error?.message || err.message || 'Failed to save preset.');
      showError('Failed to save preset.');
    } finally {
      setIsSavingPreset(false);
    }
  }, [checkedPlugins, instanceId, pluginDraftId, serializeConfigs, serializeFactories, showSuccess, showError]);

  const handleOverwritePreset = useCallback(async (presetId, { description }) => {
    setIsSavingPreset(true);
    setPresetError(null);
    try {
      const { files: serializedFactories } = serializeFactories();
      const { files: cfgFiles, folders: cfgFolders } = serializeConfigs();
      if (pluginFileManagerRef.current?.flushEdits) {
        await pluginFileManagerRef.current.flushEdits();
      }
      const presetData = {
        description: description || null,
        configs: cfgFiles,
        config_folders: cfgFolders,
        factories: serializedFactories,
        checked_factories: Object.keys(serializedFactories),
      };
      if (pluginDraftId) {
        presetData.draft_id = pluginDraftId;
        presetData.checked_plugins = Array.from(checkedPlugins);
      }
      try {
        presetData.enabled_hooks = enabledHookFilenames(await fetchInstanceHooks(instanceId));
      } catch {
        // Best-effort: skip enabled_hooks if the fetch fails, don't block preset save
      }
      presetData.binary_meta_source = { context_type: 'instance', context_key: String(instanceId) };
      const response = await updatePreset(presetId, presetData);
      const updatedPresets = await getPresets();
      setPresets(updatedPresets || []);
      const saved = response.data || {};
      setSavedPresetForDownload({ id: saved.id ?? presetId, name: saved.name });
      showSuccess(response.message || 'Preset overwritten successfully.');
    } catch (err) {
      setPresetError(err.error?.message || err.message || 'Failed to overwrite preset.');
      showError('Failed to overwrite preset.');
    } finally {
      setIsSavingPreset(false);
    }
  }, [checkedPlugins, instanceId, pluginDraftId, serializeConfigs, serializeFactories, showSuccess, showError]);

  const handlePresetDeleted = useCallback((deletedPresetId) => {
    setPresets(prevPresets => prevPresets.filter(p => p.id !== deletedPresetId));
    if (selectedPresetId === deletedPresetId.toString()) {
      setSelectedPresetId('');
    }
    showSuccess('Preset deleted successfully.');
  }, [selectedPresetId, showSuccess]);

  const handlePresetRenamed = useCallback((presetId, newName) => {
    setPresets(prevPresets => prevPresets.map(p => (p.id === presetId ? { ...p, name: newName } : p)));
    showSuccess('Preset renamed successfully.');
  }, [showSuccess]);

  const handlePresetImported = useCallback(async () => {
    try {
      const refreshed = await getPresets();
      setPresets(refreshed || []);
    } catch (err) {
      console.error('Failed to refresh presets after import:', err);
    }
  }, []);

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

      // Flush any in-progress plugin editor content to the draft before building payload.
      if (pluginFileManagerRef.current?.flushEdits) {
        await pluginFileManagerRef.current.flushEdits();
      }

      const { files: cfgFiles, folders: cfgFolders } = serializeConfigs();
      const configPayload = {
        name: currentInstanceName,
        hostname: serverHostname,
        lan_rate_enabled: lanRateEnabled,
        restart: restartAfterSave,
        configs: cfgFiles,
        config_folders: cfgFolders,
        factories: serializeFactories().files,
        draft_id: pluginDraftId,
        checked_plugins: Array.from(checkedPlugins)
          .filter(p => p.endsWith('.py') && !p.endsWith('__init__.py'))
          .map(p => p.replace(/\.py$/, '').replace(/^.*\//, '')),
      };
      if (hooksLoaded) {
        configPayload.enabled_hooks = hookEnabledOrder;
      }

      // Pass restart parameter to updateInstanceConfig
      const response = await updateInstanceConfig(instanceId, configPayload, restartAfterSave);

      const successMsg = lanRateChanged
        ? `Configuration and LAN rate saved successfully. Task queued.`
        : (response.message || 'Configuration saved successfully. Task queued.');

      // Append info about restart status if not implicit in the message
      const restartMsg = restartAfterSave ? " (Restarting)" : " (Restart skipped)";
      showSuccess(successMsg + restartMsg);

      consumePlugins();
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

  const handleToggleHook = useCallback((filename) => {
    setHookEnabledOrder((cur) => (
      cur.includes(filename) ? cur.filter((name) => name !== filename) : [...cur, filename]
    ));
  }, []);

  const handleReorderHooks = useCallback((nextOrder) => setHookEnabledOrder(nextOrder), []);

  const handleRemoveMissingHook = useCallback((filename) => {
    setHookMissing((cur) => cur.filter((name) => name !== filename));
    setHookEnabledOrder((cur) => cur.filter((name) => name !== filename));
  }, []);

  const handleRefreshHooks = useCallback((options = {}) => {
    if (options.hooksChanged) setHookDiskChanged(true);
    return loadHooks();
  }, [loadHooks]);

  const handleExpandEditor = (selectedFile, content = '') => {
    const fileNameToExpand = typeof selectedFile === 'string'
      ? selectedFile
      : (selectedFile?.path || selectedFile?.name || '');
    setExpandedPluginPath(null);
    setExpandedFactoryPath(null);
    setExpandedFileName(fileNameToExpand);
    setExpandedFileContent(content || serializeConfigs().files[fileNameToExpand] || '');
    setExpandedFileLanguage(getLanguageForFile(fileNameToExpand));
    setExpandedFileLinterSource(getLinterSource(fileNameToExpand));
    setIsExpandedEditorOpen(true);
  };

  const handleExpandPluginEditor = useCallback((selectedFile, content) => {
    setExpandedFactoryPath(null);
    setExpandedPluginPath(selectedFile.path);
    setExpandedFileName(selectedFile.name);
    setExpandedFileContent(content);
    setExpandedFileLanguage(selectedFile.name.endsWith('.py') ? python() : null);
    setExpandedFileLinterSource(null);
    setIsExpandedEditorOpen(true);
  }, []);

  const handleExpandFactoryEditor = useCallback((selectedFile, content = '') => {
    const fileName = selectedFile?.name || '';
    const filePath = selectedFile?.path || fileName;
    setExpandedPluginPath(null);
    setExpandedFactoryPath(filePath);
    setExpandedFileName(fileName);
    setExpandedFileContent(content);
    setExpandedFileLanguage(getFactoryLanguage(fileName));
    setExpandedFileLinterSource(getFactoryLinterSource(fileName));
    setIsExpandedEditorOpen(true);
  }, []);

  const handleExpandedEditorContentChange = (newContent) => {
    setExpandedFileContent(newContent);
    if (expandedPluginPath) {
      if (pluginFileManagerRef.current?.updateContent) {
        pluginFileManagerRef.current.updateContent(expandedPluginPath, newContent);
      }
    } else if (expandedFactoryPath) {
      factoriesAdapter.writeContent(expandedFactoryPath, newContent).catch((err) => {
        setSaveError(err.message || 'Failed to update expanded editor content.');
      });
    } else {
      writeConfigContent(expandedFileName, newContent).catch((err) => {
        setSaveError(err.message || 'Failed to update expanded editor content.');
      });
    }
    setIsDirty(true);
  };

  const handleCloseExpandedEditor = () => {
    // Potentially add unsaved changes check for expanded modal here if needed
    setExpandedPluginPath(null);
    setExpandedFactoryPath(null);
    setIsExpandedEditorOpen(false);
  };

  const handleAttemptClose = () => {
    if (isDirty) {
      setShowCloseConfirm(true);
    } else {
      discardPlugins();
      onClose(); // Call original onClose if not dirty
    }
  };

  const confirmModalClose = () => {
    setShowCloseConfirm(false);
    setIsDirty(false); // Reset dirty state as we are discarding changes
    discardPlugins();
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
      <Dialog open={isOpen} as="div" className="relative z-50" onClose={handleAttemptClose}>
        <DialogBackdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0" />

          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-center justify-center p-4 text-center">
                <Dialog.Panel transition className="modal-panel w-full max-w-[87.1rem] transform p-4 lg:p-6 text-left align-middle transition-all h-[90vh] max-h-[90vh] flex flex-col transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:translate-y-4 data-[closed]:scale-95">
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
                        <div className="mb-2 lg:mb-4 flex-shrink-0">
                          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:gap-6">
                            {/* Server Hostname Input */}
                            <div className="min-w-0 flex-1">
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
                                  maxLength={64}
                                  className="input-base pr-16"
                                  placeholder="Enter server hostname"
                                />
                                <span className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none">
                                  <span className="font-mono text-[10px] font-bold tracking-wider uppercase px-1.5 py-0.5 rounded bg-[var(--surface-elevated)] border border-[var(--surface-border)] text-[var(--text-muted)]">
                                    AUTO
                                  </span>
                                </span>
                              </div>
                              <div className="mt-1 flex items-center justify-between">
                                <p className="text-sm text-[var(--text-muted)] hidden lg:block">
                                  Synced with <code className="text-xs bg-[var(--surface-elevated)] px-1 py-0.5 rounded font-mono text-[var(--text-secondary)]">sv_hostname</code> in server.cfg.
                                </p>
                                <p className={`text-xs ml-auto ${serverHostname.length > 64 ? 'text-red-500' : serverHostname.length >= 50 ? 'text-amber-500' : 'text-[var(--text-muted)]'}`}>
                                  {serverHostname.length} / 64
                                </p>
                              </div>
                            </div>

                            {/* Toggle Switches Container */}
                            <div className="flex flex-shrink-0 flex-wrap items-center gap-5 lg:gap-6">
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
                              <div className="flex items-center gap-3">
                                <button
                                  type="button"
                                  onClick={handleRestartToggle}
                                  disabled={saving || loading || restartForced}
                                  className="neu-toggle"
                                  aria-pressed={restartAfterSave}
                                >
                                  <span className="sr-only">Toggle Restart after Save</span>
                                  <span className={`neu-toggle__track ${restartAfterSave ? 'neu-toggle__track--on' : 'neu-toggle__track--off'}`}>
                                    <span className={`neu-toggle__knob ${restartAfterSave ? 'neu-toggle__knob--on' : 'neu-toggle__knob--off'}`} />
                                  </span>
                                </button>
                                <span className={`flex items-center text-sm font-medium ${restartForced ? 'text-[var(--text-muted)]' : 'text-[var(--text-primary)]'}`}>
                                  <RotateCw size={16} className={`mr-2 ${restartAfterSave ? 'text-[var(--accent-primary)]' : 'text-[var(--text-muted)]'}`} />
                                  Restart after saving
                                </span>
                                {restartForced && (
                                  <InfoTooltip
                                    text={lanRateChanged
                                      ? 'Changing 99k LAN Rate requires an instance restart'
                                      : hooksForceRestart
                                        ? 'Changing hooks requires an instance restart'
                                        : 'Stopped instances stay stopped when hook changes are saved'}
                                    variant="warning"
                                    size={14}
                                  />
                                )}
                              </div>
                            </div>
                          </div>
                          {presetError && (
                            <p className="mt-2 text-sm font-medium text-theme-danger">{presetError}</p>
                          )}
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
                        <div className="flex flex-shrink-0 border border-[var(--surface-border)] bg-[var(--surface-elevated)] rounded-t-xl overflow-hidden mb-0">
                          {[
                            { key: 'config', icon: Settings, label: 'Configuration Files' },
                            { key: 'scripts', icon: Code2, label: 'Plugins' },
                            { key: 'factories', icon: LayoutGrid, label: 'Factories' },
                            { key: 'hooks', icon: Webhook, label: 'Hooks' },
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
                          <div className={activeMainTab === 'config' ? 'flex-1 min-h-0' : 'hidden'}>
                            <FileManager
                              adapter={configsAdapter}
                              capabilities={CONFIG_CAPS}
                              defaultSelectedPath="server.cfg"
                              onExpandEditor={handleExpandEditor}
                              getLanguageForFile={getLanguageForFile}
                              getLinterSourceForFile={getLinterSource}
                            />
                          </div>
                          <div className={activeMainTab === 'scripts' ? 'flex-1 min-h-0' : 'hidden'}>
                            <FileManager
                              ref={pluginFileManagerRef}
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
                                contextType: 'instance',
                                contextKey: String(instanceId),
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
                          {activeMainTab === 'hooks' && (
                            <div className="flex-1 min-h-0">
                              <HooksTab
                                instanceId={instanceId}
                                available={hookAvailable}
                                missing={hookMissing}
                                systemHooks={hookSystem}
                                enabledOrder={hookEnabledOrder}
                                dirty={hooksDirty}
                                onToggleHook={handleToggleHook}
                                onReorderHooks={handleReorderHooks}
                                onRemoveMissing={handleRemoveMissingHook}
                                onRefresh={handleRefreshHooks}
                                instanceStatus={instanceStatus}
                              />
                            </div>
                          )}
                        </div>

                        <div className="mt-4 flex justify-between items-center flex-shrink-0">
                          {/* Left side - Preset management buttons (non-hooks tabs only) */}
                          <div className="flex gap-2">
                            {activeMainTab !== 'hooks' && (
                              <>
                                <button
                                  type="button"
                                  onClick={() => { setSavedPresetForDownload(null); setPresetError(null); setPresetManagerTab('load'); setIsPresetManagerOpen(true); }}
                                  className="btn btn-secondary"
                                >
                                  <FolderOpen className="w-4 h-4 mr-2" />
                                  Load Preset
                                </button>
                                <button
                                  type="button"
                                  onClick={() => { setSavedPresetForDownload(null); setPresetError(null); setPresetManagerTab('save'); setIsPresetManagerOpen(true); }}
                                  className="btn btn-secondary"
                                >
                                  <Save className="w-4 h-4 mr-2" />
                                  Save Preset
                                </button>
                              </>
                            )}
                          </div>

                          {/* Right side - Esc hint + Cancel + Save */}
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
            </div>
          </div>
      </Dialog>

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

      {/* Preset Manager Modal */}
      <PresetManagerModal
        isOpen={isPresetManagerOpen}
        onClose={() => { setIsPresetManagerOpen(false); setSavedPresetForDownload(null); setPresetError(null); }}
        initialTab={presetManagerTab}
        zIndexClass="z-[60]"
        presets={presets}
        isLoading={loadingPresets}
        onLoadPreset={handleLoadPreset}
        onSavePreset={handleSavePreset}
        onOverwritePreset={handleOverwritePreset}
        isSaving={isSavingPreset}
        savedPreset={savedPresetForDownload}
        onPresetDeleted={handlePresetDeleted}
        onPresetRenamed={handlePresetRenamed}
        onPresetImported={handlePresetImported}
      />
    </>
  );
}

export default EditInstanceConfigModal;
