import React, { useRef, useState } from 'react';
import { AlertTriangle, LoaderCircle, Upload } from 'lucide-react';

const PRESET_NAME_PATTERN = /^[a-zA-Z0-9_-]+$/;

function validateNameLocally(value) {
  if (!value.trim()) return null;
  if (!PRESET_NAME_PATTERN.test(value.trim())) {
    return 'Letters, numbers, hyphens, and underscores only.';
  }
  if (value.trim().toLowerCase() === 'default') return '"default" is a reserved preset name.';
  return null;
}

function PresetImportPanel({
  conflict = null,
  isImporting = false,
  error = null,
  onImportFile,
  onResolveConflict,
  onCancelConflict,
}) {
  const inputRef = useRef(null);
  const [newName, setNewName] = useState('');

  const nameError = validateNameLocally(newName);

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setNewName('');
    onImportFile(file);
  };

  if (conflict) {
    const isDuplicate = conflict.type === 'duplicate';
    return (
      <div className="mb-3 rounded-md border border-[var(--accent-warning)]/35 bg-[var(--accent-warning)]/8 px-3 py-3 text-xs">
        <div className="flex items-start gap-2 text-[var(--accent-warning)]">
          <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
          <span>
            {isDuplicate
              ? <>A preset named <b>{conflict.name}</b> already exists. Overwrite it, or import under a new name.</>
              : <>The preset name <b>{conflict.name}</b> can&apos;t be used. Choose a new name to import it.</>}
          </span>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <input
            type="text"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="New preset name"
            aria-label="New preset name"
            className="input-base h-8 flex-1 text-xs"
            disabled={isImporting}
          />
          <button
            type="button"
            className="btn btn-primary h-8 px-3 text-xs"
            disabled={isImporting || !newName.trim() || Boolean(nameError)}
            onClick={() => onResolveConflict({ overwrite: false, newName: newName.trim() })}
          >
            Import as new
          </button>
        </div>
        {nameError && <p className="mt-1 text-[var(--accent-danger)]">{nameError}</p>}
        <div className="mt-2 flex items-center justify-between">
          {isDuplicate ? (
            <button
              type="button"
              className="btn btn-caution h-8 px-3 text-xs"
              disabled={isImporting}
              onClick={() => onResolveConflict({ overwrite: true })}
            >
              {isImporting && <LoaderCircle className="mr-1 h-3.5 w-3.5 animate-spin" />}
              Overwrite &quot;{conflict.name}&quot;
            </button>
          ) : <span />}
          <button
            type="button"
            className="text-xs underline text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            onClick={onCancelConflict}
            disabled={isImporting}
          >
            Cancel import
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="mb-3">
      <input
        ref={inputRef}
        type="file"
        accept=".zip,application/zip"
        className="hidden"
        onChange={handleFileChange}
      />
      <button
        type="button"
        className="btn btn-secondary w-full"
        onClick={() => inputRef.current?.click()}
        disabled={isImporting}
      >
        {isImporting
          ? <><LoaderCircle className="mr-1 h-4 w-4 animate-spin" />Importing...</>
          : <><Upload className="mr-1 h-4 w-4" />Import from ZIP</>}
      </button>
      {error && (
        <p role="alert" className="mt-2 rounded-md border border-[var(--accent-danger)]/35 bg-[var(--accent-danger)]/10 px-3 py-2 text-sm text-[var(--accent-danger)]">
          {error}
        </p>
      )}
    </div>
  );
}

export default PresetImportPanel;
