import { runtimeLabel } from '../constants/runtimes';

// A preset carries the runtime of the host it was saved from. Loading it onto a
// host running the other runtime is allowed -- the backend swaps each untouched
// standard plugin for the target runtime's own version and asks about the rest
// -- but the operator is told before it happens, because it is not a lossless
// load: a plugin this preset modified, or one the target has no version of,
// cannot come across as it is.

export const presetRuntimeMatches = (preset, host) => {
  if (!host) return true; // No host chosen yet -- nothing to compare against.
  return runtimeLabel(preset?.runtime) === runtimeLabel(host?.runtime);
};

export const presetRuntimeStripWarning = (preset, host) => {
  if (presetRuntimeMatches(preset, host)) return '';
  const presetRuntime = runtimeLabel(preset?.runtime);
  const hostRuntime = runtimeLabel(host?.runtime);
  return `Saved from a ${presetRuntime} host; this host runs ${hostRuntime}. `
    + 'Server config loads as-is. Plugins are not interchangeable between the two '
    + `runtimes, so each standard plugin is swapped for ${hostRuntime}'s own version, `
    + "keeping this preset's plugin selection. You will be asked only about plugins "
    + `this preset modified, or that ${hostRuntime} has no version of.`;
};
