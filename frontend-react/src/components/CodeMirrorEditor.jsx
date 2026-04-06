import React, { useEffect, useRef, useCallback } from 'react';
import { EditorState, StateEffect, Prec } from '@codemirror/state';
import { search, searchKeymap } from '@codemirror/search';
import {
  EditorView,
  keymap,
  lineNumbers,
  highlightActiveLineGutter,
  highlightSpecialChars,
  drawSelection,
  dropCursor,
  rectangularSelection,
  crosshairCursor,
  highlightActiveLine,
} from '@codemirror/view';
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands';
import { oneDark } from '@codemirror/theme-one-dark';
import { linter, lintGutter } from '@codemirror/lint';
import { syntaxHighlighting, HighlightStyle, bracketMatching, indentOnInput } from '@codemirror/language';
import { tags as t } from '@lezer/highlight';
import { useTheme } from '../context/ThemeContext';
// Imports for custom tags are still needed for highlight style, but specific linters aren't needed for the check anymore
import {
  modTag,
  adminTag,
  banTag
} from '../codemirror-lang-qlaccess';

// Import qlcfg language (assuming it exists or will be created)
import { qlcfgLanguage } from '../codemirror-lang-qlcfg';
// Import custom log language for viewing logs
import { logLanguage } from '../utils/logLanguage';
// Import new custom chat log language
import { chatLogLanguage, chatDarkHighlighting, chatLightHighlighting } from '../utils/chatLogLanguage';

// Dark highlight style
const darkHighlightStyle = HighlightStyle.define([
  { tag: t.lineComment, class: 'custom-line-comment' },
  { tag: modTag, color: '#42a5f5' },
  { tag: adminTag, color: 'yellow' },
  { tag: banTag, color: 'red' },
  { tag: t.number, color: '#569CD6' },
  { tag: t.operator, color: '#D4D4D4' },
  { tag: t.invalid, color: '#ff6b6b', fontWeight: 'bold' },
  { tag: t.keyword, color: '#ffa500' },
  { tag: t.string, color: '#98c379' },
  { tag: t.comment, color: '#6A9955' },
  { tag: t.meta, color: '#c678dd' },
  { tag: t.attributeName, color: '#61afef' },
  { tag: t.typeName, color: '#e5c07b' },
]);

// Light highlight style — high contrast for light backgrounds
const lightHighlightStyle = HighlightStyle.define([
  { tag: t.lineComment, color: '#6e7781' },
  { tag: modTag, color: '#0550ae' },
  { tag: adminTag, color: '#953800' },
  { tag: banTag, color: '#cf222e' },
  { tag: t.number, color: '#0550ae' },
  { tag: t.operator, color: '#24292f' },
  { tag: t.invalid, color: '#cf222e', fontWeight: 'bold' },
  { tag: t.keyword, color: '#8250df', fontWeight: 'bold' },
  { tag: t.string, color: '#0a3069' },
  { tag: t.comment, color: '#6e7781' },
  { tag: t.meta, color: '#8250df' },
  { tag: t.variableName, color: '#cf222e' },
  { tag: t.attributeName, color: '#116329' },
  { tag: t.typeName, color: '#953800' },
]);

