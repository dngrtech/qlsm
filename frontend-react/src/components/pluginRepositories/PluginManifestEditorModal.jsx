import { useCallback, useEffect, useMemo, useState } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import {
  closestCenter, DndContext, DragOverlay, KeyboardSensor, PointerSensor, useSensor, useSensors,
} from '@dnd-kit/core';
import {
  arrayMove, SortableContext, sortableKeyboardCoordinates, useSortable, verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  X, FileJson, Plus, Trash2, AlertTriangle, Download, CircleAlert, GripVertical, ArrowDownAZ,
} from 'lucide-react';
import { RUNTIME_OPTIONS } from '../../constants/runtimes';
import { validateManifestPlugins, issueCounts } from '../../utils/pluginManifestValidation';
import { triggerManifestDownload } from '../../utils/pluginManifestDownload';

// A stable id per plugin row for @dnd-kit and React keys -- plugin.filename
// can't serve that role here the way it does for HookRow's SortableHookRow,
// since a freshly-added plugin starts blank and two rows can briefly share
// (or lack) a filename while the operator is mid-edit.
let pluginKeySeed = 0;
const makePluginKey = () => `plugin-${pluginKeySeed++}`;

// Blank plugin/cvar/command shapes for "+ Add".
const blankPlugin = () => ({
  _key: makePluginKey(),
  filename: '', label: '', description: '', runtime: '', requires_qlsm_version: '', cvars: [], commands: [],
});
const blankCvar = () => ({ cvar: '', label: '', type: 'string', default: '', description: '' });
const blankCommand = () => ({ name: '', usage: '', description: '' });

function defaultForCvarType(type) {
  if (type === 'number') return 0;
  if (type === 'bool') return false;
  return '';
}

// One row in the plugin list: a drag handle (reorder), the select area, and
// a remove button -- three separate controls rather than one nested inside
// another, so the drag listeners never fight the click handler.
function SortablePluginRow({ plugin, isSelected, errorBucket, onSelect, onRemove }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: plugin._key });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  };
  const displayName = plugin.label || plugin.filename || 'plugin';

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`flex items-center gap-1 px-2 py-2 text-sm border-b border-[var(--surface-border)] last:border-b-0 transition-colors ${
        isSelected ? 'bg-black/[0.05] dark:bg-white/[0.06]' : 'hover:bg-black/[0.03] dark:hover:bg-white/[0.03]'
      }`}
    >
      <button
        type="button"
        {...attributes}
        {...listeners}
        aria-label={`Reorder ${displayName}`}
        className="flex-shrink-0 p-1 rounded text-slate-500 hover:text-slate-300 cursor-grab touch-none"
      >
        <GripVertical size={14} />
      </button>
      <button type="button" onClick={onSelect} className="flex items-center gap-2 min-w-0 flex-1 text-left">
        <span
          className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
            errorBucket?.errors ? 'bg-red-500' : errorBucket?.warnings ? 'bg-amber-500' : 'bg-emerald-500'
          }`}
        />
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[var(--text-primary)]">{plugin.label || plugin.filename || '(untitled)'}</span>
          <span className="block truncate font-mono text-[11px] text-[var(--text-muted)]">{plugin.filename || '—'}</span>
        </span>
      </button>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${displayName}`}
        className="p-1 rounded text-slate-500 hover:text-red-400 hover:bg-red-500/10 flex-shrink-0"
      >
        <Trash2 size={13} />
      </button>
    </div>
  );
}

// What follows the cursor while a row is being dragged -- a static snapshot,
// so it doesn't need (and shouldn't have) its own drag listeners.
function PluginRowOverlay({ plugin }) {
  return (
    <div className="flex items-center gap-1 px-2 py-2 text-sm bg-[var(--surface-raised)] border border-[var(--surface-border)] rounded-md shadow-lg">
      <span className="flex-shrink-0 p-1 text-slate-400"><GripVertical size={14} /></span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[var(--text-primary)]">{plugin.label || plugin.filename || '(untitled)'}</span>
        <span className="block truncate font-mono text-[11px] text-[var(--text-muted)]">{plugin.filename || '—'}</span>
      </span>
    </div>
  );
}

