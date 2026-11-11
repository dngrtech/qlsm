import { useEffect, useMemo, useState } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { X, FileJson, AlertTriangle, Download, CircleAlert } from 'lucide-react';
import { RUNTIME_OPTIONS } from '../../constants/runtimes';
import { validateManifestPlugins, validateManifestAddons, issueCounts } from '../../utils/pluginManifestValidation';
import { triggerManifestDownload, DEFAULT_MANIFEST_FILENAME } from '../../utils/pluginManifestDownload';
import {
  blankPlugin, blankAddon, blankCvar, blankCommand, buildManifestDraft, buildAddonDraft,
} from '../../utils/pluginManifestDraft';
import PluginManifestPluginList from './PluginManifestPluginList';
import PluginManifestAddonList from './PluginManifestAddonList';
import PluginManifestAddonFields from './PluginManifestAddonFields';
import PluginManifestCvarRows from './PluginManifestCvarRows';
import PluginManifestCommandRows from './PluginManifestCommandRows';
import PluginManifestIssues from './PluginManifestIssues';

/**
 * Edits a local, in-memory copy of one repository's plugin and addon lists
 * and exports them as a new qlsm-repository.json to download.
 *
 * Deliberately does not save anything back into this repository's row:
 * `PluginRepository.manifest_json` is a verbatim cache of the last fetch from
 * the repo's own URL (see ui/models.py), and every Sync overwrites it from
 * that URL again. An edit qlsm itself remembered would just look reverted
 * the next time someone clicked Sync -- so this is an authoring aid for the
 * file you commit to the repository's actual source, not a live editor of
 * what qlsm has stored.
 */
