import { describe, expect, it } from 'vitest';

import {
  PLUGIN_HINT_TEXT,
  folderHasPluginFiles,
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
