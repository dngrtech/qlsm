import { useState } from 'react';
import { Check, Pencil, X } from 'lucide-react';
import { setInstanceHookDescription } from '../../services/api';

export function DescriptionText({ description }) {
  if (!description) {
    return <em className="block truncate text-[var(--text-muted)] opacity-75">No description</em>;
  }
  return <span className="block truncate">{description}</span>;
}

export default function HookDescriptionCell({ hook, instanceId, onChanged, readOnly }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(hook.description || '');
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await setInstanceHookDescription(instanceId, hook.filename, value);
      setEditing(false);
      onChanged?.();
    } finally {
      setSaving(false);
    }
  };

  if (readOnly) {
    return (
      <span className="min-w-0 truncate text-sm text-[var(--text-secondary)]">
        <DescriptionText description={hook.description} />
      </span>
    );
  }

  if (!editing) {
    return (
      <span className="flex min-w-0 items-center gap-2 text-sm text-[var(--text-secondary)]">
        <DescriptionText description={hook.description} />
        <button
          type="button"
          aria-label={`Edit description for ${hook.filename}`}
          onClick={() => setEditing(true)}
          className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded text-[var(--text-muted)] opacity-0 transition-opacity hover:bg-[var(--surface-elevated)] focus:opacity-100 group-hover:opacity-100"
        >
          <Pencil size={12} />
        </button>
      </span>
    );
  }

  return (
    <span className="flex min-w-0 flex-1 items-center gap-1">
      <input
        type="text"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') save();
          if (e.key === 'Escape') { setEditing(false); setValue(hook.description || ''); }
        }}
        autoFocus
        disabled={saving}
        className="min-w-0 flex-1 rounded border border-[var(--surface-border)] bg-[var(--surface-raised)] px-2 py-1 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-primary)]"
      />
      <button type="button" onClick={save} disabled={saving} aria-label="Save description" className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded text-[var(--accent-primary)] hover:bg-[var(--surface-elevated)]">
        <Check size={12} />
      </button>
      <button
        type="button"
        onClick={() => { setEditing(false); setValue(hook.description || ''); }}
        disabled={saving}
        aria-label="Cancel description"
        className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded text-[var(--text-muted)] hover:bg-[var(--surface-elevated)]"
      >
        <X size={12} />
      </button>
    </span>
  );
}
