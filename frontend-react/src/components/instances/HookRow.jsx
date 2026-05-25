import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { GripVertical, Info } from 'lucide-react';

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function HookRowContent({ hook, onToggle, dragHandleProps = null, style = undefined, readOnly = false }) {
  return (
    <div
      style={style}
      className={`flex min-h-10 items-center gap-3 border-b border-[var(--surface-border)] px-3 py-2${readOnly ? '' : ' hover:bg-[var(--surface-hover)]'}`}
      data-testid={`hook-row-${hook.filename}`}
    >
      {!readOnly && (dragHandleProps ? (
        <button
          type="button"
          {...dragHandleProps.attributes}
          {...dragHandleProps.listeners}
          className="flex h-7 w-7 items-center justify-center rounded text-[var(--text-muted)] hover:bg-[var(--surface-elevated)]"
          aria-label={`Reorder ${hook.filename}`}
        >
          <GripVertical size={16} />
        </button>
      ) : (
        <span className="h-7 w-7" />
      ))}
      {readOnly && <span className="h-7 w-7" />}
      <input
        type="checkbox"
        checked={hook.enabled}
        onChange={readOnly ? undefined : () => onToggle(hook.filename)}
        disabled={readOnly}
        className={`h-4 w-4 ${readOnly ? 'cursor-default opacity-75' : 'cursor-pointer'}`}
        aria-label={`Enable ${hook.filename}`}
      />
      <span className="min-w-0 flex-1 truncate font-mono text-sm text-[var(--text-primary)]">
        {hook.filename}
      </span>
      <span className="w-20 text-right font-mono text-xs text-[var(--text-muted)]">
        {formatSize(hook.size)}
      </span>
      {hook.description ? (
        <span title={hook.description} className="text-[var(--text-muted)]">
          <Info size={14} />
        </span>
      ) : (
        <span className="w-3.5" />
      )}
    </div>
  );
}

export function SortableHookRow({ hook, onToggle }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: hook.filename,
  });
  const style = {
    opacity: isDragging ? 0.6 : 1,
    transform: CSS.Transform.toString(transform),
    transition,
  };
  return (
    <div ref={setNodeRef}>
      <HookRowContent
        hook={hook}
        onToggle={onToggle}
        dragHandleProps={{ attributes, listeners }}
        style={style}
      />
    </div>
  );
}

export function ReadOnlyHookRow({ hook }) {
  return <HookRowContent hook={{ ...hook, enabled: true }} readOnly />;
}

export default function HookRow({ hook, onToggle }) {
  return <HookRowContent hook={hook} onToggle={onToggle} />;
}
