import { runtimeLabel } from '../constants/runtimes';

// A preset carries the runtime of the host it was saved from. Loading it onto a
// host running the other runtime is allowed -- the backend strips the plugins
// that cannot run there and offers same-named replacements -- but the operator
// is told before it happens, because it is not a lossless load.

export const presetRuntimeMatches = (preset, host) => {
  if (!host) return true; // No host chosen yet -- nothing to compare against.
  return runtimeLabel(preset?.runtime) === runtimeLabel(host?.runtime);
};

export const presetRuntimeStripWarning = (preset, host) => {
  if (presetRuntimeMatches(preset, host)) return '';
  const presetRuntime = runtimeLabel(preset?.runtime);
  const hostRuntime = runtimeLabel(host?.runtime);
  return `Saved from a ${presetRuntime} host; this host runs ${hostRuntime}. `
    + 'Server config loads as-is, but plugins are not interchangeable between the two '
    + "runtimes — only plugins matching this runtime's shipped versions are kept. "
    + 'You will see the full list first, with a replacement offered where one exists.';
};
