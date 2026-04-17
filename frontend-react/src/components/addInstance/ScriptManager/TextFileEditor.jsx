import { useState, useCallback } from 'react';
import { CheckCircle, XCircle, RefreshCw, Maximize } from 'lucide-react';
import CodeMirrorEditor from '../../CodeMirrorEditor';
import { python } from '@codemirror/lang-python';
import { validateScript } from '../../../services/api';

function getFileType(path) {
  if (path?.endsWith('.py')) return 'python';
  if (path?.endsWith('.txt')) return 'text';
  return 'text';
}

export default function TextFileEditor({
  filePath, content, onChange, isDirty, isLoading, onExpand,
}) {
  const [lintStatus, setLintStatus] = useState(null);
  const [lintErrors, setLintErrors] = useState([]);
  const [isValidating, setIsValidating] = useState(false);
  const fileType = getFileType(filePath);
  const isPython = fileType === 'python';

  const handleValidate = useCallback(async () => {
    if (!isPython || !content) return;
    setIsValidating(true);
    try {
      const result = await validateScript(content);
      setLintStatus(result.valid ? 'valid' : 'invalid');
      setLintErrors(result.errors || []);
    } catch {
      setLintStatus(null);
    } finally {
      setIsValidating(false);
    }
  }, [content, isPython]);

  const language = isPython ? python() : null;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        Loading...
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-3 py-2 border-b border-gray-700">
        <div className="flex items-center gap-2 text-sm text-gray-400 min-w-0 flex-1">
          <span className="truncate">{filePath}</span>
          {isDirty && <span className="text-yellow-500 text-xs flex-shrink-0">(modified)</span>}
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {isPython && (
            <>
              {lintStatus === 'valid' && (
                <CheckCircle className="h-4 w-4 text-green-400" title="Valid" />
              )}
              {lintStatus === 'invalid' && (
                <XCircle className="h-4 w-4 text-red-400" title="Errors found" />
              )}
              <button
                onClick={handleValidate}
                disabled={isValidating}
                className="flex items-center gap-1 px-2 py-1 text-xs bg-gray-700 hover:bg-gray-600 text-gray-300 rounded disabled:opacity-50"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isValidating ? 'animate-spin' : ''}`} />
                Validate
              </button>
            </>
          )}
          {onExpand && (
            <button
              type="button"
              onClick={onExpand}
              className="p-1 hover:bg-[var(--surface-base)] rounded transition-colors text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              title="Expand editor"
              aria-label="Expand editor"
            >
              <Maximize size={14} />
            </button>
          )}
        </div>
      </div>

      {lintStatus === 'invalid' && lintErrors.length > 0 && (
        <div className="px-3 py-2 bg-red-900/20 border-b border-red-800/30 text-xs text-red-300 max-h-24 overflow-y-auto">
          {lintErrors.map((err, i) => (
            <div key={i}>Line {err.line}: {err.message}</div>
          ))}
        </div>
      )}

      <div className="flex-1 min-h-0 overflow-hidden">
        <CodeMirrorEditor
          value={content || ''}
          onChange={onChange}
          language={language}
          height="100%"
          isActiveTab={true}
        />
      </div>
    </div>
  );
}
