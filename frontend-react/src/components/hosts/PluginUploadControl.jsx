import React, { useRef, useState } from 'react';
import { Upload, X } from 'lucide-react';
import { validateRuntimeUploadPlugin } from '../../services/runtimeUpgradeApi';

// Upload / replace / remove control for one stripped plugin row. The file must
// be named exactly like the row's path; the server checks the text and only
// then does the file count as uploaded. Upload/Replace stay disabled while a
// check is running, so a late answer can never overwrite a newer pick.

function PluginUploadControl({ hostId, path, upload, onUploaded, onRemove, disabled = false, onPendingChange }) {
  const inputRef = useRef(null);
  const [pending, setPending] = useState(false);
  const [problem, setProblem] = useState(null);

  const setPendingState = (value) => {
    setPending(value);
    if (onPendingChange) onPendingChange(value);
  };

  const handleFile = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (file.name !== path) {
      setProblem({ message: `Need a file named ${path}`, reasons: [] });
      return;
    }
    setProblem(null);
    setPendingState(true);
    try {
      const text = await file.text();
      await validateRuntimeUploadPlugin(hostId, { path, text });
      onUploaded({ name: file.name, text });
    } catch (err) {
      const data = err?.response?.data?.error;
      setProblem({
        message: data?.message || err?.message || 'Could not check this file.',
        reasons: Array.isArray(data?.reasons) ? data.reasons : [],
      });
    } finally {
      setPendingState(false);
    }
  };

  return (
    <div className="mt-2 text-theme-primary">
      <input
        ref={inputRef}
        type="file"
        accept=".py"
        className="hidden"
        data-testid={`upload-input-${path}`}
        onChange={handleFile}
      />
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn btn-secondary"
          aria-label={`${upload ? 'Replace' : 'Upload'} ${path}`}
          disabled={disabled || pending}
          onClick={() => inputRef.current?.click()}
        >
          <Upload className="mr-1 h-3.5 w-3.5" />
          {upload ? 'Replace' : 'Upload'}
        </button>
        {upload && (
          <button
            type="button"
            className="btn btn-secondary"
            aria-label={`Remove uploaded ${path}`}
            disabled={disabled || pending}
            onClick={onRemove}
          >
            <X className="mr-1 h-3.5 w-3.5" />
            Remove
          </button>
        )}
        {upload && <span className="text-theme-secondary">Uploaded {upload.name}</span>}
      </div>
      {problem && (
        <div role="alert" className="mt-1 text-[var(--accent-danger)]">
          <p>{problem.message}</p>
          {problem.reasons.length > 0 && (
            <ul className="list-disc pl-4">
              {problem.reasons.map((reason) => <li key={reason}>{reason}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export default PluginUploadControl;
