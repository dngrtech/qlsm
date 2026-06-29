import React from 'react';
import { Download, LoaderCircle, Trash2 } from 'lucide-react';
import { classNames } from '../../utils/uiUtils';

function PresetLoadTab({
  presets = [],
  isLoading = false,
  selectedId = null,
  onSelect,
  onRequestDelete,
  onDownload,
  downloadingId = null,
}) {
  if (isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 py-10 text-sm text-[var(--text-muted)]">
        <LoaderCircle className="h-4 w-4 animate-spin" /> Loading presets...
      </div>
    );
  }
  if (presets.length === 0) {
    return <p className="py-10 text-center text-sm italic text-[var(--text-muted)]">No presets available.</p>;
  }

  return (
    <div className="max-h-[20rem] overflow-y-auto rounded-md border border-[var(--surface-border)] scrollbar-thin">
      {presets.map((preset) => {
        const selected = preset.id === selectedId;
        return (
          <div
            key={preset.id}
            onClick={() => onSelect(preset.id)}
            className={classNames(
              'group flex cursor-pointer items-center gap-3 border-b border-[var(--surface-border)] px-3.5 py-2.5 last:border-b-0 transition-colors',
              selected
                ? 'bg-[var(--accent-primary)]/10 shadow-[inset_2px_0_0_var(--accent-primary)]'
                : 'hover:bg-[var(--surface-elevated)]'
            )}
          >
            <div className="min-w-0 flex-1">
              <div className={classNames('truncate text-sm font-semibold', selected ? 'text-[var(--accent-primary)]' : 'text-[var(--text-primary)]')}>
                {preset.name}
              </div>
              <div className="mt-0.5 truncate text-xs text-[var(--text-muted)]">
                {preset.description || 'No description'}
              </div>
            </div>
            <div className={classNames('flex items-center gap-1.5 transition-opacity', selected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100')}>
              <button
                type="button"
                aria-label={`Download ${preset.name}`}
                onClick={(e) => { e.stopPropagation(); onDownload(preset); }}
                disabled={downloadingId === preset.id}
                className="rounded border border-[var(--surface-border)] p-1.5 text-[var(--text-muted)] hover:border-[var(--accent-primary)] hover:text-[var(--accent-primary)]"
              >
                {downloadingId === preset.id
                  ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
                  : <Download className="h-3.5 w-3.5" />}
              </button>
              <button
                type="button"
                aria-label={`Delete ${preset.name}`}
                onClick={(e) => { e.stopPropagation(); onRequestDelete(preset); }}
                disabled={preset.is_builtin}
                title={preset.is_builtin ? 'Cannot delete a built-in preset' : 'Delete preset'}
                className="rounded border border-[var(--surface-border)] p-1.5 text-[var(--text-muted)] enabled:hover:border-[var(--accent-danger)] enabled:hover:text-[var(--accent-danger)] disabled:opacity-40"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default PresetLoadTab;