// Dark editor chrome theme
const darkEditorTheme = EditorView.theme({
  '& .custom-line-comment': { color: '#6A9955 !important' },
  '&': { height: '100%', backgroundColor: 'transparent !important' },
  '& .cm-scroller': { backgroundColor: 'transparent !important', scrollbarColor: '#555 transparent' },
  '& .cm-content': { backgroundColor: 'transparent !important' },
  '& .cm-gutters': { backgroundColor: 'transparent !important', borderRight: '1px solid var(--surface-border)' },
  '& .cm-gutter': { backgroundColor: 'transparent !important' },
  '& .cm-activeLineGutter': { backgroundColor: 'rgba(255, 255, 255, 0.05) !important' },
  '& .cm-activeLine': { backgroundColor: 'rgba(255, 255, 255, 0.03) !important' },
  '& .cm-scroller::-webkit-scrollbar': { width: '14px', height: '14px' },
  '& .cm-scroller::-webkit-scrollbar-track': { background: 'transparent' },
  '& .cm-scroller::-webkit-scrollbar-thumb': { background: '#555', borderRadius: '4px' },
  '& .cm-scroller::-webkit-scrollbar-thumb:hover': { background: '#777' },
  '& .cm-panels': { backgroundColor: '#1e1e1e', zIndex: '100' },
  '& .cm-panels-top': { borderBottom: '1px solid #444' },
  '& .cm-search': { padding: '4px 8px' },
  '& .cm-search input': { backgroundColor: '#333', color: '#fff', border: '1px solid #555', borderRadius: '3px', padding: '2px 6px' },
  '& .cm-search button': { backgroundColor: '#444', color: '#fff', border: '1px solid #555', borderRadius: '3px', padding: '2px 8px', marginLeft: '4px' },
  '& .cm-lint-marker-info': { content: '"" !important', color: '#60a5fa', fontSize: '14px', fontWeight: 'bold', fontFamily: 'serif', fontStyle: 'italic', width: '1em', textAlign: 'center' },
  '& .cm-lint-marker-info::before': { content: '"i"' },
});

// Light editor chrome theme
const lightEditorTheme = EditorView.theme({
  '&': { height: '100%', backgroundColor: '#f6f8fa !important' },
  '& .cm-scroller': { backgroundColor: '#f6f8fa !important', scrollbarColor: '#c1c8d1 transparent' },
  '& .cm-content': { backgroundColor: 'transparent !important', color: '#24292f' },
  '& .cm-gutters': { backgroundColor: '#eef1f5 !important', borderRight: '1px solid #d0d7de !important', color: '#636c76 !important' },
  '& .cm-gutter': { backgroundColor: 'transparent !important' },
  '& .cm-activeLineGutter': { backgroundColor: 'rgba(0, 0, 0, 0.06) !important', color: '#24292f !important' },
  '& .cm-activeLine': { backgroundColor: 'rgba(0, 0, 0, 0.04) !important' },
  '& .cm-cursor': { borderLeftColor: '#24292f !important' },
  '& .cm-selectionBackground': { backgroundColor: 'rgba(59, 130, 246, 0.2) !important' },
  '& .cm-matchingBracket': { backgroundColor: 'rgba(5, 80, 174, 0.15) !important', color: '#0550ae !important' },
  '& .cm-scroller::-webkit-scrollbar': { width: '14px', height: '14px' },
  '& .cm-scroller::-webkit-scrollbar-track': { background: 'transparent' },
  '& .cm-scroller::-webkit-scrollbar-thumb': { background: '#c1c8d1', borderRadius: '4px' },
  '& .cm-scroller::-webkit-scrollbar-thumb:hover': { background: '#a0a8b4' },
  '& .cm-panels': { backgroundColor: '#eef1f5', zIndex: '100', color: '#24292f' },
  '& .cm-panels-top': { borderBottom: '1px solid #d0d7de' },
  '& .cm-search': { padding: '4px 8px' },
  '& .cm-search input': { backgroundColor: '#fff', color: '#24292f', border: '1px solid #d0d7de', borderRadius: '3px', padding: '2px 6px' },
  '& .cm-search button': { backgroundColor: '#e8ecf1', color: '#24292f', border: '1px solid #d0d7de', borderRadius: '3px', padding: '2px 8px', marginLeft: '4px' },
  '& .cm-lint-marker-info': { content: '"" !important', color: '#2563eb', fontSize: '14px', fontWeight: 'bold', fontFamily: 'serif', fontStyle: 'italic', width: '1em', textAlign: 'center' },
  '& .cm-lint-marker-info::before': { content: '"i"' },
});

