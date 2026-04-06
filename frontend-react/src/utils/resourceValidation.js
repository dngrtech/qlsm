// RFC 1123 compliant hostname validation
export const HOST_NAME_MAX_LENGTH = 20;
export const INSTANCE_NAME_MAX_LENGTH = 40;
export const HOST_NAME_PATTERN = /^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$/;
// Instance names also allow spaces (unlike host names)
export const INSTANCE_NAME_PATTERN = /^[a-zA-Z0-9]([a-zA-Z0-9- ]*[a-zA-Z0-9])?$/;

export function validateHostName(name) {
  if (typeof name !== 'string') return 'Name must be a string';
  const trimmed = name.trim();
  if (!trimmed) return 'Name cannot be empty';
  if (trimmed.length > HOST_NAME_MAX_LENGTH) return `Name cannot exceed ${HOST_NAME_MAX_LENGTH} characters`;
  if (!HOST_NAME_PATTERN.test(trimmed)) return 'Name must start and end with a letter or number, and can only contain letters, numbers, and hyphens';
  return null;
}

export function validateInstanceName(name) {
  if (typeof name !== 'string') return 'Name must be a string';
  const trimmed = name.trim();
  if (!trimmed) return 'Name cannot be empty';
  if (trimmed.length > INSTANCE_NAME_MAX_LENGTH) return `Name cannot exceed ${INSTANCE_NAME_MAX_LENGTH} characters`;
  if (!INSTANCE_NAME_PATTERN.test(trimmed)) return 'Name must start and end with a letter or number, and can only contain letters, numbers, hyphens, and spaces';
  return null;
}
