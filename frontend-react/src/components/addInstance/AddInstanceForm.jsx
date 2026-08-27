import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { LoaderCircle, Save, FolderOpen, Settings, Code2, LayoutGrid, Webhook, CheckCircle, AlertTriangle, X } from 'lucide-react';
import { json, jsonParseLinter } from '@codemirror/lang-json';
import { python } from '@codemirror/lang-python';
import { getAvailablePortsForHost, getFactoryContent, getFactoryTree, getPresetById, getPresets, savePreset, updatePreset } from '../../services/api';
import { getBinaryMeta, saveBinaryMeta, uploadDraftHook, deleteDraftHook } from '../../services/draftApi';
import InstanceBasicInfoForm from './InstanceBasicInfoForm';
import InstanceOptionsRow from './InstanceOptionsRow';
import { buildRedisDbOptions, nextFreeRedisDb } from './redisDbOptions';
import HooksTab from '../instances/HooksTab';
import PresetManagerModal from '../presetManager/PresetManagerModal';
import InfoTooltip from '../common/InfoTooltip';
import FullScreenConfigEditorModal from '../config/FullScreenConfigEditorModal';
import SubfolderPluginNotice from '../fileManager/SubfolderPluginNotice';
import {
  CONFIG_CAPS,
  FACTORY_CAPS,
  FileManager,
  PLUGIN_CAPS,
  useDraftAdapter,
  useStateAdapter,
} from '../fileManager';
import { partitionCheckedPaths, toQlxPluginNames } from '../fileManager/pluginSelection';
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
  isLanRateForcedOn,
  isLanRateSupported,
} from '../../utils/lanRateCompatibility';
import { validateZmqPassword } from '../../utils/zmqPassword';
import { defaultPresetNameForRuntime, runtimeLabel } from '../../constants/runtimes';
import { presetRuntimeStripWarning } from '../../utils/presetRuntimeCompat';
import { combineAcceptedPaths, mergeReplacements } from '../../utils/presetCompatibility';
import PresetCompatibilityDialog from '../presetManager/PresetCompatibilityDialog';

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

