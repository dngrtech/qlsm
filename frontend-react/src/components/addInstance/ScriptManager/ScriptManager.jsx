import { useState, useCallback, useImperativeHandle, forwardRef } from 'react';
import PluginFileTree from './PluginFileTree';
import TextFileEditor from './TextFileEditor';
import BinaryDetailsPanel from './BinaryDetailsPanel';
import NewScriptModal from './NewScriptModal';

function getFileType(name) {
  if (name?.endsWith('.py')) return 'python';
  if (name?.endsWith('.txt')) return 'text';
  if (name?.endsWith('.so')) return 'binary';
  return 'text';
}

const NEW_SCRIPT_TEMPLATE = `"""
minqlx plugin
"""

import minqlx


class MyPlugin(minqlx.Plugin):
    def __init__(self):
        super().__init__()
        # Add hooks and commands here
`;

const ScriptManager = forwardRef(function ScriptManager({
  tree,
  onTreeRefresh,
  readContent,
  writeContent,
  upload,
  deleteFile,
  checkable,
  checkedFiles,
  onCheck,
  loading,
  error,
  onExpandEditor,
}, ref) {
  const [selectedFile, setSelectedFile] = useState(null);
  const [currentContent, setCurrentContent] = useState('');
  const [editedContent, setEditedContent] = useState({});
  const [contentLoading, setContentLoading] = useState(false);
  const [showNewModal, setShowNewModal] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  // Flush all pending text edits to the draft server-side
  const flushEdits = useCallback(async () => {
    const entries = Object.entries(editedContent);
    for (const [path, content] of entries) {
      await writeContent(path, content);
    }
    setEditedContent({});
  }, [editedContent, writeContent]);

  const updateContent = useCallback((path, content) => {
    setEditedContent(prev => ({ ...prev, [path]: content }));
    if (selectedFile?.path === path) {
      setCurrentContent(content);
    }
  }, [selectedFile]);

  useImperativeHandle(ref, () => ({ flushEdits, updateContent }), [flushEdits, updateContent]);

  const handleSelectFile = useCallback(async (item) => {
    if (item.type === 'folder') return;
    setSelectedFile(item);
    const fileType = item.file_type || getFileType(item.name);

    if (fileType !== 'binary') {
      if (editedContent[item.path] !== undefined) {
        setCurrentContent(editedContent[item.path]);
      } else {
        setContentLoading(true);
        try {
          const content = await readContent(item.path);
          setCurrentContent(content || '');
        } catch {
          setCurrentContent('');
        } finally {
          setContentLoading(false);
        }
      }
    }
  }, [readContent, editedContent]);

  const handleContentChange = useCallback((value) => {
    setCurrentContent(value);
    if (selectedFile) {
      setEditedContent(prev => ({ ...prev, [selectedFile.path]: value }));
    }
  }, [selectedFile]);

  const handleUpload = useCallback(async (file) => {
    try {
      await upload(file);
      const path = file.name;
      const fileType = getFileType(path);

      // Auto-check .py files
      if (checkable && path.endsWith('.py') && !checkedFiles?.has(path)) {
        onCheck(path, true);
      }

      // Auto-select and open the uploaded file
      const item = { name: file.name, path, file_type: fileType, type: 'file' };
      if (fileType !== 'binary') {
        setSelectedFile(item);
        setContentLoading(true);
        try {
          const content = await readContent(path);
          setCurrentContent(content || '');
        } catch {
          setCurrentContent('');
        } finally {
          setContentLoading(false);
        }
      } else {
        setSelectedFile(item);
      }
    } catch (err) {
      alert(err.response?.data?.error?.message || err.message || 'Upload failed');
    }
  }, [upload, checkable, checkedFiles, onCheck, readContent]);

  const handleDelete = useCallback(async () => {
    if (!selectedFile) return;
    const confirmed = window.confirm(`Delete ${selectedFile.name}?`);
    if (!confirmed) return;
    setIsDeleting(true);
    try {
      await deleteFile(selectedFile.path);
      if (checkable && checkedFiles?.has(selectedFile.path)) {
        onCheck(selectedFile.path, false);
      }
      setSelectedFile(null);
      setCurrentContent('');
    } catch (err) {
      alert(err.message || 'Delete failed');
    } finally {
      setIsDeleting(false);
    }
  }, [selectedFile, deleteFile, checkable, checkedFiles, onCheck]);

  const handleReplace = useCallback(async (file) => {
    if (!selectedFile) return;
    const confirmed = window.confirm(`Replace ${selectedFile.name} with ${file.name}?`);
    if (!confirmed) return;
    try {
      const dir = selectedFile.path.includes('/')
        ? selectedFile.path.substring(0, selectedFile.path.lastIndexOf('/'))
        : '';
      const uploadResult = await upload(file, dir);
      const uploadedPath = uploadResult?.path || (dir ? `${dir}/${file.name}` : file.name);
      if (uploadedPath !== selectedFile.path) {
        await deleteFile(selectedFile.path);
      }
    } catch (err) {
      alert(err.message || 'Replace failed');
    }
  }, [selectedFile, deleteFile, upload]);

  const handleNewFile = useCallback(async (path) => {
    const template = path.endsWith('.py') ? NEW_SCRIPT_TEMPLATE : '';
    await writeContent(path, template);
    await onTreeRefresh();
    setShowNewModal(false);

    // Auto-check new .py files
    if (checkable && path.endsWith('.py') && !checkedFiles?.has(path)) {
      onCheck(path, true);
    }

    // Auto-select and open the new file
    const fileType = getFileType(path);
    const name = path.includes('/') ? path.substring(path.lastIndexOf('/') + 1) : path;
    const item = { name, path, file_type: fileType, type: 'file' };
    setSelectedFile(item);
    setCurrentContent(template);
  }, [writeContent, onTreeRefresh, checkable, checkedFiles, onCheck]);

  if (error) {
    return (
      <div className="flex items-center justify-center h-full text-red-400 p-4">
        Failed to load plugin files: {error}
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400">
        Loading plugin files...
      </div>
    );
  }

  const fileType = selectedFile ? (selectedFile.file_type || getFileType(selectedFile.name)) : null;
  const isDirty = selectedFile ? editedContent[selectedFile.path] !== undefined : false;

  return (
    <div className="flex h-full border border-[var(--surface-border)] rounded-lg overflow-hidden">
      <div className="w-64 flex-shrink-0 border-r border-[var(--surface-border)] bg-[var(--surface-base)]">
        <PluginFileTree
          files={tree}
          selectedPath={selectedFile?.path}
          onSelectFile={handleSelectFile}
          onNewFile={() => setShowNewModal(true)}
          onUploadFile={handleUpload}
          checkable={checkable}
          checkedFiles={checkedFiles}
          onCheck={onCheck}
        />
      </div>
      <div className="flex-1 min-w-0 bg-[var(--surface-base)]">
        {!selectedFile ? (
          <div className="flex items-center justify-center h-full text-gray-500 text-sm">
            Select a file to view or edit
          </div>
        ) : fileType === 'binary' ? (
          <BinaryDetailsPanel
            filePath={selectedFile.path}
            fileName={selectedFile.name}
            size={selectedFile.size}
            lastModified={selectedFile.last_modified}
            onReplace={handleReplace}
            onDelete={handleDelete}
            isDeleting={isDeleting}
          />
        ) : (
          <TextFileEditor
            filePath={selectedFile.path}
            content={currentContent}
            onChange={handleContentChange}
            isDirty={isDirty}
            isLoading={contentLoading}
            onExpand={onExpandEditor ? () => onExpandEditor(selectedFile, currentContent) : undefined}
          />
        )}
      </div>
      <NewScriptModal
        isOpen={showNewModal}
        onClose={() => setShowNewModal(false)}
        onCreate={handleNewFile}
      />
    </div>
  );
});

export default ScriptManager;
