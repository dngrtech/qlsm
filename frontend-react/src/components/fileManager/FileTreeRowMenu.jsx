import { Fragment, useRef } from 'react';
import { Menu, Transition } from '@headlessui/react';
import { Copy, Download, FilePlus, MoreVertical, Pencil, Trash2, Upload } from 'lucide-react';

export default function FileTreeRowMenu({
  itemType,
  isProtected = false,
  capabilities = {},
  onDownload,
  onCopyContent,
  onRename,
  onDelete,
  onNewFileInFolder,
  onUploadToFolder,
}) {
  const fileInputRef = useRef(null);
  const isFolder = itemType === 'folder';

  if (isFolder && !capabilities.canCreateFolder) return null;

  const items = isFolder
    ? [
        { key: 'new-file', label: 'New File', icon: FilePlus, onClick: onNewFileInFolder },
        { key: 'upload', label: 'Upload', icon: Upload, onClick: () => fileInputRef.current?.click() },
        { key: 'rename', label: 'Rename', icon: Pencil, onClick: onRename },
        { key: 'delete', label: 'Delete', icon: Trash2, onClick: onDelete, danger: true },
      ]
    : [
        { key: 'download', label: 'Download', icon: Download, onClick: onDownload },
        { key: 'copy', label: 'Copy Content', icon: Copy, onClick: onCopyContent },
        { key: 'rename', label: 'Rename', icon: Pencil, onClick: onRename, disabled: isProtected, disabledTitle: 'Built-in file, cannot be renamed' },
        { key: 'delete', label: 'Delete', icon: Trash2, onClick: onDelete, danger: true, disabled: isProtected, disabledTitle: 'Built-in file, cannot be deleted' },
      ];

  return (
    <>
      <Menu as="div" className="relative">
        <Menu.Button
          className="opacity-0 group-hover:opacity-100 data-[open]:opacity-100 p-1 rounded hover:bg-[var(--surface-base)]"
          onClick={(e) => e.stopPropagation()}
          aria-label={`${itemType} actions`}
        >
          <MoreVertical className="w-3.5 h-3.5 text-[var(--text-muted)]" />
        </Menu.Button>
        <Transition as={Fragment}
          enter="transition ease-out duration-100"
          enterFrom="transform opacity-0 scale-95"
          enterTo="transform opacity-100 scale-100"
          leave="transition ease-in duration-75"
          leaveFrom="transform opacity-100 scale-100"
          leaveTo="transform opacity-0 scale-95"
        >
          <Menu.Items className="absolute right-0 mt-1 w-44 origin-top-right rounded-md bg-[var(--surface-elevated)] border border-[var(--surface-border)] shadow-lg focus:outline-none z-50">
            <div className="py-1">
              {items.map(item => (
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
                      className={`${active ? 'bg-black/10 dark:bg-white/10' : ''} ${disabled ? 'opacity-40 cursor-not-allowed' : ''} ${item.danger ? 'text-[var(--accent-danger)]' : 'text-[var(--text-secondary)]'} flex w-full items-center gap-2 px-3 py-1.5 text-xs`}
                    >
                      <item.icon className="w-3.5 h-3.5" /> {item.label}
                    </button>
                  )}
                </Menu.Item>
              ))}
            </div>
          </Menu.Items>
        </Transition>
      </Menu>
      {isFolder && (
        <input
          type="file"
          multiple
          ref={fileInputRef}
          className="hidden"
          accept={(capabilities.allowedExtensions || []).join(',')}
          onChange={(e) => {
            if (e.target.files.length && onUploadToFolder) onUploadToFolder(Array.from(e.target.files));
            e.target.value = '';
          }}
        />
      )}
    </>
  );
}
