// Applying the operator's answer to the compatibility gate.
//
// The backend has already stripped everything that cannot run on the target
// runtime and listed a same-named replacement where one exists. Nothing is
// swapped in silently: this runs only over the paths the operator ticked.

const compatOf = (presetData) => presetData?.compatibility || null;

// The stripped entries the operator can actually do something about.
export function strippedWithReplacements(presetData) {
  const compat = compatOf(presetData);
  if (!compat) return [];
  return (compat.stripped || []).filter((entry) => entry.replacement);
}

// Which of those the dialog should start pre-accepted. `stripped` reports
// every file the preset's own scripts folder has, which itself is seeded
// from the ENTIRE default catalog of the preset's own (source) runtime
// before the preset's actual files are overlaid on top -- most entries were
// never part of what the operator actually had enabled (see
// ui/preset_compat.py's apply_compatibility for why). Defaulting every
// offered replacement to checked would silently
// re-enable the runtime's entire default plugin set on confirm regardless
// of the preset's real selection, so only a plugin the backend flagged
// `originally_checked` starts ticked -- everything else stays an opt-in
// the operator ticks themselves.
export function defaultAcceptedReplacementPaths(presetData) {
  return strippedWithReplacements(presetData)
    .filter((entry) => entry.originally_checked)
    .map((entry) => entry.path);
}

export function mergeReplacements(presetData, acceptedPaths = []) {
  const compat = compatOf(presetData);
  if (!compat) return presetData;

  const offered = compat.replacements || {};
  const accepted = (acceptedPaths || []).filter(
    (path) => Object.prototype.hasOwnProperty.call(offered, path)
  );
  if (accepted.length === 0) return { ...presetData };

  const scripts = { ...(presetData.scripts || {}) };
  const checked = new Set(presetData.checked_plugins || []);
  accepted.forEach((path) => {
    scripts[path] = offered[path];
    checked.add(path);
  });

  return { ...presetData, scripts, checked_plugins: Array.from(checked) };
}
