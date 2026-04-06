import React, { useRef, useState } from 'react';
import { FolderOpen } from 'lucide-react'; // Using FilePlus2 icon

function FileUploadButton({
  onFileSelect,
  allowedExtensions = ['.cfg', '.txt'],
  maxSizeKB = 256,
  label = 'Upload File',
  targetConfigFileName, // The name of the config file this button is for (e.g., 'server.cfg')
  className = '',
}) {
  // console.log(`[FileUploadButton for ${targetConfigFileName}] Received onFileSelect prop type:`, typeof onFileSelect, 'Value:', onFileSelect); // Removed for cleaner console
  const fileInputRef = useRef(null);
  const [error, setError] = useState(null);

  const handleFileChange = async (event) => {
    setError(null);
    const file = event.target.files[0];
    if (!file) {
      return;
    }

    // Validate file extension
    const fileExtension = file.name.substring(file.name.lastIndexOf('.')).toLowerCase();
    if (!allowedExtensions.includes(fileExtension)) {
      const errMessage = `Invalid file type. Allowed: ${allowedExtensions.join(', ')}`;
      setError(errMessage);
      if (typeof onFileSelect === 'function') {
        onFileSelect(null, targetConfigFileName, errMessage); // Notify parent of error
      }
      event.target.value = null; // Reset file input
      return;
    }

    // Validate file size
    const maxSizeInBytes = maxSizeKB * 1024;
    if (file.size > maxSizeInBytes) {
      const errMessage = `File is too large. Maximum size: ${maxSizeKB}KB.`;
      setError(errMessage);
      if (typeof onFileSelect === 'function') {
        onFileSelect(null, targetConfigFileName, errMessage); // Notify parent of error
      }
      event.target.value = null; // Reset file input
      return;
    }

    // Read file content
    try {
      // console.log('[FileUploadButton] Reading file content for:', file.name); // Removed for cleaner console
      const content = await file.text();
      // console.log('[FileUploadButton] File content read. Calling onFileSelect for:', targetConfigFileName); // Removed for cleaner console
      if (typeof onFileSelect === 'function') {
        onFileSelect(content, targetConfigFileName, null); // Pass content and target file name, no error
      } else {
        console.warn('[FileUploadButton] onFileSelect is not a function!');
      }
    } catch (readError) {
      console.error('[FileUploadButton] Error reading file:', readError);
      const errMessage = 'Error reading file content.';
      setError(errMessage);
      if (typeof onFileSelect === 'function') {
        onFileSelect(null, targetConfigFileName, errMessage); // Notify parent of error
      } else {
        console.warn('[FileUploadButton] onFileSelect is not a function (in catch)!');
      }
    }
    event.target.value = null; // Reset file input for subsequent uploads of the same file
  };

  const handleClick = () => {
    setError(null); // Clear previous errors when opening dialog
    fileInputRef.current?.click();
  };

  return (
    <>
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileChange}
        accept={allowedExtensions.join(',')}
        style={{ display: 'none' }}
        aria-hidden="true"
      />
      <button
        type="button"
        onClick={handleClick}
        className={`flex items-center justify-center border border-gray-300 dark:border-slate-600 rounded-md text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-slate-700 hover:bg-gray-50 dark:hover:bg-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 dark:focus:ring-offset-slate-800 ${className}`} // Removed px-3, py-1.5, added justify-center
        title={`Upload ${targetConfigFileName}`}
      >
        <FolderOpen size={18} /> {/* Changed size to 18, removed mr-2, added fixed color */}
        {label && <span className="ml-2">{label}</span>} {/* Conditionally add margin if label exists */}
      </button>
      {/* Display error message directly below the button if needed, or parent can handle it */}
      {/* {error && <p className="text-xs text-red-500 mt-1">{error}</p>} */}
    </>
  );
}

export default FileUploadButton;
