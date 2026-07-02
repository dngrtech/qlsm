import React, { useEffect, useRef, useState } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { FolderOpen, LayoutGrid, LoaderCircle, Save } from 'lucide-react';
import { classNames } from '../../utils/uiUtils';
import { deletePreset, importPreset, updatePreset } from '../../services/api';
import { triggerPresetDownload } from '../../utils/presetDownload';
import ConfirmationModal from '../ConfirmationModal';
import PresetImportPanel from './PresetImportPanel';
import PresetLoadTab from './PresetLoadTab';
import PresetRenameModal from './PresetRenameModal';
import PresetSaveTab from './PresetSaveTab';

const TABS = [
  { key: 'load', icon: FolderOpen, label: 'Load Preset' },
  { key: 'save', icon: Save, label: 'Save / Overwrite' },
];

function PresetManagerModal({
  isOpen,
  onClose,
  initialTab = 'load',
  zIndexClass = 'z-[60]',
  presets = [],
  isLoading = false,
  onLoadPreset,
  isLoadingPreset = false,
  onSavePreset,
  onOverwritePreset,
  isSaving = false,
  savedPreset = null,
  onPresetDeleted,
  onPresetRenamed,
  onPresetImported,
  initialOverwriteName = null,
}) {
  const [activeTab, setActiveTab] = useState(initialTab);
  const [selectedId, setSelectedId] = useState(null);
  const [downloadingId, setDownloadingId] = useState(null);
  const [isDownloadingSaved, setIsDownloadingSaved] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleteError, setDeleteError] = useState(null);
  const [downloadError, setDownloadError] = useState(null);
  const [showLoadConfirm, setShowLoadConfirm] = useState(false);
  const [pendingRename, setPendingRename] = useState(null);
  const [renameError, setRenameError] = useState(null);
  const [isRenaming, setIsRenaming] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [importConflict, setImportConflict] = useState(null);
  const [importError, setImportError] = useState(null);
  const [importedPresetPreview, setImportedPresetPreview] = useState(null);
  const pendingImportFileRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      setActiveTab(initialTab);
      setSelectedId(null);
      setPendingDelete(null);
      setDeleteError(null);
      setDownloadError(null);
      setShowLoadConfirm(false);
      setPendingRename(null);
      setRenameError(null);
      setIsRenaming(false);
      setIsImporting(false); setImportConflict(null);
      setImportError(null); setImportedPresetPreview(null);
      pendingImportFileRef.current = null;
    }
  }, [isOpen, initialTab]);

  const selectedPreset = presets.find((p) => p.id === selectedId) || (importedPresetPreview?.id === selectedId ? importedPresetPreview : null);

  const handleDownload = async (preset) => {
    setDownloadingId(preset.id);
    setDownloadError(null);
    try {
      await triggerPresetDownload(preset);
    } catch (err) {
      setDownloadError(`Failed to download "${preset.name}": ${err.error?.message || err.message || 'Unknown error.'}`);
    } finally {
      setDownloadingId(null);
    }
  };

  const handleDownloadSaved = async (preset) => {
    setIsDownloadingSaved(true);
    setDownloadError(null);
    try {
      await triggerPresetDownload(preset);
    } catch (err) {
      setDownloadError(`Failed to download "${preset.name}": ${err.error?.message || err.message || 'Unknown error.'}`);
    } finally {
      setIsDownloadingSaved(false);
    }
  };

  const handleConfirmDelete = async () => {
    const target = pendingDelete;
    if (!target) return;
    setDeleteError(null);
    try {
      await deletePreset(target.id);
      if (selectedId === target.id) setSelectedId(null);
      onPresetDeleted?.(target.id);
    } catch (err) {
      setDeleteError(
        `Failed to delete "${target.name}": ${err.error?.message || err.message || 'Unknown error.'}`
      );
    }
  };

  const handleConfirmLoad = () => {
    setShowLoadConfirm(false);
    if (selectedId != null) onLoadPreset(selectedId);
  };

  const handleConfirmRename = async (newName) => {
    const target = pendingRename;
    if (!target) return;
    setRenameError(null);
    setIsRenaming(true);
    try {
      await updatePreset(target.id, { name: newName });
      onPresetRenamed?.(target.id, newName);
      setPendingRename(null);
    } catch (err) {
      setRenameError(err.error?.message || err.message || 'Failed to rename preset.');
    } finally {
      setIsRenaming(false);
    }
  };

  const runImport = async (options = {}) => {
    const file = pendingImportFileRef.current;
    if (!file) return;
    setIsImporting(true);
    setImportError(null);
    try {
      const result = await importPreset(file, options);
      const imported = result.data;
      setImportConflict(null); pendingImportFileRef.current = null;
      setImportedPresetPreview(imported);
      onPresetImported?.(imported);
      setSelectedId(imported.id); setShowLoadConfirm(true);
    } catch (err) {
      if (err?.conflict) {
        setImportConflict(err.conflict);
      } else {
        setImportError(err.error?.message || err.message || 'Failed to import preset.');
      }
    } finally {
      setIsImporting(false);
    }
  };

  const handleImportFile = (file) => {
    pendingImportFileRef.current = file; setImportConflict(null);
    runImport();
  };

  const handleResolveImportConflict = ({ overwrite, newName }) => {
    runImport(overwrite
      ? { overwritePresetId: importConflict.preset_id }
      : { name: newName });
  };

  const handleCancelImportConflict = () => {
    setImportConflict(null); setImportError(null); pendingImportFileRef.current = null;
  };

  return (
    <>
      <Dialog open={isOpen} as="div" className={classNames('relative', zIndexClass)} onClose={onClose}>
        <DialogBackdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0" />
        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4 text-center">
            <Dialog.Panel transition className="modal-panel w-full max-w-xl transform p-0 text-left align-middle transition-all data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:scale-95">
              <div className="accent-line-top" />
              <Dialog.Title as="h3" className="relative z-10 flex items-center gap-3 px-6 pb-3 pt-5">
                <LayoutGrid className="h-5 w-5 text-[var(--accent-primary)]" />
                <span className="font-display text-lg font-semibold uppercase tracking-wider text-[var(--text-primary)]">
                  Preset Manager
                </span>
              </Dialog.Title>

              <div className="relative z-10 flex border-y border-[var(--surface-border)] bg-[var(--surface-elevated)]">
                {TABS.map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    onClick={() => setActiveTab(tab.key)}
                    className={classNames(
                      'flex items-center gap-2 px-6 py-3 text-[13px] font-display font-semibold uppercase tracking-wide border-b-2 transition-all duration-200',
                      activeTab === tab.key
                        ? 'border-b-[var(--accent-primary)] text-[var(--accent-primary)] bg-[var(--accent-primary)]/5'
                        : 'border-b-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-base)]/50'
                    )}
                  >
                    {React.createElement(tab.icon, { size: 16 })}
                    {tab.label}
                  </button>
                ))}
              </div>

              <div className="relative z-10 flex min-h-[27rem] flex-col p-6">
                {activeTab === 'load' ? (
                  <>
                    <div className="flex-1">
                      <PresetImportPanel
                        conflict={importConflict}
                        isImporting={isImporting}
                        error={importError}
                        onImportFile={handleImportFile}
                        onResolveConflict={handleResolveImportConflict}
                        onCancelConflict={handleCancelImportConflict}
                      />
                      <PresetLoadTab
                        presets={presets}
                        isLoading={isLoading}
                        selectedId={selectedId}
                        onSelect={setSelectedId}
                        onRequestDelete={(p) => { setDeleteError(null); setPendingDelete(p); }}
                        onRequestRename={(p) => { setRenameError(null); setPendingRename(p); }}
                        onDownload={handleDownload}
                        downloadingId={downloadingId}
                      />
                      {deleteError && (
                        <p role="alert" className="mt-3 rounded-md border border-[var(--accent-danger)]/35 bg-[var(--accent-danger)]/10 px-3 py-2 text-sm text-[var(--accent-danger)]">
                          {deleteError}
                        </p>
                      )}
                      {downloadError && (
                        <p role="alert" className="mt-3 rounded-md border border-[var(--accent-danger)]/35 bg-[var(--accent-danger)]/10 px-3 py-2 text-sm text-[var(--accent-danger)]">
                          {downloadError}
                        </p>
                      )}
                    </div>
                    <div className="mt-auto flex items-center justify-end gap-3 pt-6">
                      <button type="button" className="btn btn-secondary" onClick={onClose}>Cancel</button>
                      <button
                        type="button"
                        className="btn btn-primary"
                        disabled={selectedId == null || isLoadingPreset}
                        onClick={() => setShowLoadConfirm(true)}
                      >
                        {isLoadingPreset
                          ? <><LoaderCircle className="mr-1 h-4 w-4 animate-spin" />Loading...</>
                          : <><FolderOpen className="mr-1 h-4 w-4" />Load Selected</>}
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <PresetSaveTab
                      key={`${isOpen ? 'open' : 'closed'}-${initialOverwriteName || 'new'}`}
                      presets={presets}
                      initialOverwriteName={initialOverwriteName}
                      onSavePreset={onSavePreset}
                      onOverwritePreset={onOverwritePreset}
                      isSaving={isSaving}
                      savedPreset={savedPreset}
                      onDownloadSaved={handleDownloadSaved}
                      isDownloadingSaved={isDownloadingSaved}
                      onCancel={onClose}
                    />
                    {downloadError && (
                      <p role="alert" className="mt-3 rounded-md border border-[var(--accent-danger)]/35 bg-[var(--accent-danger)]/10 px-3 py-2 text-sm text-[var(--accent-danger)]">
                        {downloadError}
                      </p>
                    )}
                  </>
                )}
              </div>
            </Dialog.Panel>
          </div>
        </div>
      </Dialog>

      <ConfirmationModal
        isOpen={Boolean(pendingDelete)}
        onClose={() => setPendingDelete(null)}
        onConfirm={handleConfirmDelete}
        title="Delete Preset"
        message={`Are you sure you want to delete the preset "${pendingDelete?.name}"? This action cannot be undone.`}
        confirmButtonText="Delete"
        cancelButtonText="Cancel"
        confirmButtonVariant="danger"
        zIndexClass="z-[70]"
      />

      <PresetRenameModal
        isOpen={Boolean(pendingRename)}
        onClose={() => { setPendingRename(null); setRenameError(null); }}
        onRename={handleConfirmRename}
        currentName={pendingRename?.name || ''}
        existingNames={presets.map((p) => p.name)}
        isSaving={isRenaming}
        error={renameError}
      />

      <ConfirmationModal
        isOpen={showLoadConfirm}
        onClose={() => setShowLoadConfirm(false)}
        onConfirm={handleConfirmLoad}
        title="Confirm Load Preset"
        message={`Loading "${selectedPreset?.name}" will overwrite your current configuration changes. Continue?`}
        confirmButtonText="Load Preset"
        cancelButtonText="Keep Editing"
        confirmButtonVariant="primary"
        zIndexClass="z-[70]"
      />
    </>
  );
}

export default PresetManagerModal;