function seedCheckedPlugins(paths) {
  return partitionCheckedPaths(paths || []);
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
  // Plugin/hook seeds are per-runtime: minqlx plugins do not load on
  // minqlxtended, so every seed site resolves through the selected host rather
  // than a single flat default.
  const initialHostRuntime = (initialData.hosts || [])
    .find((host) => String(host.id) === String(initialHostId))?.runtime;
  const seedForRuntime = useCallback((runtime) => (
    (initialData.defaultSeedsByRuntime || {})[runtimeLabel(runtime)]
      || { checkedPlugins: [], availableHooks: [], enabledHooks: [] }
  ), [initialData.defaultSeedsByRuntime]);
  const initialSeed = seedForRuntime(initialHostRuntime);

  const [name, setName] = useState('');
  const [selectedHostId, setSelectedHostId] = useState('');
  const [port, setPort] = useState('');
  const [redisDb, setRedisDb] = useState(1);
  const [hostname, setHostname] = useState('');
  const [lanRateEnabled, setLanRateEnabled] = useState(false);
  const [autoGeneratePasswords, setAutoGeneratePasswords] = useState(true);
  const [zmqStatsPassword, setZmqStatsPassword] = useState('');
  const [zmqRconPassword, setZmqRconPassword] = useState('');
  const [passwordErrors, setPasswordErrors] = useState({});
  const [configContents, setConfigContents] = useState(() => normalizeConfigMap(initialData.defaultConfigContents || createEmptyConfigMap()));
  const [availablePorts, setAvailablePorts] = useState([]);
  const [loadingPorts, setLoadingPorts] = useState(false);
  const [internalFormError, setInternalFormError] = useState(null);
  const [serverCfgHasLintErrors, setServerCfgHasLintErrors] = useState(false);
  const [isFullScreenEditorOpen, setIsFullScreenEditorOpen] = useState(false);
  const [editingFileDetails, setEditingFileDetails] = useState({ name: '', path: '', content: '', language: undefined, linterSource: null, kind: 'config' });

  // Preset manager states
  const [isPresetManagerOpen, setIsPresetManagerOpen] = useState(false);
  const [presetManagerTab, setPresetManagerTab] = useState('load');
  const [isSavingPreset, setIsSavingPreset] = useState(false);
  const [isLoadingPreset, setIsLoadingPreset] = useState(false);
  const [pendingPreset, setPendingPreset] = useState(null); // { id, data } awaiting compat confirmation

  // Local presets state (allows filtering after deletion without refetching)
  const [presets, setPresets] = useState(initialData.presets || []);

  // Loaded preset tracking
  // { id, name, description, runtime, sourceRuntime } or null.
  // `runtime` is the TARGET runtime the preset was applied against (the
  // currently/last selected host's runtime at load time) -- handleHostChange
  // compares this against the newly selected host's runtime to decide
  // whether the loaded preset is stale. `sourceRuntime` is the preset's own
  // declared runtime, i.e. where it was originally saved from -- used by
  // presetRuntimeStripWarning to describe that provenance. These two values
  // differ whenever a preset is loaded cross-runtime; conflating them was
  // the root cause of a prior bug where reselecting a host silently wiped
  // the operator's plugin selection.
  const [loadedPreset, setLoadedPreset] = useState(null);
  const [isPresetModified, setIsPresetModified] = useState(false);
  const [isUpdatingPreset, setIsUpdatingPreset] = useState(false);
  // Set when a host switch invalidates the loaded preset (runtime mismatch)
  // or when the operator cancels the preset compatibility dialog; explains
  // the auto-clear so it isn't silent. Cleared on dismiss or on the next
  // successful preset load.
  const [presetClearedNotice, setPresetClearedNotice] = useState(null);

  // Scripts tab state
  const [activeMainTab, setActiveMainTab] = useState('config'); // 'config' | 'scripts' | 'factories'
  const initialPluginSeed = seedCheckedPlugins(initialSeed.checkedPlugins);
  const [checkedPlugins, setCheckedPlugins] = useState(initialPluginSeed.selectable);
  const [droppedPluginCount, setDroppedPluginCount] = useState(initialPluginSeed.dropped.length);
  const [pluginNoticeDismissed, setPluginNoticeDismissed] = useState(false);
  const pluginsManagerRef = useRef(null);
  const [draftPreset, setDraftPreset] = useState(defaultPresetNameForRuntime(initialHostRuntime));
  // Bare filenames the operator accepted a runtime replacement for, from the
  // preset compatibility dialog. Sent to the draft seed so the server writes
  // the replacement files. Cleared whenever a different preset seed loads.
  const [acceptedReplacements, setAcceptedReplacements] = useState([]);
  const [factoryServerTree, setFactoryServerTree] = useState(initialData.defaultFactoryTree || []);

  // Hooks tab state. There is no instance yet, so hook files come from the
  // preset (default preset on first open); HooksTab renders in its instance-less
  // mode (view + toggle + reorder). enabledHookOrder is the LD_PRELOAD order sent
  // on create as enabled_hooks.
  const [availableHooks, setAvailableHooks] = useState(initialSeed.availableHooks);
  const [enabledHookOrder, setEnabledHookOrder] = useState(initialSeed.enabledHooks);
  const initialEnabledHookOrderRef = useRef(initialSeed.enabledHooks);
  // True when the hook enablement/order differs from the loaded (or default)
  // preset baseline. Feeds both the unsaved-changes guard and the "(modified)"
  // preset indicator.
  const hooksChanged = useMemo(() => {
    const baseline = initialEnabledHookOrderRef.current;
    return (
      enabledHookOrder.length !== baseline.length ||
      enabledHookOrder.some((filename, index) => baseline[index] !== filename)
    );
  }, [enabledHookOrder]);

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
  const initialCheckedPluginsRef = useRef(initialPluginSeed.selectable);
  const loadedPresetConfigRef = useRef(null); // Stores config contents when preset is loaded, for modification detection
  // Mirrors loadedPreset so handleHostChange can read it without taking it as a
  // useCallback dependency. It must not: the mount/reset effect below depends on
  // handleHostChange's identity and calls setLoadedPreset(null), so a new
  // identity on every preset load would re-run that reset and wipe the preset
  // the operator just loaded.
  const loadedPresetRef = useRef(null);
  useEffect(() => { loadedPresetRef.current = loadedPreset; }, [loadedPreset]);
  const loadedPresetCheckedPluginsRef = useRef(initialPluginSeed.selectable);
  // The runtime the plugin/hook seed currently reflects. handleHostChange
  // compares against it so a same-runtime host switch leaves the operator's
  // selection alone, while a cross-runtime switch re-seeds. Invariant: every
  // place that replaces the plugin/hook seed must point this at the runtime
  // the new seed came from -- the mount/reset effect, handleHostChange, and
  // applyPresetData. Leave it stale in any one of them and the next host
  // change compares against the wrong runtime and silently re-seeds over what
  // the operator has.
  const seededRuntimeRef = useRef(runtimeLabel(initialHostRuntime));
  const loadedPresetLanRateRef = useRef(false);

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

  // Hoisted above pluginsAdapter (below) so its runtime is available to feed
  // the draft seed; lanRateSupported/lanRateForcedOn/redisDbOptions further
  // down still read off these same consts.
  const effectiveHostId = selectedHostId || (initialHostId ? String(initialHostId) : '');
  const selectedHost = (initialData.hosts || []).find((host) => String(host.id) === String(effectiveHostId));
  const selectedHostOsType = selectedHost?.os_type ?? null;
  const hasSelectedHost = Boolean(selectedHost);
  const selectedHostShape = {
    os_type: selectedHostOsType,
    lan_rate_uses_hook: selectedHost?.lan_rate_uses_hook ?? false,
    runtime: selectedHost?.runtime ?? null,
  };

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
    targetRuntime: selectedHostShape.runtime,
    acceptedReplacements,
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

    const newHostRecord = (initialData.hosts || []).find((host) => String(host.id) === String(hostId));
    const newRuntime = runtimeLabel(newHostRecord?.runtime);
    const previousRuntime = seededRuntimeRef.current;

    // A preset loaded against one host's runtime is not safe to carry over to
    // a host on the other runtime -- its plugin selection came from the old
    // runtime and would silently be submitted against the new one. Clear it
    // (and say so) rather than leaving it in place unvalidated.
    const carriedPreset = loadedPresetRef.current;
    let presetCleared = false;
    if (carriedPreset && hostId && !isInitialLoad) {
      if (runtimeLabel(carriedPreset.runtime) !== newRuntime) {
        setPresetClearedNotice(
          `The loaded preset "${carriedPreset.name}" no longer matches this host and was cleared — reload it here to apply it. `
          // presetRuntimeStripWarning reads `.runtime` expecting the preset's
          // original source runtime (it says "Saved from a ... host") -- pass
          // sourceRuntime through as runtime rather than carriedPreset itself,
          // whose `.runtime` field tracks the target runtime it was applied
          // against, not where it was saved from.
          + presetRuntimeStripWarning({ ...carriedPreset, runtime: carriedPreset.sourceRuntime }, newHostRecord)
        );
        setLoadedPreset(null);
        loadedPresetConfigRef.current = null;
        presetCleared = true;
      }
    }

    // Re-seed from the new host's runtime. Plugins are not interchangeable
    // between runtimes, so a cross-runtime switch has to move the seed with it
    // -- otherwise the form ships minqlx files to a minqlxtended host. A
    // same-runtime switch leaves whatever the operator selected in place.
    if (hostId && !isInitialLoad && (newRuntime !== previousRuntime || presetCleared)) {
      const seed = seedForRuntime(newRuntime);
      const { selectable, dropped } = seedCheckedPlugins(seed.checkedPlugins);
      setCheckedPlugins(selectable);
      setDroppedPluginCount(dropped.length);
      setPluginNoticeDismissed(false);
      loadedPresetCheckedPluginsRef.current = selectable;
      initialCheckedPluginsRef.current = selectable;
      setAvailableHooks(seed.availableHooks);
      setEnabledHookOrder(seed.enabledHooks);
      initialEnabledHookOrderRef.current = seed.enabledHooks;
      setDraftPreset(defaultPresetNameForRuntime(newRuntime));
      setAcceptedReplacements([]);
    }
    if (hostId) {
      seededRuntimeRef.current = newRuntime;
    }

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

        if (isInitialLoad) {
          const hostRecord = (initialData.hosts || []).find((host) => String(host.id) === String(hostId));
          setRedisDb(nextFreeRedisDb(hostRecord?.instances));
        }

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
  }, [initialData.hosts, seedForRuntime, syncConfigFile, syncConfigState]);

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

    // Seeded from the host the modal opened on, not a flat default: the two
    // runtimes ship different plugins.
    const seed = seedForRuntime(initialHostRuntime);
    setAvailableHooks(seed.availableHooks);
    setEnabledHookOrder(seed.enabledHooks);
    initialEnabledHookOrderRef.current = seed.enabledHooks;

    const { selectable, dropped } = seedCheckedPlugins(seed.checkedPlugins);
    setCheckedPlugins(selectable);
    setDroppedPluginCount(dropped.length);
    setPluginNoticeDismissed(false);
    initialCheckedPluginsRef.current = selectable;
    loadedPresetCheckedPluginsRef.current = selectable;
    setDraftPreset(defaultPresetNameForRuntime(initialHostRuntime));
    setAcceptedReplacements([]);
    seededRuntimeRef.current = runtimeLabel(initialHostRuntime);
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
    initialData.defaultConfigContents,
    initialData.defaultFactories,
    initialData.defaultFactoryTree,
    initialHostId,
    initialHostRuntime,
    resetFactories,
    seedForRuntime,
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
      !autoGeneratePasswords ||
      zmqStatsPassword !== '' ||
      zmqRconPassword !== '' ||
      JSON.stringify(configContents) !== JSON.stringify(initialConfigContentsRef.current) ||
      configsHaveChanges ||
      factoriesHaveChanges ||
      pluginsHaveChanges ||
      checkedPluginsChanged ||
      hooksChanged;
    if (onDirtyStateChange) onDirtyStateChange(isDirty);
  }, [
    autoGeneratePasswords,
    checkedPlugins,
    configContents,
    configsHaveChanges,
    factoriesHaveChanges,
    hooksChanged,
    hostname,
    lanRateEnabled,
    name,
    onDirtyStateChange,
    pluginsHaveChanges,
    port,
    selectedHostId,
    zmqRconPassword,
    zmqStatsPassword,
  ]);

  // Track if loaded preset has been modified
  useEffect(() => {
    if (loadedPreset && loadedPresetConfigRef.current) {
      const modified =
        JSON.stringify(configContents) !== JSON.stringify(loadedPresetConfigRef.current) ||
        configsHaveChanges ||
        factoriesHaveChanges ||
        pluginsHaveChanges ||
        !areSetsEqual(checkedPlugins, loadedPresetCheckedPluginsRef.current) ||
        hooksChanged ||
        lanRateEnabled !== loadedPresetLanRateRef.current;
      setIsPresetModified(modified);
    }
  }, [
    checkedPlugins,
    configContents,
    configsHaveChanges,
    factoriesHaveChanges,
    hooksChanged,
    lanRateEnabled,
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

  const lanRateSupported = !hasSelectedHost || isLanRateSupported(selectedHostShape);
  // QLSM deploys minqlxtended instances at 99k, so the toggle renders on and
  // locked instead of offering a 25k it will not honour.
  const lanRateForcedOn = hasSelectedHost && isLanRateForcedOn(selectedHostShape);
  const lanRateUnavailableReason = hasSelectedHost && (lanRateForcedOn || !lanRateSupported)
    ? getLanRateUnsupportedMessage(selectedHostShape)
    : null;
  const redisDbOptions = useMemo(
    () => buildRedisDbOptions({ instances: selectedHost?.instances }),
    [selectedHost]
  );

  // Handle loading a preset
  const applyPresetData = useCallback(async (presetId, presetData, acceptedPaths = []) => {
    setIsLoadingPreset(true);
    try {
      setInternalFormError(null);
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
      setLoadedPreset({
        id: presetId,
        name: presetData.name,
        description: presetData.description || '',
        is_builtin: !!presetData.is_builtin,
        // The runtime the preset was actually applied against, not the
        // preset's own declared source runtime -- a cross-runtime load's
        // source and target runtimes differ by definition, and
        // handleHostChange compares this field against the currently
        // selected host's runtime to decide whether the preset is still
        // valid. Storing the source runtime here made that comparison
        // mismatch on every subsequent host reselection, even a no-op
        // reselection of the same host, silently wiping the plugin
        // selection this function just set. The preset's true source
        // runtime is preserved separately below as `sourceRuntime`.
        runtime: selectedHostShape.runtime,
        // The preset's own declared source runtime, kept for consumers
        // (e.g. presetRuntimeStripWarning) that need to describe where the
        // preset was originally saved from, as opposed to `runtime` above
        // which tracks the host it's currently applied against.
        sourceRuntime: presetData.runtime,
      });
      setPresetClearedNotice(null);
      // The preset's plugin/hook selection is now the seed, and that seed
      // was built for the host it was just applied against -- so the
      // seeded runtime must be the target runtime (selectedHostShape.runtime),
      // matching `loadedPreset.runtime` above, not the preset's own source
      // runtime (see the comment on that field for why the distinction
      // matters).
      seededRuntimeRef.current = runtimeLabel(selectedHostShape.runtime);
      // Reseed draft workspace with the loaded preset's scripts. acceptedPaths
      // defaults to [] (a plain default, not a speculative clear elsewhere) so
      // a no-dialog load carries nothing forward, and both state updates land
      // in the same render as the one re-seed this load causes.
      setDraftPreset(presetData.name);
      setAcceptedReplacements(acceptedPaths);
      loadedPresetConfigRef.current = newConfigs;

      // Reflect the preset's hooks: available files + enabled order/status.
      const presetAvailableHooks = Array.isArray(presetData.user_hooks) ? presetData.user_hooks : [];
      const presetEnabledHooks = Array.isArray(presetData.enabled_hooks) ? presetData.enabled_hooks : [];
      setAvailableHooks(presetAvailableHooks);
      setEnabledHookOrder(presetEnabledHooks);
      initialEnabledHookOrderRef.current = presetEnabledHooks;
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
        const { selectable, dropped } = partitionCheckedPaths(presetData.checked_plugins);
        nextCheckedBaseline = selectable;
        setCheckedPlugins(selectable);
        setDroppedPluginCount(dropped.length);
        setPluginNoticeDismissed(false);
      }
      loadedPresetCheckedPluginsRef.current = nextCheckedBaseline;
      initialCheckedPluginsRef.current = nextCheckedBaseline;

      // lan_rate_enabled: null/undefined = the preset pre-dates this feature —
      // leave whatever the toggle is currently set to. Clamp inline (rather
      // than relying solely on the reactive lanRateSupported auto-disable
      // effect below) so the initial/loaded-preset refs never capture an
      // unclamped value — otherwise the "preset modified" badge lights up
      // spuriously and Overwrite Preset could silently strip the setting.
      const nextLanRate = presetData.lan_rate_enabled != null
        ? (presetData.lan_rate_enabled && !lanRateSupported ? false : presetData.lan_rate_enabled)
        : lanRateEnabled;
      setLanRateEnabled(nextLanRate);
      initialLanRateEnabledRef.current = nextLanRate;
      loadedPresetLanRateRef.current = nextLanRate;

      setIsPresetManagerOpen(false);
    } catch (err) {
      setInternalFormError(err.error?.message || err.message || `Failed to load preset.`);
    } finally {
      setIsLoadingPreset(false);
    }
  }, [checkedPlugins, lanRateEnabled, lanRateSupported, resetConfigs, resetFactories, syncConfigState, selectedHostShape.runtime]);

  const handleLoadPreset = useCallback(async (presetId) => {
    setIsLoadingPreset(true);
    try {
      setInternalFormError(null);
      const presetData = await getPresetById(presetId, { targetRuntime: selectedHostShape.runtime });
      if (presetData.compatibility?.stripped?.length) {
        setPendingPreset({ id: presetId, data: presetData });
        return;
      }
      // No decision left for the operator, but a cross-runtime load still has
      // replacements the backend applied on its own -- every standard plugin
      // this preset carried unmodified. They have to travel to the draft here
      // too, or the filter deletes those files and writes nothing back.
      const auto = combineAcceptedPaths(presetData);
      await applyPresetData(presetId, mergeReplacements(presetData, auto), auto);
    } catch (err) {
      setInternalFormError(err.error?.message || err.message || `Failed to load preset.`);
    } finally {
      setIsLoadingPreset(false);
    }
  }, [applyPresetData, selectedHostShape.runtime]);

  const handleConfirmPresetCompatibility = useCallback(async (tickedPaths) => {
    if (!pendingPreset) return;
    const { id, data } = pendingPreset;
    setPendingPreset(null);
    // What the operator ticked, plus what was swapped without asking.
    const acceptedPaths = combineAcceptedPaths(data, tickedPaths);
    // applyPresetData sets both draftPreset and acceptedReplacements together
    // (see its own body) -- the accepted list is an argument to "apply this
    // preset", not ambient state some other codepath clears speculatively. A
    // cancelled load therefore calls nothing here at all, leaving whatever
    // preset is currently active, and its accepted replacements, untouched.
    await applyPresetData(id, mergeReplacements(data, acceptedPaths), acceptedPaths);
  }, [applyPresetData, pendingPreset]);

  const handleCancelPresetCompatibility = useCallback(() => {
    const cancelledName = pendingPreset?.data?.name;
    setPendingPreset(null);
    setIsPresetManagerOpen(false);
    if (cancelledName) {
      setPresetClearedNotice(
        `The preset "${cancelledName}" was not applied — its plugin compatibility was not confirmed.`
      );
    }
  }, [pendingPreset]);

  // Handle saving current config as a preset
  const handleSavePreset = useCallback(async ({ name, description, runtime }) => {
    setIsSavingPreset(true);
    try {
      // Map internal config keys to API keys
      const { files: serializedFactories } = serializeFactories();
      const { files: cfgFiles, folders: cfgFolders } = serializeConfigs();
      const presetData = {
        name,
        description: description || null,
        runtime,
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
      // Persist the hook enablement/order so a preset saved here round-trips.
      presetData.enabled_hooks = enabledHookOrder;
      // Persist the 99k LAN rate toggle so it round-trips with the preset.
      presetData.lan_rate_enabled = lanRateEnabled;

      await savePreset(presetData);
      setIsPresetManagerOpen(false);
      setInternalFormError(null);
    } catch (err) {
      // Don't close modal on error, let user retry
      setInternalFormError(err.error?.message || err.message || 'Failed to save preset.');
    } finally {
      setIsSavingPreset(false);
    }
  }, [checkedPlugins, draftPreset, enabledHookOrder, lanRateEnabled, pluginDraftId, serializeConfigs, serializeFactories]);

  const handleOverwritePreset = useCallback(async (presetId, { description, runtime }) => {
    setIsUpdatingPreset(true);
    try {
      const { files: serializedFactoriesUpdate } = serializeFactories();
      const { files: cfgFiles, folders: cfgFolders } = serializeConfigs();
      const presetData = {
        description,
        runtime,
        configs: cfgFiles,
        config_folders: cfgFolders,
        factories: serializedFactoriesUpdate,
        checked_factories: Object.keys(serializedFactoriesUpdate),
      };
      if (pluginsManagerRef.current?.flushEdits) {
        await pluginsManagerRef.current.flushEdits();
      }
      if (pluginDraftId) presetData.draft_id = pluginDraftId;
      presetData.checked_plugins = Array.from(checkedPlugins);
      presetData.enabled_hooks = enabledHookOrder;
      presetData.lan_rate_enabled = lanRateEnabled;
      await updatePreset(presetId, presetData);
      const refreshed = await getPresets();
      setPresets(refreshed || []);
      if (loadedPreset?.id === presetId) {
        loadedPresetConfigRef.current = serializeConfigs().files;
        loadedPresetCheckedPluginsRef.current = new Set(checkedPlugins);
        setLoadedPreset((prev) => (prev ? { ...prev, description: description || '' } : prev));
        setIsPresetModified(false);
      }
      setInternalFormError(null);
      setIsPresetManagerOpen(false);
    } catch (err) {
      setInternalFormError(err.error?.message || err.message || 'Failed to overwrite preset.');
    } finally {
      setIsUpdatingPreset(false);
    }
  }, [checkedPlugins, enabledHookOrder, lanRateEnabled, loadedPreset, pluginDraftId, serializeConfigs, serializeFactories]);

  // Handle preset deletion from PresetManagerModal
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

  // Handle preset rename from PresetManagerModal
  const handlePresetRenamed = useCallback((presetId, newName) => {
    setPresets(prev => prev.map(p => (p.id === presetId ? { ...p, name: newName } : p)));
    setLoadedPreset(prev => (prev?.id === presetId ? { ...prev, name: newName } : prev));
  }, []);

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

  // Hooks tab handlers (instance-less mode: toggle/reorder/remove-missing only).
  const availableHookNames = useMemo(
    () => new Set(availableHooks.map((hook) => hook.filename)),
    [availableHooks],
  );
  const missingHooks = useMemo(
    () => enabledHookOrder.filter((filename) => !availableHookNames.has(filename)),
    [availableHookNames, enabledHookOrder],
  );
  const handleToggleHook = useCallback((filename) => {
    setEnabledHookOrder((cur) => (
      cur.includes(filename) ? cur.filter((name) => name !== filename) : [...cur, filename]
    ));
  }, []);
  const handleReorderHooks = useCallback((nextOrder) => setEnabledHookOrder(nextOrder), []);
  const handleRemoveMissingHook = useCallback((filename) => {
    setEnabledHookOrder((cur) => cur.filter((name) => name !== filename));
  }, []);
  const handleUploadHook = useCallback(async (file) => {
    if (!pluginDraftId) throw new Error('Draft not ready');
    const meta = await uploadDraftHook(pluginDraftId, file);
    setAvailableHooks((cur) => (
      cur.some((h) => h.filename === meta.filename) ? cur : [...cur, meta]
    ));
    return meta;
  }, [pluginDraftId]);
  const handleDeleteHook = useCallback(async (filename) => {
    if (!pluginDraftId) throw new Error('Draft not ready');
    await deleteDraftHook(pluginDraftId, filename);
    setAvailableHooks((cur) => cur.filter((h) => h.filename !== filename));
    setEnabledHookOrder((cur) => cur.filter((name) => name !== filename));
  }, [pluginDraftId]);

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
  // Re-enabling auto-generate disables the password inputs, so any validation
  // errors on them are no longer actionable -- clear them with the toggle.
  const handleAutoGeneratePasswordsChange = useCallback((enabled) => {
    setAutoGeneratePasswords(enabled);
    if (enabled) setPasswordErrors({});
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

  useEffect(() => {
    if (!lanRateSupported && lanRateEnabled) {
      setLanRateEnabled(false);
    }
  }, [lanRateEnabled, lanRateSupported]);

  const localHandleSubmit = async (e) => {
    e.preventDefault();
    if (serverCfgHasLintErrors) { setInternalFormError("Please fix errors in server.cfg before submitting."); return; }
    setInternalFormError(null);

    if (!autoGeneratePasswords) {
      const statsError = validateZmqPassword(zmqStatsPassword, 'ZMQ Stats Password');
      const rconError = validateZmqPassword(zmqRconPassword, 'ZMQ RCON Password');
      if (statsError || rconError) {
        setPasswordErrors({ stats: statsError, rcon: rconError });
        setInternalFormError(statsError || rconError);
        return;
      }
    }
    setPasswordErrors({});

    if (pluginsManagerRef.current?.flushEdits) {
      await pluginsManagerRef.current.flushEdits();
    }

    const checkedPluginNames = toQlxPluginNames(checkedPlugins);
    const submitData = {
      name,
      host_id: parseInt(selectedHostId, 10),
      port: parseInt(port, 10),
      redis_db: redisDb,
      hostname,
      lan_rate_enabled: lanRateEnabled,
      ...(() => { const { files, folders } = serializeConfigs(); return { configs: files, config_folders: folders }; })(),
      factories: serializeFactories().files,
      checked_plugins: checkedPluginNames,
      qlx_plugins: checkedPluginNames.join(', '),
    };

    if (!autoGeneratePasswords) {
      submitData.zmq_stats_password = zmqStatsPassword.trim();
      submitData.zmq_rcon_password = zmqRconPassword.trim();
    }

    if (pluginDraftId) {
      submitData.draft_id = pluginDraftId;
    }
    submitData.enabled_hooks = enabledHookOrder;

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
        <InstanceBasicInfoForm name={name} onNameChange={(e) => setName(e.target.value)} selectedHostId={selectedHostId} onHostChange={handleHostChange} hosts={initialData.hosts || []} port={port} onPortChange={setPort} availablePorts={availablePorts} loadingPorts={loadingPorts} redisDb={redisDb} onRedisDbChange={setRedisDb} redisDbOptions={redisDbOptions} hostname={hostname} onHostnameChange={(e) => setHostname(e.target.value)} />
        <InstanceOptionsRow
          lanRateEnabled={lanRateEnabled}
          onLanRateChange={setLanRateEnabled}
          lanRateDisabled={!lanRateSupported}
          lanRateForcedOn={lanRateForcedOn}
          lanRateUnavailableReason={lanRateUnavailableReason}
          autoGeneratePasswords={autoGeneratePasswords}
          onAutoGeneratePasswordsChange={handleAutoGeneratePasswordsChange}
          zmqStatsPassword={zmqStatsPassword}
          onZmqStatsPasswordChange={setZmqStatsPassword}
          zmqRconPassword={zmqRconPassword}
          onZmqRconPasswordChange={setZmqRconPassword}
          passwordErrors={passwordErrors}
        />
      </div>
      <div className="flex flex-col flex-grow min-h-0 mb-2">
        {/* Shown when a host switch invalidated the loaded preset, or when
            the operator cancelled the preset compatibility dialog */}
        {presetClearedNotice && (
          <div role="status" className="alert-warning mb-3 flex items-start gap-2 text-sm flex-shrink-0">
            <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" style={{ color: 'var(--accent-warning)' }} />
            <span className="flex-1 min-w-0 text-[var(--text-secondary)]">{presetClearedNotice}</span>
            <button
              type="button"
              onClick={() => setPresetClearedNotice(null)}
              aria-label="Dismiss"
              className="flex-shrink-0 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}
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
              { key: 'hooks', icon: Webhook, label: 'Hooks' },
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
            <div className={activeMainTab === 'scripts' ? 'flex-1 min-h-0 flex flex-col' : 'hidden'}>
              <SubfolderPluginNotice
                count={pluginNoticeDismissed ? 0 : droppedPluginCount}
                onDismiss={() => setPluginNoticeDismissed(true)}
              />
              <div className="flex-1 min-h-0">
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
                  instanceId={null}
                  available={availableHooks}
                  missing={missingHooks}
                  systemHooks={[]}
                  enabledOrder={enabledHookOrder}
                  dirty={false}
                  onToggleHook={handleToggleHook}
                  onReorderHooks={handleReorderHooks}
                  onRemoveMissing={handleRemoveMissingHook}
                  uploadHook={pluginDraftId ? handleUploadHook : undefined}
                  deleteHook={pluginDraftId ? handleDeleteHook : undefined}
                />
              </div>
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
      <div className="flex justify-between items-center flex-shrink-0 mt-4">
        {/* Left side - Preset buttons + Esc hint */}
        <div className="flex items-center gap-3">
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => { setPresetManagerTab('save'); setIsPresetManagerOpen(true); }}
              className="btn btn-secondary"
            >
              <Save className="w-4 h-4 mr-2" />
              Save Preset
            </button>
            <span className="flex items-center gap-1.5">
              <button
                type="button"
                onClick={() => { setPresetManagerTab('load'); setIsPresetManagerOpen(true); }}
                className="btn btn-secondary"
                disabled={!hasSelectedHost}
              >
                <FolderOpen className="w-4 h-4 mr-2" />
                Load Preset
              </button>
              {!hasSelectedHost && (
                <InfoTooltip
                  text="Select a host first. Presets are runtime-specific, and QLSM needs to know which runtime to check compatibility against before showing you any."
                  variant="info"
                  size={14}
                />
              )}
            </span>
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
      <PresetManagerModal
        isOpen={isPresetManagerOpen}
        onClose={() => setIsPresetManagerOpen(false)}
        initialTab={presetManagerTab}
        zIndexClass="z-[60]"
        host={selectedHost}
        presets={presets}
        isLoading={false}
        isLoadingPreset={isLoadingPreset}
        onLoadPreset={handleLoadPreset}
        onSavePreset={handleSavePreset}
        onOverwritePreset={handleOverwritePreset}
        isSaving={isSavingPreset || isUpdatingPreset}
        savedPreset={null}
        onPresetDeleted={handlePresetDeleted}
        onPresetRenamed={handlePresetRenamed}
        onPresetImported={handlePresetImported}
        initialOverwriteName={loadedPreset && !loadedPreset.is_builtin ? loadedPreset.name : null}
      />

      <PresetCompatibilityDialog
        isOpen={Boolean(pendingPreset)}
        compatibility={pendingPreset?.data?.compatibility}
        onConfirm={handleConfirmPresetCompatibility}
        onCancel={handleCancelPresetCompatibility}
      />

      <FullScreenConfigEditorModal isOpen={isFullScreenEditorOpen} onClose={handleCloseFullScreenEditor} onSave={handleSaveFullScreenEditor} fileName={editingFileDetails.name} initialContent={editingFileDetails.content} language={editingFileDetails.language} linterSource={editingFileDetails.linterSource} />
    </form>
  );
}

export default AddInstanceForm;
