// Which plugin files the Plugins tab lets you enable.
//
// minqlx loads every qlx_plugins entry as a top-level module out of
// qlx_pluginsPath, so only root-level .py files can ever be enabled. Files in
// subfolders are helper modules imported by a root plugin (e.g.
// discord_extensions/* is imported by mydiscordbot.py), and __init__.py is a
// package marker. Both used to render a checkbox that silently did nothing.
import { basename } from './fileManagerUtils';
import { getPluginManifest } from './pluginManifest';

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
  'plugin-dependency': "This plugin is required by another enabled plugin, so it's enabled automatically and can't be toggled on its own.",
};

// depends_on entries a plugin's manifest declares, normalized to bare root
// filenames (e.g. "iouonegirl.py"). See pluginManifest.js for the schema.
export function getPluginDependsOn(item) {
  const manifest = getPluginManifest(item);
  const dependsOn = manifest?.depends_on;
  if (!Array.isArray(dependsOn)) return [];
  return dependsOn.filter(name => typeof name === 'string' && name.trim()).map(name => name.trim());
}

// path -> Set(path) of dependencies, root-level files only (same constraint as
// the plugins that declare them — minqlx can only ever load a root .py).
function buildDependencyPathMap(tree = []) {
  const rootFiles = new Map(); // filename -> tree node
  const walk = (node) => {
    if (!node) return;
    if (node.type === 'folder') {
      (node.children || []).forEach(walk);
      return;
    }
    const path = node.path || '';
    if (path.endsWith('.py') && !path.includes('/')) rootFiles.set(path, node);
  };
  tree.forEach(walk);

  const depMap = new Map();
  for (const [path, node] of rootFiles) {
    const resolved = new Set(getPluginDependsOn(node).filter(name => rootFiles.has(name)));
    if (resolved.size) depMap.set(path, resolved);
  }
  return depMap;
}

// Every filename declared as a dependency by any plugin in the tree — hidden
// from the checkbox list the same way ABSTRACT_PLUGIN_MODULES is, since it's
// controlled exclusively by whichever plugin(s) depend on it.
export function collectDependencyFilenames(tree = []) {
  const all = new Set();
  buildDependencyPathMap(tree).forEach(deps => deps.forEach(d => all.add(d)));
  return all;
}

// Transitive closure: every dependency (direct and indirect) the paths in
// `seedPaths` need, per the tree's depends_on declarations.
function dependencyClosure(depMap, seedPaths) {
  const result = new Set();
  const stack = [...seedPaths];
  while (stack.length) {
    const path = stack.pop();
    const deps = depMap.get(path);
    if (!deps) continue;
    deps.forEach(dep => {
      if (!result.has(dep)) {
        result.add(dep);
        stack.push(dep);
      }
    });
  }
  return result;
}

// The set to actually keep checked, given the plugins the operator explicitly
// picked (`manualPaths` — never includes a dependency-only file, since those
// have no checkbox to click): the manual picks plus every dependency they
// need, transitively. Re-derives the full set from scratch each call rather
// than tracking auto-added entries separately, so it's self-healing against
// stale state (an older save, a manifest that gained a new depends_on entry).
export function applyPluginDependencies(tree, manualPaths) {
  const depMap = buildDependencyPathMap(tree);
  const manual = new Set(manualPaths);
  const deps = dependencyClosure(depMap, manual);
  return new Set([...manual, ...deps]);
}

export function isEnableablePluginPath(path = '', libraryNames = null) {
  if (!path.endsWith('.py')) return false;
  if (path.includes('/')) return false;
  if (ABSTRACT_PLUGIN_MODULES.has(path)) return false;
  if (libraryNames && libraryNames.has(path)) return false;
  return path !== '__init__.py';
}

// Hint for a file row. Files inside a subfolder answer null: the folder row
// carries a single 'subfolder' hint for everything under it, rather than every
// child repeating the same explanation.
export function getPluginHintReason(path = '', libraryNames = null) {
  if (!path.endsWith('.py')) return null;
  if (path.includes('/')) return null;
  if (ABSTRACT_PLUGIN_MODULES.has(path)) return 'abstract-module';
  if (libraryNames && libraryNames.has(path)) return 'plugin-dependency';
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

// `tree` is optional: pass it when available so a stored dependency-only
// entry from before a manifest declared depends_on (or a hand-edited one)
// gets folded back into the closure instead of just being dropped.
export function partitionCheckedPaths(paths = [], tree = null) {
  const libraryNames = tree ? collectDependencyFilenames(tree) : null;
  const selectable = new Set();
  const dropped = [];
  for (const path of paths) {
    if (isEnableablePluginPath(path, libraryNames)) selectable.add(path);
    else dropped.push(path);
  }
  if (!tree) return { selectable, dropped };
  return { selectable: applyPluginDependencies(tree, selectable), dropped };
}

// Maps bare qlx_plugins names back onto tree paths. Only root-level files can
// match, so a name that resolves solely to a subfolder file is reported as
// dropped rather than silently ticking the wrong node. Dependency-only names
// are folded into the closure of whatever else resolved, same as
// partitionCheckedPaths.
export function resolveRootPluginPaths(tree = [], rawNames = []) {
  const libraryNames = collectDependencyFilenames(tree);
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
    if (isEnableablePluginPath(path, libraryNames)) rootPaths.add(path);
    else unusableNames.add(name);
  };
  tree.forEach(walk);

  const paths = [...applyPluginDependencies(tree, rootPaths)];
  const resolved = new Set(paths.map(path => path.replace(/\.py$/, '')));
  return {
    paths,
    droppedNames: [...unusableNames].filter(name => !resolved.has(name)),
  };
}

export function toQlxPluginNames(checked = []) {
  return Array.from(checked)
    .filter(path => isEnableablePluginPath(path))
    .map(path => path.replace(/\.py$/, ''));
}
