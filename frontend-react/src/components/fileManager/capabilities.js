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
  newFileTemplate: () => '',
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
