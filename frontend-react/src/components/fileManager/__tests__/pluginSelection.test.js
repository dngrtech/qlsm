import { describe, expect, it } from 'vitest';

import {
  PLUGIN_HINT_TEXT,
  applyPluginDependencies,
  collectDependencyFilenames,
  folderHasPluginFiles,
  getPluginDependsOn,
  getPluginHintReason,
  isEnableablePluginPath,
  partitionCheckedPaths,
  resolveRootPluginPaths,
  toQlxPluginNames,
} from '../pluginSelection';

describe('isEnableablePluginPath', () => {
  it('accepts a root-level .py plugin', () => {
    expect(isEnableablePluginPath('essentials.py')).toBe(true);
  });

  it('rejects a plugin inside a subfolder', () => {
    expect(isEnableablePluginPath('discord_extensions/admin.py')).toBe(false);
  });

  it('rejects __init__.py at the root and in a subfolder', () => {
    expect(isEnableablePluginPath('__init__.py')).toBe(false);
    expect(isEnableablePluginPath('extras/__init__.py')).toBe(false);
  });

  it('rejects non-python files', () => {
    expect(isEnableablePluginPath('plugins.txt')).toBe(false);
    expect(isEnableablePluginPath('ql_netfix.so')).toBe(false);
  });

  it('rejects iouonegirl.py — an abstract base other plugins import', () => {
    expect(isEnableablePluginPath('iouonegirl.py')).toBe(false);
  });
});