// Helper function to build extensions
const getExtensions = (currentLanguage, currentLinterSource, onChangeCallback, isReadOnly = false, isDark = true) => {
  const highlightStyle = isDark ? darkHighlightStyle : lightHighlightStyle;

  const baseExtensions = [
    lineNumbers(),
    highlightActiveLineGutter(),
    highlightSpecialChars(),
    history(),
    drawSelection(),
    dropCursor(),
    indentOnInput(),
    syntaxHighlighting(highlightStyle, { fallback: true }),
    bracketMatching(),
    rectangularSelection(),
    crosshairCursor(),
    highlightActiveLine(),
    search(),
    Prec.highest(keymap.of([
      ...searchKeymap,
      ...defaultKeymap,
      ...historyKeymap,
    ])),
    ...(isDark ? [oneDark, darkEditorTheme] : [lightEditorTheme]),
    EditorView.updateListener.of((update) => {
      if (update.docChanged && !isReadOnly) {
        onChangeCallback(update.state.doc.toString());
      }
    }),
  ];

  // Add readOnly extension if needed
  if (isReadOnly) {
    baseExtensions.push(EditorState.readOnly.of(true));
  }
  if (currentLanguage) {
    baseExtensions.push(currentLanguage);

    // Add dedicated chat log highlighting (non-fallback, so custom tags are styled)
    if (currentLanguage === chatLogLanguage) {
      baseExtensions.push(isDark ? chatDarkHighlighting : chatLightHighlighting);
    }

    // Determine the linter function to use
    // Determine the linter function to use
    let activeLinter = null;
    if (currentLinterSource) {
      // Check if the provided linterSource is one of the direct linters
      // or if it's a factory function that needs to be called.
      if (typeof currentLinterSource === 'function') {
        // Distinguish between a linter function (takes 'view') and a factory (takes 0 args)
        if (currentLinterSource.length > 0) {
          activeLinter = currentLinterSource;
        } else {
          activeLinter = currentLinterSource();
        }
      }
    } else {
      // Static linters fallback removed as we want to be explicit via props
      // If needed, they can be re-added but reliance on equality check was the issue.
      // Since EditInstanceConfigModal passes them explicitly now, this fallback block is likely redundant or risky if imports match.
      // We will leave the fallback empty or strictly safe.

    }

    // Add linter and gutter if a linter function was determined
    if (activeLinter) {
      baseExtensions.push(linter(activeLinter));
      baseExtensions.push(lintGutter());
    }
  }
  return baseExtensions;
};