/**
 * Edits a local, in-memory copy of one repository's plugin list and exports
 * it as a new qlsm-plugins.json to download.
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
  const [filename, setFilename] = useState('qlsm-plugins.json');

  useEffect(() => {
    if (isOpen) {
      // Only the fields a real qlsm-plugins.json entry carries -- notably
      // never `version_risk`, which qlsm adds itself at sync time from
      // requires_qlsm_version + this install's own VERSION and is never
      // something to author or ship in the file.
      const draft = (repo?.plugins || []).map((p) => ({
        _key: makePluginKey(),
        filename: p.filename || '',
        label: p.label || '',
        description: p.description || '',
        runtime: p.runtime || '',
        requires_qlsm_version: p.requires_qlsm_version || '',
        cvars: Array.isArray(p.cvars) ? p.cvars : [],
        commands: Array.isArray(p.commands) ? p.commands : [],
      }));
      setPlugins(draft);
      setSelectedIndex(draft.length ? 0 : -1);
      setFilename('qlsm-plugins.json');
    }
  }, [isOpen, repo]);

  const issues = useMemo(() => validateManifestPlugins(plugins), [plugins]);
  const { errors, warnings } = useMemo(() => issueCounts(issues), [issues]);
  const issuesByPlugin = useMemo(() => {
    const map = new Map();
    issues.forEach((iss) => {
      if (iss.index === undefined) return;
      const bucket = map.get(iss.index) || { errors: 0, warnings: 0 };
      if (iss.severity === 'error') bucket.errors += 1; else bucket.warnings += 1;
      map.set(iss.index, bucket);
    });
    return map;
  }, [issues]);

  const updatePlugin = (index, patch) => {
    setPlugins((prev) => prev.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  };
  const updateCvar = (pIndex, cIndex, patch) => {
    setPlugins((prev) => prev.map((p, i) => (i !== pIndex ? p : {
      ...p,
      cvars: p.cvars.map((c, j) => (j === cIndex ? { ...c, ...patch } : c)),
    })));
  };
  const updateCommand = (pIndex, cIndex, patch) => {
    setPlugins((prev) => prev.map((p, i) => (i !== pIndex ? p : {
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
  const addCvar = (pIndex) => updatePlugin(pIndex, { cvars: [...(plugins[pIndex].cvars || []), blankCvar()] });
  const removeCvar = (pIndex, cIndex) => updatePlugin(pIndex, { cvars: plugins[pIndex].cvars.filter((_, j) => j !== cIndex) });
  const addCommand = (pIndex) => updatePlugin(pIndex, { commands: [...(plugins[pIndex].commands || []), blankCommand()] });
  const removeCommand = (pIndex, cIndex) => updatePlugin(pIndex, { commands: plugins[pIndex].commands.filter((_, j) => j !== cIndex) });

  const handleDownload = () => {
    triggerManifestDownload(filename, plugins);
  };

  // Reordering (drag or Sort A-Z) moves plugins around in the array, so the
  // currently-selected row is tracked by its stable _key across the move and
  // selectedIndex is recomputed from where that key landed -- an index alone
  // would end up pointed at whatever plugin happened to slide into that slot.
  const reorderTo = (nextPlugins) => {
    const selectedKey = selectedIndex >= 0 ? plugins[selectedIndex]?._key : null;
    setPlugins(nextPlugins);
    if (selectedKey) {
      const nextIndex = nextPlugins.findIndex((p) => p._key === selectedKey);
      setSelectedIndex(nextIndex);
    }
  };

  const handleSortAlpha = () => {
    const sorted = [...plugins].sort((a, b) => (
      (a.label || a.filename || '').localeCompare(b.label || b.filename || '', undefined, { sensitivity: 'base' })
    ));
    reorderTo(sorted);
  };

  const [activeKey, setActiveKey] = useState(null);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );
  const itemKeys = useMemo(() => plugins.map((p) => p._key), [plugins]);
  const activePlugin = useMemo(
    () => (activeKey ? plugins.find((p) => p._key === activeKey) : null),
    [activeKey, plugins],
  );

  const handleDragStart = useCallback((event) => {
    setActiveKey(event.active.id);
  }, []);
  const handleDragEnd = useCallback((event) => {
    setActiveKey(null);
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = plugins.findIndex((p) => p._key === active.id);
    const newIndex = plugins.findIndex((p) => p._key === over.id);
    if (oldIndex === -1 || newIndex === -1) return;
    reorderTo(arrayMove(plugins, oldIndex, newIndex));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plugins, selectedIndex]);
  const handleDragCancel = useCallback(() => {
    setActiveKey(null);
  }, []);

  const selected = selectedIndex >= 0 ? plugins[selectedIndex] : null;

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
              Edits a local copy of this repository&apos;s plugin list. Download writes a new{' '}
              <code>qlsm-plugins.json</code> for you to commit to the repository itself — Sync always
              re-fetches from the source URL, so nothing here is saved by qlsm.
            </p>

            <div className="relative z-10 flex-1 min-h-0 grid grid-cols-1 md:grid-cols-[260px_1fr] gap-4">
              {/* Plugin list */}
              <div className="flex flex-col min-h-0 border border-[var(--surface-border)] rounded-lg overflow-hidden">
                <div className="flex-1 overflow-y-auto scrollbar-thin divide-y divide-[var(--surface-border)]">
                  <DndContext
                    sensors={sensors}
                    collisionDetection={closestCenter}
                    onDragStart={handleDragStart}
                    onDragEnd={handleDragEnd}
                    onDragCancel={handleDragCancel}
                  >
                    <SortableContext items={itemKeys} strategy={verticalListSortingStrategy}>
                      {plugins.map((p, i) => (
                        <SortablePluginRow
                          key={p._key}
                          plugin={p}
                          isSelected={i === selectedIndex}
                          errorBucket={issuesByPlugin.get(i)}
                          onSelect={() => setSelectedIndex(i)}
                          onRemove={() => removePlugin(i)}
                        />
                      ))}
                    </SortableContext>
                    <DragOverlay dropAnimation={null}>
                      {activePlugin ? <PluginRowOverlay plugin={activePlugin} /> : null}
                    </DragOverlay>
                  </DndContext>
                  {plugins.length === 0 && (
                    <p className="text-sm text-[var(--text-muted)] p-3">No plugins yet.</p>
                  )}
                </div>
                <div className="p-2 border-t border-[var(--surface-border)] flex-shrink-0 flex gap-2">
                  <button
                    type="button"
                    onClick={handleSortAlpha}
                    disabled={plugins.length < 2}
                    title="Sort plugins A to Z by label"
                    className="btn btn-secondary flex-1 justify-center !px-2"
                  >
                    <ArrowDownAZ className="w-4 h-4" />
                    Sort A–Z
                  </button>
                  <button type="button" onClick={addPlugin} className="btn btn-secondary flex-1 justify-center !px-2">
                    <Plus className="w-4 h-4" />
                    Add Plugin
                  </button>
                </div>
              </div>

              {/* Selected plugin editor */}
              <div className="flex flex-col min-h-0 overflow-y-auto scrollbar-thin pr-1">
                {!selected ? (
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

                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="label-tech">Cvars ({(selected.cvars || []).length})</span>
                        <button type="button" onClick={() => addCvar(selectedIndex)} className="btn btn-secondary !px-2.5 !py-1 !text-xs">
                          <Plus className="w-3.5 h-3.5" /> Add Cvar
                        </button>
                      </div>
                      <div className="space-y-2">
                        {(selected.cvars || []).map((c, j) => (
                          <div key={j} className="border border-[var(--surface-border)] rounded-lg p-3 space-y-2">
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                              <input
                                className="input-base font-mono text-xs" placeholder="cvar" value={c.cvar}
                                onChange={(e) => updateCvar(selectedIndex, j, { cvar: e.target.value })}
                              />
                              <input
                                className="input-base text-xs" placeholder="label" value={c.label}
                                onChange={(e) => updateCvar(selectedIndex, j, { label: e.target.value })}
                              />
                              <select
                                className="input-base text-xs" value={c.type}
                                onChange={(e) => updateCvar(selectedIndex, j, { type: e.target.value, default: defaultForCvarType(e.target.value) })}
                              >
                                <option value="string">string</option>
                                <option value="number">number</option>
                                <option value="bool">bool</option>
                              </select>
                              {c.type === 'bool' ? (
                                <label className="flex items-center gap-2 text-xs px-1">
                                  <input
                                    type="checkbox" checked={!!c.default}
                                    onChange={(e) => updateCvar(selectedIndex, j, { default: e.target.checked })}
                                  />
                                  default
                                </label>
                              ) : (
                                <input
                                  className="input-base font-mono text-xs"
                                  type={c.type === 'number' ? 'number' : 'text'}
                                  placeholder="default"
                                  value={c.default ?? ''}
                                  onChange={(e) => updateCvar(selectedIndex, j, {
                                    default: c.type === 'number' ? (e.target.value === '' ? '' : Number(e.target.value)) : e.target.value,
                                  })}
                                />
                              )}
                            </div>
                            <div className="flex gap-2 items-start">
                              <textarea
                                className="input-base text-xs flex-1" rows={1} placeholder="description" value={c.description}
                                onChange={(e) => updateCvar(selectedIndex, j, { description: e.target.value })}
                              />
                              <button type="button" onClick={() => removeCvar(selectedIndex, j)} className="btn btn-secondary !px-2 !py-1 flex-shrink-0">
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </div>
                        ))}
                        {(selected.cvars || []).length === 0 && (
                          <p className="text-xs text-[var(--text-muted)]">No cvars.</p>
                        )}
                      </div>
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="label-tech">Commands ({(selected.commands || []).length})</span>
                        <button type="button" onClick={() => addCommand(selectedIndex)} className="btn btn-secondary !px-2.5 !py-1 !text-xs">
                          <Plus className="w-3.5 h-3.5" /> Add Command
                        </button>
                      </div>
                      <div className="space-y-2">
                        {(selected.commands || []).map((c, j) => (
                          <div key={j} className="border border-[var(--surface-border)] rounded-lg p-3 space-y-2">
                            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                              <input
                                className="input-base font-mono text-xs" placeholder="name" value={c.name}
                                onChange={(e) => updateCommand(selectedIndex, j, { name: e.target.value })}
                              />
                              <input
                                className="input-base font-mono text-xs" placeholder="usage" value={c.usage || ''}
                                onChange={(e) => updateCommand(selectedIndex, j, { usage: e.target.value })}
                              />
                              <input
                                className="input-base font-mono text-xs" type="number" min={0} max={5} placeholder="permission"
                                value={c.permission ?? ''}
                                onChange={(e) => updateCommand(selectedIndex, j, {
                                  permission: e.target.value === '' ? undefined : Number(e.target.value),
                                })}
                              />
                            </div>
                            <div className="flex gap-2 items-start">
                              <textarea
                                className="input-base text-xs flex-1" rows={1} placeholder="description" value={c.description}
                                onChange={(e) => updateCommand(selectedIndex, j, { description: e.target.value })}
                              />
                              <button type="button" onClick={() => removeCommand(selectedIndex, j)} className="btn btn-secondary !px-2 !py-1 flex-shrink-0">
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </div>
                        ))}
                        {(selected.commands || []).length === 0 && (
                          <p className="text-xs text-[var(--text-muted)]">No commands.</p>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>

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
