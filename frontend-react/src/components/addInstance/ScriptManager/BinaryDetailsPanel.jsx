import { Box, Upload, Trash2 } from 'lucide-react';

function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0)} ${units[i]}`;
}

function formatDate(timestamp) {
  return new Date(timestamp * 1000).toLocaleString();
}

export default function BinaryDetailsPanel({
  filePath, fileName, size, lastModified, onReplace, onDelete, isDeleting,
}) {
  return (
    <div className="flex flex-col h-full p-6">
      <div className="flex items-center gap-3 mb-6">
        <Box className="w-8 h-8 text-purple-400 flex-shrink-0" />
        <div className="min-w-0">
          <h3 className="text-lg font-semibold text-white truncate">{fileName}</h3>
          <p className="text-sm text-gray-400 truncate">{filePath}</p>
        </div>
      </div>

      <div className="space-y-3 mb-8">
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Type</span>
          <span className="text-gray-200">Native shared library (.so)</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Size</span>
          <span className="text-gray-200">{size != null ? formatBytes(size) : '\u2014'}</span>
        </div>
        <div className="flex justify-between text-sm">
          <span className="text-gray-400">Last modified</span>
          <span className="text-gray-200">{lastModified ? formatDate(lastModified) : '\u2014'}</span>
        </div>
      </div>

      <div className="flex gap-3 mt-auto">
        <label className="flex items-center gap-2 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-200 rounded-lg cursor-pointer text-sm transition-colors">
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
        <button
          onClick={onDelete}
          disabled={isDeleting}
          className="flex items-center gap-2 px-4 py-2 bg-red-900/50 hover:bg-red-800/50 text-red-300 rounded-lg text-sm transition-colors disabled:opacity-50"
        >
          <Trash2 className="w-4 h-4" />
          {isDeleting ? 'Deleting...' : 'Delete'}
        </button>
      </div>
    </div>
  );
}
