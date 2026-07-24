import { Fragment } from 'react';
import { Menu, Transition } from '@headlessui/react';
import { ChevronDown, FilePlus, FolderPlus, Plus, Upload } from 'lucide-react';

export default function FileSidebarActions({
  capabilities,
  onNewFile,
  onNewFolder,
  onUpload,
}) {
  const {
    canCreate,
    canUpload,
    canCreateFolder,
    allowedExtensions,
  } = capabilities;

  if (!canCreate && !canUpload) return null;

  return (
    <div className="flex-shrink-0 border-t border-[var(--surface-border)] p-2">
      <div className="grid grid-cols-2 gap-2">
        {canCreate && (
          <Menu as="div" className="relative">
            <Menu.Button className="w-full flex items-center justify-center gap-1 px-3 py-1.5 bg-[var(--surface-elevated)] hover:bg-[var(--surface-elevated)]/80 text-[var(--text-secondary)] rounded text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--surface-border-strong)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--surface-base)]">
              <Plus className="w-3.5 h-3.5" /> New
              <ChevronDown className="w-3 h-3" />
            </Menu.Button>
            <Transition as={Fragment}
              enter="transition ease-out duration-100"
              enterFrom="transform opacity-0 scale-95"
              enterTo="transform opacity-100 scale-100"
              leave="transition ease-in duration-75"
              leaveFrom="transform opacity-100 scale-100"
              leaveTo="transform opacity-0 scale-95"
            >
              <Menu.Items className="absolute left-0 bottom-full mb-1 w-44 origin-bottom-left rounded-md bg-[var(--surface-elevated)] border border-[var(--surface-border)] shadow-lg focus:outline-none z-50">
                <div className="py-1">
                  <Menu.Item>
                    {({ active }) => (
                      <button
                        type="button"
                        onClick={onNewFile}
                        className={`${active ? 'bg-black/10 dark:bg-white/10' : ''} flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[var(--text-secondary)]`}
                      >
                        <FilePlus className="w-3.5 h-3.5" /> New File
                      </button>
                    )}
                  </Menu.Item>
                  <Menu.Item disabled={!canCreateFolder}>
                    {({ active, disabled }) => (
                      <button
                        type="button"
                        onClick={onNewFolder}
                        disabled={disabled}
                        title={disabled ? 'Folders are not supported here' : 'Create a new folder'}
                        className={`${active ? 'bg-black/10 dark:bg-white/10' : ''} ${disabled ? 'opacity-40 cursor-not-allowed' : ''} flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[var(--text-secondary)]`}
                      >
                        <FolderPlus className="w-3.5 h-3.5" /> New Folder
                      </button>
                    )}
                  </Menu.Item>
                </div>
              </Menu.Items>
            </Transition>
          </Menu>
        )}
        {canUpload && (
          <label className="flex items-center justify-center gap-1 px-3 py-1.5 bg-[var(--surface-elevated)] hover:bg-[var(--surface-elevated)]/80 text-[var(--text-secondary)] rounded text-xs cursor-pointer">
            <Upload className="w-3.5 h-3.5" /> Upload
            <input
              type="file"
              multiple
              accept={allowedExtensions.join(',')}
              className="hidden"
              onChange={(e) => {
                if (e.target.files.length) onUpload(Array.from(e.target.files));
                e.target.value = '';
              }}
            />
          </label>
        )}
      </div>
    </div>
  );
}
