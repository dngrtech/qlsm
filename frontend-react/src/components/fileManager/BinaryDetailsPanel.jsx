import { useEffect, useRef, useState } from 'react';
import { Box, Upload } from 'lucide-react';

const DESCRIPTION_MAX = 1000;
const FORBIDDEN_RE = /[<>{}"]/;

function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

function formatDate(timestamp) {
  return new Date(timestamp * 1000).toLocaleString();
}

function validateDescription(value) {
  if (value.length > DESCRIPTION_MAX) return `Max ${DESCRIPTION_MAX} characters`;
  if (FORBIDDEN_RE.test(value)) return 'Cannot contain < > { } "';
  return null;
}

export default function BinaryDetailsPanel({
  filePath,
  fileName,
  size,
  lastModified,
  onReplace,
  description = '',
  onDescriptionSave,
}) {
  const [localDesc, setLocalDesc] = useState(description);
  const [focused, setFocused] = useState(false);
  const [validationError, setValidationError] = useState(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    setLocalDesc(description);
    setValidationError(null);
  }, [description, filePath]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [localDesc]);

  const handleChange = (e) => {
    const value = e.target.value;
    setLocalDesc(value);
    setValidationError(validateDescription(value));
  };

  const handleSave = () => {
    if (!onDescriptionSave) return;
    const trimmed = localDesc.trim();
    const error = validateDescription(trimmed);
    if (error) {
      setValidationError(error);
      return;
    }
    setValidationError(null);
    if (trimmed !== description) onDescriptionSave(trimmed);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleSave();
    }
    if (e.key === 'Escape') {
      setLocalDesc(description);
      setValidationError(null);
    }
  };

  return (
    <div className="flex flex-col h-full p-6 overflow-hidden">
      <div className="flex items-center gap-3 mb-6">
        <Box className="w-8 h-8 text-purple-400 flex-shrink-0" />
        <div className="min-w-0">
          <h3 className="text-lg font-semibold text-[var(--text-primary)] truncate">{fileName}</h3>
          <p className="text-sm text-[var(--text-secondary)] truncate">{filePath}</p>
        </div>
      </div>

      <div className="space-y-3 mb-6">
        <div className="flex justify-between text-sm">
          <span className="text-[var(--text-secondary)]">Type</span>
          <span className="text-[var(--text-primary)]">Native shared library (.so)</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-[var(--text-secondary)]">Size</span>
          <span className="text-[var(--text-primary)]">{size != null ? formatBytes(size) : '\u2014'}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-[var(--text-secondary)]">Last modified</span>
          <span className="text-[var(--text-primary)]">{lastModified ? formatDate(lastModified) : '\u2014'}</span>
        </div>
      </div>

      {onDescriptionSave && (
        <div className="flex flex-col flex-1 min-h-0 mb-4">
          <label className="block text-sm text-[var(--text-secondary)] mb-1">Description</label>
          <textarea
            ref={textareaRef}
            value={localDesc}
            onChange={handleChange}
            onBlur={() => {
              setFocused(false);
              handleSave();
            }}
            onFocus={() => setFocused(true)}
            onKeyDown={handleKeyDown}
            placeholder="Short label for this file..."
            style={{ resize: 'vertical', minHeight: '2rem', overflowY: 'auto' }}
            className={`flex-1 min-h-0 w-full px-3 py-1.5 bg-[var(--surface-elevated)] border rounded text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none ${
              validationError ? 'border-[var(--accent-danger)]' : 'border-[var(--surface-border)] focus:border-[var(--text-muted)]'
            }`}
          />
          <div className="flex justify-between mt-1">
            {validationError
              ? <span className="text-xs text-[var(--accent-danger)]">{validationError}</span>
              : <span />
            }
            {focused && (
              <span className={`text-xs ml-auto ${localDesc.length > DESCRIPTION_MAX ? 'text-[var(--accent-danger)]' : 'text-[var(--text-muted)]'}`}>
                {localDesc.length}/{DESCRIPTION_MAX}
              </span>
            )}
          </div>
        </div>
      )}

      <label className="inline-flex w-fit items-center gap-2 px-4 py-2 bg-[var(--surface-elevated)] hover:bg-[var(--surface-elevated)]/80 text-[var(--text-primary)] rounded text-sm transition-colors cursor-pointer">
        <Upload className="w-4 h-4" />
        Replace
        <input
          type="file"
          accept=".so"
          className="hidden"
          onChange={(e) => {
            if (e.target.files[0]) onReplace(e.target.files[0]);
            e.target.value = '';
          }}
        />
      </label>
    </div>
  );
}
