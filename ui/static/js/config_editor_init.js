
// Wait for the DOM to be fully loaded before initializing CodeMirror
document.addEventListener('DOMContentLoaded', () => {
  // Check if the CodeMirror global object is available
  if (typeof CodeMirror === 'undefined') {
    console.error("CodeMirror (window.CodeMirror) not loaded. Check script tags in base.html.");
    return;
  }

  // Store editor instances
  const editors = {};

  // NOTE: Custom CodeMirror modes (qlcfg, qlaccess, qlmappool) are now defined in separate files
  // in the ui/static/js/codemirror_modes/ directory.
  // Ensure those files are loaded before this script in your HTML.

  function initEditor(textareaId, mode, theme) {
    const textarea = document.getElementById(textareaId);
    if (!textarea) {
      console.warn(`Textarea with ID '${textareaId}' not found.`);
      return;
    }

    const editorOptions = {
      lineNumbers: true,
      mode: mode, // e.g., 'properties', 'text/plain'
      theme: theme || 'default', // Use a specific theme or CodeMirror's default
      // Add other CodeMirror 5 options as needed:
      // matchBrackets: true,
      // autoCloseBrackets: true,
      // lineWrapping: true,
    };

    try {
      const editor = CodeMirror.fromTextArea(textarea, editorOptions);
      editors[textareaId] = editor; // Store the editor instance
      // If you need to ensure the textarea is updated on change for form submission:
      editor.on('change', () => {
         editor.save(); // Copies content back to the original textarea
       });
     } catch (e) {
       console.error(`Error initializing CodeMirror 5 for ${textareaId}:`, e);
       // Fallback: Ensure the original textarea is visible if CodeMirror fails
       textarea.style.display = 'block'; 
     }
  }

  // Initialize editors for each config file type
  // For server.cfg, use 'text/x-properties' mode (key = value, # or // for comments)
  // Note: CodeMirror's 'properties' mode typically uses '#' or '!' for comments.
  // Quake Live .cfg files use '//'. We might need a custom mode or adapt.
  // For simplicity, let's try 'properties' and see. If '//' isn't highlighted,
  // we can use 'text/plain' or look into a simple custom mode later.
  // The 'properties' mode from cdnjs should handle key=value and #/! comments.
  // For '//' comments, a more specific mode like 'clike' or a custom one would be better.
  // Let's start with 'properties' for server.cfg as it's included.
  
  // For server.cfg, 'properties' mode is a good start.
  // It handles key = value and usually # or ! for comments.
  // Quake Live uses // for comments. 'text/x-ini' might be closer if available or 'properties'.
  // The included 'properties.min.js' should define 'text/x-properties'.
  // Using 'text/x-csrc' from clike.min.js for // comments.
  initEditor('server-cfg-editor', 'qlcfg', 'default'); 

  // For the other files, they are simple line-based text or have simple comments.
  // 'text/plain' is the default if no mode is specified or if the mode isn't loaded.
  // We can be explicit with 'text/plain' or try to find simple modes if needed.
  // For mappool.txt (map|factory) and access.txt (steamid|level), comments are '#'.
  // 'properties' mode might work for these too if we treat the whole line as a key or value.
  // Or, we can use a mode that just highlights comments if we load one (e.g. from 'comment.js' addon).
  // For now, let's use 'text/plain' for simplicity for the others, or 'properties' if '#' comments are desired.
  
  initEditor('mappool-editor', 'qlmappool', 'default'); 
  initEditor('access-editor', 'qlaccess', 'default');  // Use new qlaccess mode
  initEditor('workshop-editor', 'qlworkshop', 'default'); // Use new qlworkshop mode

  // Handle Bootstrap tabs to refresh CodeMirror instances
  const configTabs = document.querySelectorAll('#configTabs button[data-bs-toggle="tab"]');
  configTabs.forEach(tabEl => {
    tabEl.addEventListener('shown.bs.tab', event => {
      const activeTabPaneId = event.target.getAttribute('data-bs-target').substring(1); // e.g., server-cfg-pane
      const editorTextareaId = activeTabPaneId.replace('-pane', '-editor'); // e.g., server-cfg-editor
      
      if (editors[editorTextareaId]) {
        editors[editorTextareaId].refresh();
      }
    });
  });

  // Also refresh the editor in the initially active tab, just in case.
  // This might not be strictly necessary if it's already visible on load,
  // but can help in some edge cases or if initial display is tricky.
  const initiallyActiveTabButton = document.querySelector('#configTabs .nav-link.active');
  if (initiallyActiveTabButton) {
    const activeTabPaneId = initiallyActiveTabButton.getAttribute('data-bs-target').substring(1);
    const editorTextareaId = activeTabPaneId.replace('-pane', '-editor');
    if (editors[editorTextareaId]) {
      // Delay refresh slightly to ensure the tab pane is fully rendered
      setTimeout(() => {
        editors[editorTextareaId].refresh();
      }, 50); // Small delay
    }
  }
});
