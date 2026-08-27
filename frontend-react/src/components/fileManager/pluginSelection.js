// Which plugin files the Plugins tab lets you enable.
//
// minqlx loads every qlx_plugins entry as a top-level module out of
// qlx_pluginsPath, so only root-level .py files can ever be enabled. Files in
// subfolders are helper modules imported by a root plugin (e.g.
// discord_extensions/* is imported by mydiscordbot.py), and __init__.py is a
// package marker. Both used to render a checkbox that silently did nothing.
import { basename } from './fileManagerUtils';

// Root-level .py files that are libraries, not plugins. iouonegirl.py is an
// abstract base class (its own header says "DO NOT MANUALLY LOAD THIS ABSTRACT
// PLUGIN") that mybalance.py, protect.py, voteban.py and five others import; it
// has to stay in the preset's scripts/ for those imports to resolve, so it
// can't be excluded the way serverchecker.py is (kept out of the preset
// entirely and injected at deploy time as a system plugin). Excluding it here
// instead keeps the file on disk while removing its checkbox.
export const ABSTRACT_PLUGIN_MODULES = new Set(['iouonegirl.py']);

export const PLUGIN_HINT_TEXT = {
  subfolder: "Plugins in subfolders can't be enabled directly. Import them from a plugin in the root folder instead.",
  'package-marker': "__init__.py marks a package and can't be enabled as a plugin.",
  'abstract-module': "This file is a shared library imported by other plugins, not a plugin itself. Loading it directly does nothing.",
};

export function isEnableablePluginPath(path = '') {
  if (!path.endsWith('.py')) return false;
  if (path.includes('/')) return false;
  if (ABSTRACT_PLUGIN_MODULES.has(path)) return false;
  return path !== '__init__.py';
}

// Hint for a file row. Files inside a subfolder answer null: the folder row
// carries a single 'subfolder' hint for everything under it, rather than every
// child repeating the same explanation.
export function getPluginHintReason(path = '') {
  if (!path.endsWith('.py')) return null;
  if (path.includes('/')) return null;
  if (ABSTRACT_PLUGIN_MODULES.has(path)) return 'abstract-module';
  return path === '__init__.py' ? 'package-marker' : null;
}

// Whether a folder row should carry the 'subfolder' hint — only worth showing
// when the folder actually holds plugin files somewhere beneath it.
export function folderHasPluginFiles(node) {
  return (node?.children || []).some(child => (
    child.type === 'folder'
      ? folderHasPluginFiles(child)
      : (child.path || '').endsWith('.py')
  ));
}

export function partitionCheckedPaths(paths = []) {
  const selectable = new Set();
  const dropped = [];
  for (const path of paths) {
    if (isEnableablePluginPath(path)) selectable.add(path);
    else dropped.push(path);
  }
  return { selectable, dropped };
}

// Maps bare qlx_plugins names back onto tree paths. Only root-level files can
// match, so a name that resolves solely to a subfolder file is reported as
// dropped rather than silently ticking the wrong node.
export function resolveRootPluginPaths(tree = [], rawNames = []) {
  const wanted = new Set(rawNames);
  const rootPaths = new Set();
  const unusableNames = new Set();

  const walk = (node) => {
    if (node.type === 'folder') {
      (node.children || []).forEach(walk);
      return;
    }
    const path = node.path || '';
    if (!path.endsWith('.py')) return;
    const name = basename(path).replace(/\.py$/, '');
    if (!wanted.has(name)) return;
    if (isEnableablePluginPath(path)) rootPaths.add(path);
    else unusableNames.add(name);
  };
  tree.forEach(walk);

  const paths = [...rootPaths];
  const resolved = new Set(paths.map(path => path.replace(/\.py$/, '')));
  return {
    paths,
    droppedNames: [...unusableNames].filter(name => !resolved.has(name)),
  };
}

export function toQlxPluginNames(checked = []) {
  return Array.from(checked)
    .filter(isEnableablePluginPath)
    .map(path => path.replace(/\.py$/, ''));
}
