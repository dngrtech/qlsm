const NEW_SCRIPT_TEMPLATE = `"""
minqlx plugin
"""

import minqlx


class MyPlugin(minqlx.Plugin):
    def __init__(self):
        super().__init__()
        # Add hooks and commands here
`;

export const CONFIG_CAPS = {
  canCreate: true,
  canUpload: true,
  canDelete: true,
  canRename: true,
  canFolders: true,
  canCreateFolder: true,
  canCheckEnable: false,
  canValidate: false,
  allowedExtensions: ['.cfg', '.txt', '.ent'],
  newFileTemplate: () => '',
  protectedFiles: ['server.cfg', 'mappool.txt', 'access.txt', 'workshop.txt'],
  reservedFolderNames: ['scripts', 'factories'],
};

export const PLUGIN_CAPS = {
  canCreate: true,
  canUpload: true,
  canDelete: true,
  canRename: true,
  canFolders: true,
  canCreateFolder: true,
  canCheckEnable: true,
  canValidate: true,
  allowedExtensions: ['.py', '.txt', '.so'],
  newFileTemplate: (filename) => (filename.endsWith('.py') ? NEW_SCRIPT_TEMPLATE : ''),
  protectedFiles: [],
  reservedFolderNames: [],
};

export const FACTORY_CAPS = {
  canCreate: true,
  canUpload: true,
  canDelete: true,
  canRename: true,
  canFolders: false,
  canCreateFolder: false,
  canCheckEnable: true,
  canValidate: false,
  allowedExtensions: ['.factories'],
  newFileTemplate: () => '{\n  \n}',
  protectedFiles: [],
  reservedFolderNames: [],
};
