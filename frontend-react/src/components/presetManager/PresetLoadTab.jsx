import React from 'react';
import { Menu } from '@headlessui/react';
import { Download, LoaderCircle, MoreVertical, Pencil, Trash2 } from 'lucide-react';
import { classNames } from '../../utils/uiUtils';

function PresetRowMenu({ preset, onDownload, onRename, onRequestDelete, isDownloading, boundaryRef }) {
  const buttonRef = React.useRef(null);
  const [placement, setPlacement] = React.useState('bottom end');

  const updatePlacement = () => {
    const btn = buttonRef.current;
    if (!btn) return;
    const btnRect = btn.getBoundingClientRect();
    // Approx menu height: 3 items (~30px each) + vertical padding.
    const estimatedMenuHeight = 3 * 30 + 8;
    const bottomLimit = boundaryRef?.current
      ? boundaryRef.current.getBoundingClientRect().bottom
      : window.innerHeight;
    const spaceBelow = bottomLimit - btnRect.bottom;
    setPlacement(spaceBelow < estimatedMenuHeight ? 'top end' : 'bottom end');
  };

  const items = [
    {
      key: 'download',
      label: 'Download',
      icon: isDownloading ? LoaderCircle : Download,
      iconClass: isDownloading ? 'animate-spin' : '',
      onClick: () => onDownload(preset),
      disabled: isDownloading || preset.is_builtin,
      disabledTitle: preset.is_builtin ? 'Cannot download a built-in preset' : undefined,
    },
    {
      key: 'rename',
      label: 'Rename',
      icon: Pencil,
      onClick: () => onRename(preset),
      disabled: preset.is_builtin,
      disabledTitle: 'Cannot rename a built-in preset',
    },
    {
      key: 'delete',
      label: 'Delete',
      icon: Trash2,
      onClick: () => onRequestDelete(preset),
      danger: true,
      disabled: preset.is_builtin,
      disabledTitle: 'Cannot delete a built-in preset',
    },
  ];

  return (
    <Menu as="div" className="relative">
      <Menu.Button
        ref={buttonRef}
        className="p-1 rounded text-[var(--text-muted)] hover:bg-[var(--surface-base)] hover:text-[var(--text-primary)] data-[open]:bg-[var(--surface-base)]"
        onPointerDown={updatePlacement}
        onClick={(e) => e.stopPropagation()}
        aria-label={`${preset.name} actions`}
      >
        <MoreVertical className="h-3.5 w-3.5" />
      </Menu.Button>
      <Menu.Items
        transition
        anchor={{ to: placement, gap: 4 }}
        className={classNames(
          'w-44 rounded-md bg-[var(--surface-elevated)] border border-[var(--surface-border)] shadow-lg focus:outline-none z-50',
          'origin-top data-[anchor~=top]:origin-bottom transition ease-out',
          'data-[closed]:scale-95 data-[closed]:opacity-0',
          'data-[enter]:duration-100 data-[leave]:duration-75 data-[leave]:ease-in'
        )}
      >
        <div className="py-1">
            {items.map((item) => (
              <Menu.Item key={item.key} disabled={item.disabled}>
                {({ active, disabled }) => (
                  <button
                    type="button"
                    disabled={disabled}
                    title={disabled ? item.disabledTitle : undefined}
                    onClick={(e) => {
                      e.stopPropagation();
                      item.onClick?.();
                    }}
                    className={classNames(
                      'flex w-full items-center gap-2 px-3 py-1.5 text-xs',
                      active ? 'bg-black/10 dark:bg-white/10' : '',
                      disabled ? 'opacity-40 cursor-not-allowed' : '',
                      item.danger ? 'text-[var(--accent-danger)]' : 'text-[var(--text-secondary)]'
                    )}
                  >
                    <item.icon className={classNames('h-3.5 w-3.5', item.iconClass)} /> {item.label}
                  </button>
                )}
              </Menu.Item>
            ))}
        </div>
      </Menu.Items>
    </Menu>
  );
}

function PresetLoadTab({
  presets = [],
  isLoading = false,
  selectedId = null,
  onSelect,
  onRequestDelete,
  onRequestRename,
  onDownload,
  downloadingId = null,
}) {
  const listRef = React.useRef(null);
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
    <div ref={listRef} className="max-h-[20rem] overflow-y-auto rounded-md border border-[var(--surface-border)] scrollbar-thin">
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
            <div>
              <PresetRowMenu
                preset={preset}
                onDownload={onDownload}
                onRename={onRequestRename}
                onRequestDelete={onRequestDelete}
                isDownloading={downloadingId === preset.id}
                boundaryRef={listRef}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default PresetLoadTab;
