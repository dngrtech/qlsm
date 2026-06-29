import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Download, LoaderCircle, Save } from 'lucide-react';
import { validatePresetName } from '../../services/api';
import { classNames } from '../../utils/uiUtils';
import InfoTooltip from '../common/InfoTooltip';
import PresetNameCombobox from './PresetNameCombobox';

const PRESET_NAME_PATTERN = /^[a-zA-Z0-9_-]+$/;

function PresetSaveTab({
  presets = [],
  initialOverwriteName = null,
  onSavePreset,
  onOverwritePreset,
  isSaving = false,
  savedPreset = null,
  onDownloadSaved = null,
  isDownloadingSaved = false,
  onCancel,
}) {
  const [name, setName] = useState(initialOverwriteName || '');
  const [description, setDescription] = useState('');
  const [descriptionTouched, setDescriptionTouched] = useState(false);
  const [validationError, setValidationError] = useState(null);
  const [isValidating, setIsValidating] = useState(false);

  const editablePresets = useMemo(() => presets.filter((p) => !p.is_builtin), [presets]);
  const matchedPreset = useMemo(
    () => editablePresets.find((p) => p.name.toLowerCase() === name.trim().toLowerCase()) || null,
    [editablePresets, name]
  );
  const isOverwrite = Boolean(matchedPreset);

  useEffect(() => {
    if (initialOverwriteName) {
      const p = presets.find((x) => x.name === initialOverwriteName);
      setName(initialOverwriteName);
      if (p && !descriptionTouched) setDescription(p.description || '');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialOverwriteName]);

  const validateNameLocally = useCallback((value) => {
    if (!value.trim()) return 'Preset name is required.';
    if (!PRESET_NAME_PATTERN.test(value)) {
      return 'Preset name can only contain letters, numbers, hyphens, and underscores.';
    }
    if (value.toLowerCase() === 'default') return '"default" is a reserved preset name.';
    return null;
  }, []);

  const handleNameChange = (next) => {
    setName(next);
    setValidationError(validateNameLocally(next));
    if (descriptionTouched) return;
    const match = editablePresets.find((p) => p.name.toLowerCase() === next.trim().toLowerCase());
    setDescription(match ? (match.description || '') : '');
  };

  const handleClearOverwrite = () => {
    setName('');
    if (!descriptionTouched) setDescription('');
    setValidationError(null);
  };

  const handleDescriptionChange = (e) => {
    setDescription(e.target.value);
    setDescriptionTouched(true);
  };

  const handleSubmit = async () => {
    if (savedPreset) return;
    const trimmed = name.trim();
    const desc = description.trim() || null;
    if (isOverwrite) {
      onOverwritePreset(matchedPreset.id, { description: desc });
      return;
    }
    const localError = validateNameLocally(trimmed);
    if (localError) { setValidationError(localError); return; }
    setIsValidating(true);
    try {
      const result = await validatePresetName(trimmed);
      if (!result.is_valid) { setValidationError(result.error); return; }
    } catch (err) {
      setValidationError(err.error?.message || 'Failed to validate preset name.');
      return;
    } finally {
      setIsValidating(false);
    }
    onSavePreset({ name: trimmed, description: desc });
  };

  const submitDisabled = Boolean(savedPreset) || isSaving || isValidating
    || !name.trim() || (!isOverwrite && !!validateNameLocally(name));

  return (
    <div>
      <div className="relative z-10">
        <div className="mb-1.5 flex items-center justify-between">
          <label className="label-tech">Preset Name</label>
          <span className={classNames(
            'rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider',
            isOverwrite
              ? 'bg-[var(--accent-warning)]/15 text-[var(--accent-warning)]'
              : 'bg-[var(--accent-primary)]/15 text-[var(--accent-primary)]'
          )}>
            {isOverwrite ? 'Overwriting' : 'New preset'}
          </span>
        </div>
        <PresetNameCombobox
          value={name}
          onChange={handleNameChange}
          presets={editablePresets}
          disabled={isSaving || Boolean(savedPreset)}
          hasCaution={isOverwrite}
        />
        {validationError && (
          <p className="mt-1 text-sm text-[var(--accent-danger)]">{validationError}</p>
        )}
        <p className="mt-1 text-xs text-[var(--text-muted)]">
          Letters, numbers, hyphens, and underscores only.
        </p>
        {isOverwrite && (
          <div className="mt-2 flex items-start gap-2 rounded-md border border-[var(--accent-warning)]/35 bg-[var(--accent-warning)]/8 px-3 py-2 text-xs text-[var(--accent-warning)]">
            <AlertTriangle className="mt-0.5 h-4 w-4 flex-shrink-0" />
            <span>
              This will overwrite <b>{name.trim()}</b> with the current configuration.{' '}
              <button type="button" onClick={handleClearOverwrite} className="underline hover:text-[var(--text-primary)]">
                Save as new instead
              </button>
            </span>
          </div>
        )}
      </div>

      <div className="relative z-10 mt-4">
        <label htmlFor="presetDescription" className="label-tech mb-1.5 block">
          Description <span className="font-normal normal-case tracking-normal text-[var(--text-muted)]">(optional)</span>
        </label>
        <textarea
          id="presetDescription"
          aria-label="Description"
          value={description}
          onChange={handleDescriptionChange}
          placeholder="e.g., Standard duel settings with competitive mappool"
          rows={2}
          className="input-base resize-none"
          disabled={isSaving}
        />
        {isOverwrite && !descriptionTouched && (
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            Loaded from the existing preset — edit if you want to change it.
          </p>
        )}
      </div>

      <div className="relative z-10 mt-6 flex items-center justify-end gap-3">
        <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={isSaving}>
          Cancel
        </button>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => savedPreset && onDownloadSaved?.(savedPreset)}
            disabled={!savedPreset || isDownloadingSaved}
          >
            {isDownloadingSaved ? (
              <><LoaderCircle className="mr-1 h-4 w-4 animate-spin" />Downloading...</>
            ) : (
              <><Download className="mr-1 h-4 w-4" />Download</>
            )}
          </button>
          {!savedPreset && (
            <InfoTooltip text="Download will be available after you save the preset." />
          )}
        </div>
        <button
          type="button"
          className={classNames('btn', isOverwrite ? 'btn-caution' : 'btn-primary')}
          onClick={handleSubmit}
          disabled={submitDisabled}
        >
          {(isSaving || isValidating) ? (
            <><LoaderCircle className="mr-1 h-4 w-4 animate-spin" />{isValidating ? 'Validating...' : 'Saving...'}</>
          ) : (
            <><Save className="mr-1 h-4 w-4" />{isOverwrite ? 'Overwrite Preset' : 'Save Preset'}</>
          )}
        </button>
      </div>
    </div>
  );
}

export default PresetSaveTab;
