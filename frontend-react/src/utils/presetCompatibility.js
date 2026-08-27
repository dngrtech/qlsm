// Applying the operator's answer to the compatibility gate.
//
// The backend has already stripped everything that cannot run on the target
// runtime, swapped in the target's own copy of every stock plugin the preset
// never touched, and reported only the strips that still need a decision.

const compatOf = (presetData) => presetData?.compatibility || null;

// The stripped entries the operator can actually do something about.
export function strippedWithReplacements(presetData) {
  const compat = compatOf(presetData);
  if (!compat) return [];
  return (compat.stripped || []).filter((entry) => entry.replacement);
}

// Replacements the backend applied without asking: untouched stock plugins
// swapped for the target runtime's own copy of the same file. These are not
// in `stripped` and never reach the dialog, but they still have to travel to
// the draft as accepted replacements -- _apply_runtime_filter deletes the
// source file and only writes back what it is handed. This must be included
// on the no-dialog path too, where `stripped` is empty and the load runs
// straight through.
export function autoAcceptedPaths(presetData) {
  return compatOf(presetData)?.auto_accepted || [];
}

// What to send to the draft: everything swapped automatically, plus whatever
// the operator ticked in the dialog.
export function combineAcceptedPaths(presetData, tickedPaths = []) {
  return Array.from(new Set([...autoAcceptedPaths(presetData), ...(tickedPaths || [])]));
}

export function mergeReplacements(presetData, acceptedPaths = []) {
  const compat = compatOf(presetData);
  if (!compat) return presetData;

  const offered = compat.replacements || {};
  const accepted = (acceptedPaths || []).filter(
    (path) => Object.prototype.hasOwnProperty.call(offered, path)
  );
  if (accepted.length === 0) return { ...presetData };

  // Accepting a replacement carries the FILE over. It does not enable the
  // plugin: enablement belongs to the preset's own recorded selection, which
  // the backend has already applied to checked_plugins (an auto-swapped
  // plugin keeps its tick there and is absent from `stripped` entirely). The
  // one tick this restores is a reported plugin the preset did have enabled,
  // which the backend removed precisely because its fate was undecided until
  // now. Adding every accepted path unconditionally is what let ticking the
  // dialog's rows switch on plugins the preset never had enabled.
  const originallyChecked = new Set(
    (compat.stripped || [])
      .filter((entry) => entry.originally_checked)
      .map((entry) => entry.path)
  );
  const scripts = { ...(presetData.scripts || {}) };
  const hadSelection = Array.isArray(presetData.checked_plugins);
  const checked = new Set(hadSelection ? presetData.checked_plugins : []);
  accepted.forEach((path) => {
    scripts[path] = offered[path];
    if (originallyChecked.has(path)) checked.add(path);
  });

  // A preset that pre-dates checked_plugins.json reads as null, and null is not
  // an empty selection -- applyPresetData()'s `checked_plugins != null` branch
  // keeps the current defaults for it. Auto-accepted replacements now make
  // `accepted` non-empty on essentially every cross-runtime load, so returning
  // Array.from(checked) unconditionally here would hand every legacy preset a
  // deliberate-looking empty selection and load it with no plugins at all.
  return hadSelection
    ? { ...presetData, scripts, checked_plugins: Array.from(checked) }
    : { ...presetData, scripts };
}
