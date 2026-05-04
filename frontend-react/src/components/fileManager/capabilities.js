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
  canFolders: false,
  canCheckEnable: false,
  canValidate: false,
  allowedExtensions: ['.cfg', '.txt'],
  newFileTemplate: () => '',
  protectedFiles: ['server.cfg', 'mappool.txt', 'access.txt', 'workshop.txt'],
};

export const PLUGIN_CAPS = {
  canCreate: true,
  canUpload: true,
  canDelete: true,
  canRename: true,
  canFolders: true,
  canCheckEnable: true,
  canValidate: true,
  allowedExtensions: ['.py', '.txt', '.so'],
  newFileTemplate: (filename) => (filename.endsWith('.py') ? NEW_SCRIPT_TEMPLATE : ''),
  protectedFiles: [],
};

export const FACTORY_CAPS = {
  canCreate: true,
  canUpload: true,
  canDelete: true,
  canRename: true,
  canFolders: false,
  canCheckEnable: true,
  canValidate: false,
  allowedExtensions: ['.factories'],
  newFileTemplate: () => '{\n  \n}',
  protectedFiles: [],
};
