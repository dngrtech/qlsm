import { useCallback, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle,
  Copy,
  File as FileIcon,
  Maximize,
  RefreshCw,
} from 'lucide-react';

import CodeMirrorEditor from '../CodeMirrorEditor';
import { validateScript } from '../../services/api';
import { copyToClipboard } from '../../utils/clipboard';
import BinaryDetailsPanel from './BinaryDetailsPanel';

function getFileType(name = '') {
  if (name.endsWith('.py')) return 'python';
  if (name.endsWith('.so')) return 'binary';
  return 'text';
}

export default function FileEditorPanel({
  selectedFile,
  content,
  onChange,
  isDirty,
  isLoading,
  language,
  linterSource,
  capabilities,
  onExpand,
  onReplace,
  binaryDescription,
  onSaveBinaryDescription,
}) {
  const [validation, setValidation] = useState(null);
  const [validating, setValidating] = useState(false);

  const fileType = selectedFile
    ? (selectedFile.file_type || getFileType(selectedFile.name))
    : null;
  const canValidate = capabilities?.canValidate && fileType === 'python';

  const handleCopy = useCallback(() => {
    copyToClipboard(content || '').catch(() => {});
  }, [content]);

  const handleValidate = useCallback(async () => {
    if (!canValidate) return;
    setValidating(true);
    setValidation(null);
    try {
      const result = await validateScript(content || '');
      setValidation({
        valid: Boolean(result.valid),
        errors: result.errors || [],
      });
    } catch (err) {
      setValidation({
        valid: false,
        errors: [{ message: err.message || 'Validation failed' }],
      });
    } finally {
      setValidating(false);
    }
  }, [canValidate, content]);

  if (!selectedFile) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500 text-sm">
        Select a file to view or edit
      </div>
    );
  }

  if (fileType === 'binary') {
    return (
      <BinaryDetailsPanel
        filePath={selectedFile.path}
        fileName={selectedFile.name}
        size={selectedFile.size}
        lastModified={selectedFile.last_modified}
        onReplace={onReplace}
        description={binaryDescription}
        onDescriptionSave={onSaveBinaryDescription}
      />
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        Loading...
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-3 py-2 border-b border-[var(--surface-border)]">
        <div className="flex items-center gap-2 text-sm text-[var(--text-secondary)] min-w-0">
          <FileIcon className="w-4 h-4 flex-shrink-0" />
          <span className="truncate">{selectedFile.path}</span>
          {isDirty && <span className="text-yellow-500 text-xs flex-shrink-0">(modified)</span>}
        </div>
        <div className="flex items-center gap-1 flex-shrink-0">
          {canValidate && (
            <>
              {validation?.valid && (
                <CheckCircle className="h-4 w-4 text-green-400" title="Valid" />
              )}
              {validation && !validation.valid && (
                <AlertTriangle className="h-4 w-4 text-red-400" title="Errors found" />
              )}
              <button
                type="button"
                onClick={handleValidate}
                disabled={validating}
                className="flex items-center gap-1 px-2 py-1 text-xs bg-[var(--surface-elevated)] hover:bg-[var(--surface-elevated)]/80 text-[var(--text-secondary)] rounded disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${validating ? 'animate-spin' : ''}`} />
                Validate
              </button>
            </>
          )}
          <button
            type="button"
            onClick={handleCopy}
            className="p-1 hover:bg-[var(--surface-base)] rounded transition-colors text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            title="Copy to clipboard"
            aria-label="Copy to clipboard"
          >
            <Copy size={14} />
          </button>
          {onExpand && (
            <button
              type="button"
              onClick={() => onExpand(selectedFile, content || '')}
              className="p-1 hover:bg-[var(--surface-base)] rounded transition-colors text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              title="Expand editor"
              aria-label="Expand editor"
            >
              <Maximize size={14} />
            </button>
          )}
        </div>
      </div>

      {validation && !validation.valid && validation.errors.length > 0 && (
        <div className="px-3 py-2 bg-red-900/20 border-b border-red-800/30 text-xs text-red-300 max-h-24 overflow-y-auto">
          {validation.errors.map((err, index) => (
            <div key={`${err.line || 'global'}-${index}`}>
              {err.line ? `Line ${err.line}: ` : ''}{err.message}
            </div>
          ))}
        </div>
      )}

      <div className="flex-1 min-h-0 overflow-hidden">
        <CodeMirrorEditor
          value={content || ''}
          onChange={onChange}
          language={language}
          linterSource={linterSource}
          isActiveTab={true}
          height="100%"
        />
      </div>
    </div>
  );
}
