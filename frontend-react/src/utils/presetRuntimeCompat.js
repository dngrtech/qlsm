import { runtimeLabel } from '../constants/runtimes';

// TEMPORARY (P1): a mismatched preset is simply not selectable. P5 replaces
// this with the real gate -- load the runtime-agnostic config, strip the
// incompatible plugins, and offer compatible replacements. Until that exists,
// blocking is the only honest option: minqlx plugins do not run on
// minqlxtended, and loading them would break the instance silently.

export const isPresetRuntimeCompatible = (preset, host) => {
  if (!host) return true; // No host chosen yet -- nothing to compare against.
  return runtimeLabel(preset?.runtime) === runtimeLabel(host?.runtime);
};

export const presetRuntimeMismatchMessage = (preset, host) => {
  if (isPresetRuntimeCompatible(preset, host)) return '';
  const presetRuntime = runtimeLabel(preset?.runtime);
  const hostRuntime = runtimeLabel(host?.runtime);
  return `This is a ${presetRuntime} preset and this host runs ${hostRuntime}. `
    + 'Plugins are not interchangeable between the two runtimes, so it cannot be loaded here.';
};