describe('getPluginHintReason', () => {
  it('returns null for an enableable plugin', () => {
    expect(getPluginHintReason('essentials.py')).toBeNull();
  });

  it('returns package-marker for a root __init__.py', () => {
    expect(getPluginHintReason('__init__.py')).toBe('package-marker');
  });

  it('returns null inside a subfolder — the folder row carries the hint', () => {
    expect(getPluginHintReason('extras/textart.py')).toBeNull();
    expect(getPluginHintReason('extras/__init__.py')).toBeNull();
  });

  it('returns null for non-python files so they get no hint', () => {
    expect(getPluginHintReason('notes.txt')).toBeNull();
  });

  it('returns abstract-module for iouonegirl.py', () => {
    expect(getPluginHintReason('iouonegirl.py')).toBe('abstract-module');
  });

  it('maps every reason to hint copy', () => {
    expect(PLUGIN_HINT_TEXT.subfolder).toMatch(/subfolders can't be enabled directly/);
    expect(PLUGIN_HINT_TEXT['package-marker']).toMatch(/marks a package/);
    expect(PLUGIN_HINT_TEXT['abstract-module']).toMatch(/shared library imported by other plugins/);
  });
});

describe('folderHasPluginFiles', () => {
  it('is true for a folder holding a .py file', () => {
    expect(folderHasPluginFiles({
      type: 'folder',
      children: [{ name: 'admin.py', path: 'extras/admin.py', type: 'file' }],
    })).toBe(true);
  });

  it('is true when the .py file sits in a nested folder', () => {
    expect(folderHasPluginFiles({
      type: 'folder',
      children: [{
        type: 'folder',
        children: [{ name: 'admin.py', path: 'extras/deep/admin.py', type: 'file' }],
      }],
    })).toBe(true);
  });

  it('is false for a folder with no plugin files', () => {
    expect(folderHasPluginFiles({
      type: 'folder',
      children: [{ name: 'notes.txt', path: 'extras/notes.txt', type: 'file' }],
    })).toBe(false);
  });

  it('is false for an empty or missing folder', () => {
    expect(folderHasPluginFiles({ type: 'folder', children: [] })).toBe(false);
    expect(folderHasPluginFiles(undefined)).toBe(false);
  });
});

describe('partitionCheckedPaths', () => {
  it('splits stored paths into selectable and dropped', () => {
    const { selectable, dropped } = partitionCheckedPaths([
      'balance.py',
      'discord_extensions/admin.py',
      '__init__.py',
      'essentials.py',
    ]);
    expect([...selectable]).toEqual(['balance.py', 'essentials.py']);
    expect(dropped).toEqual(['discord_extensions/admin.py', '__init__.py']);
  });

  it('handles an empty or missing list', () => {
    expect(partitionCheckedPaths([]).dropped).toEqual([]);
    expect([...partitionCheckedPaths().selectable]).toEqual([]);
  });
});

describe('resolveRootPluginPaths', () => {
  const tree = [
    {
      name: 'discord_extensions',
      path: 'discord_extensions',
      type: 'folder',
      children: [
        { name: 'admin.py', path: 'discord_extensions/admin.py', type: 'file' },
        { name: 'balance.py', path: 'discord_extensions/balance.py', type: 'file' },
      ],
    },
    { name: 'balance.py', path: 'balance.py', type: 'file' },
    { name: 'essentials.py', path: 'essentials.py', type: 'file' },
    { name: '__init__.py', path: '__init__.py', type: 'file' },
  ];

  it('resolves a name that exists only as a shared pool row', () => {
    const withShared = [...tree, { name: 'kickban.py', path: 'kickban.py', type: 'file', shared: true }];
    const { paths } = resolveRootPluginPaths(withShared, ['kickban']);
    expect(paths).toEqual(['kickban.py']);
  });

  it('resolves bare names to root-level paths only', () => {
    const { paths } = resolveRootPluginPaths(tree, ['balance', 'essentials']);
    expect(paths.sort()).toEqual(['balance.py', 'essentials.py']);
  });

  it('does not resolve a name that only exists in a subfolder, and reports it', () => {
    const { paths, droppedNames } = resolveRootPluginPaths(tree, ['admin']);
    expect(paths).toEqual([]);
    expect(droppedNames).toEqual(['admin']);
  });

  it('does not double-count a name present at root and in a subfolder', () => {
    const { paths, droppedNames } = resolveRootPluginPaths(tree, ['balance']);
    expect(paths).toEqual(['balance.py']);
    expect(droppedNames).toEqual([]);
  });

  it('ignores names that match nothing', () => {
    const { paths, droppedNames } = resolveRootPluginPaths(tree, ['nope']);
    expect(paths).toEqual([]);
    expect(droppedNames).toEqual([]);
  });
});

describe('toQlxPluginNames', () => {
  it('strips .py and drops everything non-enableable', () => {
    const names = toQlxPluginNames(new Set([
      'balance.py',
      'discord_extensions/admin.py',
      '__init__.py',
      'essentials.py',
    ]));
    expect(names).toEqual(['balance', 'essentials']);
  });

  it('never flattens a subfolder path into a bare name', () => {
    expect(toQlxPluginNames(new Set(['extras/textart.py']))).toEqual([]);
  });

  it('accepts an array as well as a Set', () => {
    expect(toQlxPluginNames(['balance.py'])).toEqual(['balance']);
  });
});

describe('plugin dependencies (depends_on)', () => {
  const depTree = [
    {
      name: 'mybalance.py', path: 'mybalance.py', type: 'file',
      plugin_manifest: { depends_on: ['iouonegirl.py'] },
    },
    {
      name: 'protect.py', path: 'protect.py', type: 'file',
      plugin_manifest: { depends_on: ['iouonegirl.py', 'shared_helper.py'] },
    },
    { name: 'iouonegirl.py', path: 'iouonegirl.py', type: 'file' },
    { name: 'shared_helper.py', path: 'shared_helper.py', type: 'file' },
    { name: 'essentials.py', path: 'essentials.py', type: 'file' },
    {
      name: 'extras', path: 'extras', type: 'folder',
      children: [{
        name: 'nested.py', path: 'extras/nested.py', type: 'file',
        plugin_manifest: { depends_on: ['ignored_subfolder_dep.py'] },
      }],
    },
  ];

  it('getPluginDependsOn reads and normalizes the manifest field', () => {
    expect(getPluginDependsOn({ plugin_manifest: { depends_on: [' iouonegirl.py ', '', 42, 'x.py'] } }))
      .toEqual(['iouonegirl.py', 'x.py']);
    expect(getPluginDependsOn({})).toEqual([]);
    expect(getPluginDependsOn({ plugin_manifest: { depends_on: 'not-an-array' } })).toEqual([]);
  });

  it('collectDependencyFilenames gathers every declared dependency across the tree', () => {
    expect(collectDependencyFilenames(depTree)).toEqual(new Set(['iouonegirl.py', 'shared_helper.py']));
  });

  it('ignores depends_on declared by a subfolder file', () => {
    expect(collectDependencyFilenames(depTree).has('ignored_subfolder_dep.py')).toBe(false);
  });

  it('isEnableablePluginPath hides a dependency file when libraryNames is passed', () => {
    const libraryNames = collectDependencyFilenames(depTree);
    expect(isEnableablePluginPath('iouonegirl.py', libraryNames)).toBe(false);
    expect(isEnableablePluginPath('shared_helper.py', libraryNames)).toBe(false);
    expect(isEnableablePluginPath('essentials.py', libraryNames)).toBe(true);
  });

  it('getPluginHintReason reports plugin-dependency for a library-only file', () => {
    const libraryNames = collectDependencyFilenames(depTree);
    expect(getPluginHintReason('shared_helper.py', libraryNames)).toBe('plugin-dependency');
    expect(PLUGIN_HINT_TEXT['plugin-dependency']).toMatch(/required by another enabled plugin/);
  });

  it('applyPluginDependencies adds the transitive closure of what is manually checked', () => {
    const result = applyPluginDependencies(depTree, new Set(['mybalance.py']));
    expect(result).toEqual(new Set(['mybalance.py', 'iouonegirl.py']));
  });

  it('applyPluginDependencies merges dependencies from multiple checked plugins', () => {
    const result = applyPluginDependencies(depTree, new Set(['mybalance.py', 'protect.py']));
    expect(result).toEqual(new Set(['mybalance.py', 'protect.py', 'iouonegirl.py', 'shared_helper.py']));
  });

  it('applyPluginDependencies drops nothing when nothing is checked', () => {
    expect(applyPluginDependencies(depTree, new Set())).toEqual(new Set());
  });

  it('resolveRootPluginPaths folds a plugin\'s dependency into the resolved set', () => {
    const { paths } = resolveRootPluginPaths(depTree, ['mybalance']);
    expect(paths.sort()).toEqual(['iouonegirl.py', 'mybalance.py']);
  });

  it('partitionCheckedPaths folds dependencies in when a tree is given', () => {
    const { selectable, dropped } = partitionCheckedPaths(['mybalance.py'], depTree);
    expect([...selectable].sort()).toEqual(['iouonegirl.py', 'mybalance.py']);
    expect(dropped).toEqual([]);
  });

  it('partitionCheckedPaths matches the old behaviour when no tree is given', () => {
    const { selectable } = partitionCheckedPaths(['mybalance.py']);
    expect([...selectable]).toEqual(['mybalance.py']);
  });
});