function PluginManifestEditorModal({ isOpen, onClose, repo }) {
  const [plugins, setPlugins] = useState([]);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [addons, setAddons] = useState([]);
  const [selectedAddonIndex, setSelectedAddonIndex] = useState(-1);
  const [tab, setTab] = useState('plugins');
  const [filename, setFilename] = useState(DEFAULT_MANIFEST_FILENAME);

  // Seeded on open and on a change of *which* repository is being edited --
  // deliberately not on `repo`'s object identity. PluginRepositoriesPage
  // replaces the whole repos array on every silent poll (a finished plugin
  // download triggers one), so depending on the object itself would throw the
  // operator's in-progress edits away mid-session with no warning.
  useEffect(() => {
    if (isOpen) {
      const draft = buildManifestDraft(repo?.plugins);
      setPlugins(draft);
      setSelectedIndex(draft.length ? 0 : -1);
      const addonDraft = buildAddonDraft(repo?.addons);
      setAddons(addonDraft);
      setSelectedAddonIndex(addonDraft.length ? 0 : -1);
      // An addon-only repository opens on its addons, everything else on plugins.
      setTab(draft.length || !addonDraft.length ? 'plugins' : 'addons');
      setFilename(DEFAULT_MANIFEST_FILENAME);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, repo?.id]);

  const issues = useMemo(
    () => [...validateManifestPlugins(plugins), ...validateManifestAddons(addons)],
    [plugins, addons],
  );
  const { errors, warnings } = useMemo(() => issueCounts(issues), [issues]);
  // Plugin issues carry no `kind`; addon issues carry kind 'addon'. The two
  // lists number their rows independently, so they get separate buckets.
  const [issuesByPlugin, issuesByAddon] = useMemo(() => {
    const byPlugin = new Map();
    const byAddon = new Map();
    issues.forEach((iss) => {
      if (iss.index === undefined) return;
      const map = iss.kind === 'addon' ? byAddon : byPlugin;
      const bucket = map.get(iss.index) || { errors: 0, warnings: 0 };
      if (iss.severity === 'error') bucket.errors += 1; else bucket.warnings += 1;
      map.set(iss.index, bucket);
    });
    return [byPlugin, byAddon];
  }, [issues]);

  const updatePlugin = (index, patch) => {
    setPlugins((prev) => prev.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  };
  const updateCvar = (cIndex, patch) => {
    setPlugins((prev) => prev.map((p, i) => (i !== selectedIndex ? p : {
      ...p,
      cvars: p.cvars.map((c, j) => (j === cIndex ? { ...c, ...patch } : c)),
    })));
  };
  const updateCommand = (cIndex, patch) => {
    setPlugins((prev) => prev.map((p, i) => (i !== selectedIndex ? p : {
      ...p,
      commands: p.commands.map((c, j) => (j === cIndex ? { ...c, ...patch } : c)),
    })));
  };

  const addPlugin = () => {
    setPlugins((prev) => [...prev, blankPlugin()]);
    setSelectedIndex(plugins.length);
  };
  const removePlugin = (index) => {
    setPlugins((prev) => prev.filter((_, i) => i !== index));
    setSelectedIndex((prev) => {
      if (index < prev) return prev - 1;
      if (index === prev) return Math.min(prev, plugins.length - 2);
      return prev;
    });
  };
  const addCvar = () => updatePlugin(selectedIndex, { cvars: [...(plugins[selectedIndex].cvars || []), blankCvar()] });
  const removeCvar = (cIndex) => updatePlugin(selectedIndex, { cvars: plugins[selectedIndex].cvars.filter((_, j) => j !== cIndex) });
  const addCommand = () => updatePlugin(selectedIndex, { commands: [...(plugins[selectedIndex].commands || []), blankCommand()] });
  const removeCommand = (cIndex) => updatePlugin(selectedIndex, { commands: plugins[selectedIndex].commands.filter((_, j) => j !== cIndex) });

  const updateAddon = (patch) => {
    setAddons((prev) => prev.map((a, i) => (i === selectedAddonIndex ? { ...a, ...patch } : a)));
  };
  const addAddon = () => {
    setAddons((prev) => [...prev, blankAddon()]);
    setSelectedAddonIndex(addons.length);
  };
  const removeAddon = (index) => {
    setAddons((prev) => prev.filter((_, i) => i !== index));
    setSelectedAddonIndex((prev) => {
      if (index < prev) return prev - 1;
      if (index === prev) return Math.min(prev, addons.length - 2);
      return prev;
    });
  };

  const selectIssue = (iss) => {
    if (iss.kind === 'addon') {
      setTab('addons');
      setSelectedAddonIndex(iss.index);
    } else {
      setTab('plugins');
      setSelectedIndex(iss.index);
    }
  };

  const handleDownload = () => {
    triggerManifestDownload(filename, plugins, addons);
  };

  // Reordering (drag or Sort A-Z) moves plugins around in the array, so the
  // currently-selected row is tracked by its stable _key across the move and
  // selectedIndex is recomputed from where that key landed -- an index alone
  // would end up pointed at whatever plugin happened to slide into that slot.
  const reorderTo = (nextPlugins) => {
    const selectedKey = selectedIndex >= 0 ? plugins[selectedIndex]?._key : null;
    setPlugins(nextPlugins);
    if (selectedKey) {
      setSelectedIndex(nextPlugins.findIndex((p) => p._key === selectedKey));
    }
  };

  const selected = selectedIndex >= 0 ? plugins[selectedIndex] : null;
  const selectedAddon = selectedAddonIndex >= 0 ? addons[selectedAddonIndex] : null;
  const tabClass = (name) => `flex-1 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
    tab === name
      ? 'bg-black/[0.06] dark:bg-white/[0.08] text-[var(--text-primary)]'
      : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
  }`;

  return (
    <Dialog open={isOpen} as="div" className="relative z-50" onClose={onClose}>
      <DialogBackdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0" />

      <div className="fixed inset-0 overflow-y-auto">
        <div className="flex min-h-full items-center justify-center p-4">
          <Dialog.Panel transition className="modal-panel w-full max-w-5xl h-[85vh] max-h-[85vh] p-6 flex flex-col transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:scale-95">
            <div className="accent-line-top" />

            <div className="relative z-10 flex items-center justify-between mb-1 flex-shrink-0">
              <Dialog.Title as="h3" className="flex items-center gap-3">
                <FileJson className="w-5 h-5" />
                <span className="font-display text-xl font-semibold tracking-wider uppercase text-theme-primary">
                  Edit Manifest — {repo?.name}
                </span>
              </Dialog.Title>
              <button
                onClick={onClose}
                className="p-1.5 rounded-md text-slate-400 hover:text-slate-200 hover:bg-slate-700/50 transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <p className="text-xs text-[var(--text-muted)] mb-4 flex-shrink-0">
              Edits a local copy of this repository&apos;s plugin and addon lists. Download writes a new{' '}
              <code>qlsm-repository.json</code> for you to commit to the repository itself — Sync always
              re-fetches from the source URL, so nothing here is saved by qlsm. Only the entries qlsm
              could read at the last sync are listed; anything it skipped is not in this file either.
            </p>

            <div className="relative z-10 flex-1 min-h-0 grid grid-cols-1 md:grid-cols-[260px_1fr] gap-4">
              <div className="flex flex-col min-h-0 gap-2">
                <div role="tablist" aria-label="Manifest sections" className="flex gap-1 p-1 rounded-lg border border-[var(--surface-border)] flex-shrink-0">
                  <button type="button" role="tab" aria-selected={tab === 'plugins'} onClick={() => setTab('plugins')} className={tabClass('plugins')}>
                    Plugins ({plugins.length})
                  </button>
                  <button type="button" role="tab" aria-selected={tab === 'addons'} onClick={() => setTab('addons')} className={tabClass('addons')}>
                    Addons ({addons.length})
                  </button>
                </div>
                {tab === 'plugins' ? (
                  <PluginManifestPluginList
                    plugins={plugins}
                    selectedIndex={selectedIndex}
                    issuesByPlugin={issuesByPlugin}
                    onSelect={setSelectedIndex}
                    onRemove={removePlugin}
                    onAdd={addPlugin}
                    onReorder={reorderTo}
                  />
                ) : (
                  <PluginManifestAddonList
                    addons={addons}
                    selectedIndex={selectedAddonIndex}
                    issuesByAddon={issuesByAddon}
                    onSelect={setSelectedAddonIndex}
                    onRemove={removeAddon}
                    onAdd={addAddon}
                  />
                )}
              </div>

              {/* Selected plugin or addon editor */}
              <div className="flex flex-col min-h-0 overflow-y-auto scrollbar-thin pr-1">
                {tab === 'addons' ? (
                  selectedAddon ? (
                    <PluginManifestAddonFields key={selectedAddon._key} addon={selectedAddon} onChange={updateAddon} />
                  ) : (
                    <p className="text-sm text-[var(--text-muted)] p-4">Add an addon, or pick one on the left, to edit it.</p>
                  )
                ) : !selected ? (
                  <p className="text-sm text-[var(--text-muted)] p-4">Add a plugin, or pick one on the left, to edit it.</p>
                ) : (
                  <div className="space-y-5 pb-2">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="label-tech mb-1.5 block">Filename</label>
                        <input
                          type="text"
                          className="input-base font-mono"
                          placeholder="myplugin.py"
                          value={selected.filename}
                          onChange={(e) => updatePlugin(selectedIndex, { filename: e.target.value })}
                        />
                      </div>
                      <div>
                        <label className="label-tech mb-1.5 block">Label</label>
                        <input
                          type="text"
                          className="input-base"
                          value={selected.label}
                          onChange={(e) => updatePlugin(selectedIndex, { label: e.target.value })}
                        />
                      </div>
                    </div>
                    <div>
                      <label className="label-tech mb-1.5 block">Description</label>
                      <textarea
                        className="input-base"
                        rows={2}
                        value={selected.description}
                        onChange={(e) => updatePlugin(selectedIndex, { description: e.target.value })}
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="label-tech mb-1.5 block">Runtime</label>
                        <select
                          className="input-base"
                          value={selected.runtime}
                          onChange={(e) => updatePlugin(selectedIndex, { runtime: e.target.value })}
                        >
                          <option value="">Not declared</option>
                          {RUNTIME_OPTIONS.map((opt) => (
                            <option key={opt.id} value={opt.id}>{opt.name}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="label-tech mb-1.5 block">Requires qlsm version</label>
                        <input
                          type="text"
                          className="input-base font-mono"
                          placeholder="1.36.0"
                          value={selected.requires_qlsm_version}
                          onChange={(e) => updatePlugin(selectedIndex, { requires_qlsm_version: e.target.value })}
                        />
                      </div>
                    </div>

                    <PluginManifestCvarRows
                      cvars={selected.cvars}
                      onAdd={addCvar}
                      onUpdate={updateCvar}
                      onRemove={removeCvar}
                    />
                    <PluginManifestCommandRows
                      commands={selected.commands}
                      onAdd={addCommand}
                      onUpdate={updateCommand}
                      onRemove={removeCommand}
                    />
                  </div>
                )}
              </div>
            </div>

            <PluginManifestIssues issues={issues} onSelect={selectIssue} />

            <div className="relative z-10 flex items-center justify-between gap-3 pt-4 mt-2 border-t border-slate-700/50 flex-shrink-0">
              <div className="flex items-center gap-2 text-xs">
                {errors > 0 ? (
                  <span className="flex items-center gap-1 text-red-500 dark:text-[#FF3366]">
                    <AlertTriangle size={14} /> {errors} error{errors === 1 ? '' : 's'}
                    {warnings > 0 && ` · ${warnings} warning${warnings === 1 ? '' : 's'}`}
                  </span>
                ) : warnings > 0 ? (
                  <span className="flex items-center gap-1 text-amber-500">
                    <CircleAlert size={14} /> {warnings} warning{warnings === 1 ? '' : 's'}
                  </span>
                ) : (
                  <span className="text-emerald-500">Looks good</span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  className="input-base font-mono text-xs w-48"
                  value={filename}
                  onChange={(e) => setFilename(e.target.value)}
                  aria-label="Export filename"
                />
                <button type="button" onClick={onClose} className="btn btn-secondary">Close</button>
                <button type="button" onClick={handleDownload} className="btn btn-primary">
                  <Download className="w-4 h-4" />
                  Download
                </button>
              </div>
            </div>
          </Dialog.Panel>
        </div>
      </div>
    </Dialog>
  );
}

export default PluginManifestEditorModal;
