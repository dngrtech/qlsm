import { Plus, Trash2 } from 'lucide-react';

/**
 * The manifest editor's left pane on the Addons tab: one row per addon entry
 * plus Add Addon. Same select/remove row shape as PluginManifestPluginList,
 * without the reordering -- an addon's position in the list changes nothing
 * qlsm does with it.
 */
function PluginManifestAddonList({
  addons, selectedIndex, issuesByAddon, onSelect, onRemove, onAdd,
}) {
  return (
    <div className="flex flex-col min-h-0 flex-1 border border-[var(--surface-border)] rounded-lg overflow-hidden">
      <div className="flex-1 overflow-y-auto scrollbar-thin divide-y divide-[var(--surface-border)]">
        {addons.map((a, i) => {
          const bucket = issuesByAddon.get(i);
          const displayName = a.label || a.id || 'addon';
          return (
            <div
              key={a._key}
              className={`flex items-center gap-1 px-2 py-2 text-sm transition-colors ${
                i === selectedIndex ? 'bg-black/[0.05] dark:bg-white/[0.06]' : 'hover:bg-black/[0.03] dark:hover:bg-white/[0.03]'
              }`}
            >
              <button type="button" onClick={() => onSelect(i)} className="flex items-center gap-2 min-w-0 flex-1 text-left pl-1">
                <span
                  className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                    bucket?.errors ? 'bg-red-500' : bucket?.warnings ? 'bg-amber-500' : 'bg-emerald-500'
                  }`}
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[var(--text-primary)]">{a.label || a.id || '(untitled)'}</span>
                  <span className="block truncate font-mono text-[11px] text-[var(--text-muted)]">{a.zip || '—'}</span>
                </span>
              </button>
              <button
                type="button"
                onClick={() => onRemove(i)}
                aria-label={`Remove ${displayName}`}
                className="p-1 rounded text-slate-500 hover:text-red-400 hover:bg-red-500/10 flex-shrink-0"
              >
                <Trash2 size={13} />
              </button>
            </div>
          );
        })}
        {addons.length === 0 && (
          <p className="text-sm text-[var(--text-muted)] p-3">No addons yet.</p>
        )}
      </div>
      <div className="p-2 border-t border-[var(--surface-border)] flex-shrink-0">
        <button type="button" onClick={onAdd} className="btn btn-secondary w-full justify-center !px-2">
          <Plus className="w-4 h-4" />
          Add Addon
        </button>
      </div>
    </div>
  );
}

export default PluginManifestAddonList;