// Pass linterSource as a prop - this should be a function that returns a linter function or null
const CodeMirrorEditor = ({ value, onChange, language, isActiveTab, linterSource = null, height = '220px', readOnly = false }) => {
  const { theme } = useTheme();
  const isDark = theme === 'dark';
  const editorRef = useRef(null);
  const viewRef = useRef(null);
  const onChangeRef = useRef(onChange);
  const languageRef = useRef(language);
  const linterSourceRef = useRef(linterSource);
  const isDarkRef = useRef(isDark);

  // Keep refs updated
  useEffect(() => { onChangeRef.current = onChange; }, [onChange]);
  useEffect(() => { languageRef.current = language; }, [language]);
  useEffect(() => { linterSourceRef.current = linterSource; }, [linterSource]);
  useEffect(() => { isDarkRef.current = isDark; }, [isDark]);


  // Effect for Initialization and Cleanup (runs only once)
  useEffect(() => {
    if (editorRef.current && !viewRef.current) {
      const extensions = getExtensions(languageRef.current, linterSourceRef.current, (newValue) => onChangeRef.current(newValue), readOnly, isDarkRef.current);
      const startState = EditorState.create({
        doc: value || '',
        extensions: extensions,
      });
      const view = new EditorView({
        state: startState,
        parent: editorRef.current,
      });
      viewRef.current = view;
    }

    // Cleanup
    return () => {
      if (viewRef.current) {
        viewRef.current.destroy();
        viewRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Empty dependency array ensures this runs only once


  // Effect for handling external value changes
  useEffect(() => {
    if (viewRef.current) {
      const currentValueInEditor = viewRef.current.state.doc.toString();
      if (value !== currentValueInEditor) {
        const newContent = value || ''; // Ensure newContent is never null/undefined
        const newDocLength = newContent.length;

        // Get current selection BEFORE dispatching the change
        const currentSelection = viewRef.current.state.selection.main; // Get the main selection range

        // Clamp the selection anchor and head to be within the new document's bounds
        const newAnchor = Math.min(currentSelection.anchor, newDocLength);
        const newHead = Math.min(currentSelection.head, newDocLength);

        viewRef.current.dispatch({
          changes: { from: 0, to: currentValueInEditor.length, insert: newContent },
          // Use the clamped selection
          selection: { anchor: newAnchor, head: newHead },
          userEvent: 'setValue'
        });
      }
    }
  }, [value]); // Only depend on the external value prop


  // Effect for handling language/linter/theme changes
  useEffect(() => {
    if (viewRef.current) {
      const newExtensions = getExtensions(language, linterSource, (newValue) => onChangeRef.current(newValue), readOnly, isDark);
      viewRef.current.dispatch({
        effects: StateEffect.reconfigure.of(newExtensions)
      });
    }
  }, [language, linterSource, isDark]);


  // Effect to refresh editor when tab becomes active (remains the same)
  useEffect(() => {
    if (isActiveTab && viewRef.current) {
      const timer = setTimeout(() => {
        if (viewRef.current) {
          viewRef.current.requestMeasure();
        }
      }, 0);
      return () => clearTimeout(timer);
    }
  }, [isActiveTab]);


  return (
    <div
      ref={editorRef}
      className="codemirror-editor-container [&_.cm-editor]:h-full" // Ensures .cm-editor inside fills this container
      style={
        height === '100%'
          ? { height: '100%', minHeight: '100px', overflow: 'hidden' } // For full height scenarios (like the modal)
          : { // Default style for tabbed view
            height: height, // Use passed height or default '220px'
            minHeight: '100px',
            maxHeight: '75vh',
            resize: 'vertical',
            overflow: 'auto',
          }
      }
    />
  );
};

// Memoize the component
const MemoizedCodeMirrorEditor = React.memo(CodeMirrorEditor);
export default MemoizedCodeMirrorEditor;

/* Original useEffect logic - kept for reference during refactor
  useEffect(() => {
    // Function to build extensions based on language and potential dynamic linter
    const getExtensions = (currentLanguage, currentLinterSource) => {
      // Define the custom highlight style using the imported tags
      const customHighlightStyle = HighlightStyle.define([
        { tag: t.lineComment, class: 'custom-line-comment' }, // Assign a custom class
        { tag: modTag, color: '#42a5f5' }, // Brighter blue for better contrast
        { tag: adminTag, color: 'yellow' },
        { tag: banTag, color: 'red' },
        { tag: t.number, color: '#569CD6' },
        { tag: t.operator, color: '#D4D4D4' },
        { tag: t.invalid, color: '#ff0000', fontStyle: 'italic' }
      ]);

      const baseExtensions = [
        basicSetup,
        keymap.of(defaultKeymap),
        oneDark, // Base theme
        syntaxHighlighting(customHighlightStyle), // Apply the custom highlight style
        EditorView.theme({ // Theme to style the custom class
          '& .custom-line-comment': { color: '#6A9955 !important' }
        }),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) {
            onChange(update.state.doc.toString());
          }
        }),
      ];
      if (currentLanguage) {
        baseExtensions.push(currentLanguage);

        // Determine the linter function to use
        let activeLinter = null;
        if (currentLinterSource) {
          // If a dynamic linter source is provided, use it
          activeLinter = currentLinterSource(); // Call the source function to get the actual linter
        } else if (currentLanguage === qlaccessLanguage) {
          // Fallback to static linters if no dynamic source
          activeLinter = qlAccessLinter;
        } else if (currentLanguage === qlworkshopLanguage) {
          activeLinter = qlWorkshopLinter;
        }

        // Add linter and gutter if a linter function was determined
        if (activeLinter) {
          baseExtensions.push(linter(activeLinter));
          baseExtensions.push(lintGutter());
        }
      }
      return baseExtensions;
    };

    if (editorRef.current && !viewRef.current) {
      // Pass linterSource to getExtensions during initial setup
      const extensions = getExtensions(language, linterSource);
      const startState = EditorState.create({
        doc: value || '',
        extensions: extensions,
      });
      const view = new EditorView({
        state: startState,
        parent: editorRef.current,
      });
      viewRef.current = view;
    } else if (viewRef.current && language) {
      // Check if the language or its associated linter needs to be reconfigured.
      let needsReconfiguration = false;
      const currentActiveExtensions = viewRef.current.state.facet(EditorState.extensions);

      const currentLangExtension = currentActiveExtensions.find(ext => ext === language || (ext && ext.language === language.language));
      if (!currentLangExtension) {
        needsReconfiguration = true;
      }

      // --- Linter Reconfiguration Logic ---
      // Determine the *new* linter function based on the *new* language and linterSource
      let newLinterFunc = null;
      if (linterSource) {
        newLinterFunc = linterSource();
      } else if (language === qlaccessLanguage) {
        newLinterFunc = qlAccessLinter;
      } else if (language === qlworkshopLanguage) {
        newLinterFunc = qlWorkshopLinter;
      }

      // Find the *currently active* linter function in the state's extensions
      let currentLinterFunc = null;
      const lintPlugin = currentActiveExtensions.find(ext => ext && typeof ext.source === 'function' && ext.extension && ext.extension.name === 'linter');
      if (lintPlugin) {
        currentLinterFunc = lintPlugin.source;
      }

      // Reconfigure if the required linter function has changed (or needs adding/removing)
      if (currentLinterFunc !== newLinterFunc) {
         needsReconfiguration = true;
      }
      // --- End Linter Reconfiguration Logic ---


      if (needsReconfiguration) {
        // Pass linterSource to getExtensions when reconfiguring
        const newExtensions = getExtensions(language, linterSource);
        viewRef.current.dispatch({
          effects: StateEffect.reconfigure.of(newExtensions)
        });
      }
    }

    return () => {
      if (viewRef.current) {
        viewRef.current.destroy();
        viewRef.current = null;
      }
    };
  // Pass linterSource as a dependency to re-run setup/reconfiguration if it changes
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editorRef, onChange, language, linterSource]);

  // Handle external changes to the value prop
  useEffect(() => {
    if (viewRef.current && value !== viewRef.current.state.doc.toString()) {
      viewRef.current.dispatch({
        changes: { from: 0, to: viewRef.current.state.doc.length, insert: value || '' },
      });
    }
  }, [value]);

  // Effect to refresh editor when tab becomes active
  useEffect(() => {
    if (isActiveTab && viewRef.current) {
      const timer = setTimeout(() => {
        if (viewRef.current) {
          viewRef.current.requestMeasure();
        }
      }, 0);
      return () => clearTimeout(timer);
    }
  }, [isActiveTab]);

  return (
    <div
      ref={editorRef}
      className="codemirror-editor-container [&_.cm-editor]:h-full"
      style={{
        height: '220px',      // Initial height
        minHeight: '100px',   // Minimum sensible height
        maxHeight: '75vh',    // Maximum height (75% of viewport height)
        resize: 'vertical',
        overflow: 'auto',
        // The border and rounded corners are typically handled by the parent container,
        // but if this component is used standalone, these ensure it looks consistent.
        // We'll rely on parent for now, assuming it has border/rounded.
      }}
    />
  );
};

export default CodeMirrorEditor;
*/
