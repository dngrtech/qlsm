import { useCallback, useEffect, useMemo, useState } from 'react';
import { fetchCvarCatalog } from '../../services/cvarCatalogApi';
import {
  cvarCompletionOptions,
  commandCompletionOptions,
  getCvarCatalog,
  setCvarCatalog,
} from '../../codemirror-lang-qlcfg';

const MAX_SUGGESTIONS = 8;
const CVAR_ARG_COMMANDS = new Set(['set', 'seta', 'sets', 'setu', 'reset', 'toggle']);

function describe(name) {
  const lower = name.toLowerCase();
  const { cvars, commands } = getCvarCatalog();
  const entry = cvars.find(cvar => cvar.name.toLowerCase() === lower)
    || commands.find(command => command.name.toLowerCase() === lower);
  return entry?.description || '';
}

// The config editor floats app-managed cvars to the top as a warning; at the
// console they're rarely what you want, so rank prefix matches first and
// app-managed ones last. Array.sort is stable, so ties keep catalog order.
function rank(options, prefix) {
  const lower = prefix.toLowerCase();
  const score = (option) => (option.label.toLowerCase().startsWith(lower) ? 0 : 2)
    + (option.detail === 'app-managed' ? 1 : 0);
  return [...options].sort((left, right) => score(left) - score(right));
}

function toSuggestion(option) {
  return { label: option.label, detail: option.detail, description: describe(option.label) };
}

// A bare first word in RCON either runs a command or, for a cvar name, prints
// its current value, so both are offered there; after set-style commands only
// cvars make sense, and anything later on the line (values, say text) gets none.
export function rconSuggestions(value) {
  const firstWord = value.match(/^\s*(\S+)$/);
  if (firstWord) {
    const prefix = firstWord[1];
    const merged = [...commandCompletionOptions(prefix), ...cvarCompletionOptions(prefix)];
    const seen = new Set();
    const unique = merged.filter((option) => {
      const key = option.label.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
    return { from: value.length - prefix.length, items: rank(unique, prefix).slice(0, MAX_SUGGESTIONS).map(toSuggestion) };
  }

  const cvarArg = value.match(/^\s*(\S+)\s+(\S+)$/);
  if (cvarArg && CVAR_ARG_COMMANDS.has(cvarArg[1].toLowerCase())) {
    const prefix = cvarArg[2];
    return {
      from: value.length - prefix.length,
      items: rank(cvarCompletionOptions(prefix), prefix).slice(0, MAX_SUGGESTIONS).map(toSuggestion),
    };
  }

  return { from: value.length, items: [] };
}

export function useRconAutocomplete({ value, setValue, enabled }) {
  const [catalogVersion, setCatalogVersion] = useState(0);
  const [dismissedFor, setDismissedFor] = useState(null);
  const [activeIndex, setActiveIndex] = useState(-1);

  useEffect(() => {
    if (!enabled) return undefined;
    let active = true;
    Promise.resolve().then(fetchCvarCatalog)
      .then((catalog) => {
        if (!active) return;
        setCvarCatalog(catalog);
        setCatalogVersion(version => version + 1);
      })
      // No catalog just means no suggestions; the console must keep working.
      .catch(() => {});
    return () => { active = false; };
  }, [enabled]);

  const { from, items } = useMemo(
    () => (enabled ? rconSuggestions(value) : { from: 0, items: [] }),
    // catalogVersion re-runs the lookup once the catalog arrives.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [enabled, value, catalogVersion],
  );

  // Hide the list when the only suggestion is exactly what's already typed.
  const exactOnly = items.length === 1 && value.slice(from).toLowerCase() === items[0].label.toLowerCase();
  const open = items.length > 0 && !exactOnly && dismissedFor !== value;

  useEffect(() => { setActiveIndex(-1); }, [value]);

  const accept = useCallback((index) => {
    const item = items[index];
    if (!item) return;
    const next = `${value.slice(0, from)}${item.label} `;
    setValue(next);
    setDismissedFor(next);
  }, [from, items, setValue, value]);

  // Returns true when the key was consumed by the suggestion list.
  const handleKeyDown = useCallback((event) => {
    if (!open) return false;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex(index => (index + 1) % items.length);
      return true;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex(index => (index <= 0 ? items.length - 1 : index - 1));
      return true;
    }
    if (event.key === 'Tab') {
      event.preventDefault();
      accept(activeIndex >= 0 ? activeIndex : 0);
      return true;
    }
    // Enter only picks a suggestion the user explicitly moved to; otherwise it
    // falls through and sends what was typed.
    if (event.key === 'Enter' && activeIndex >= 0) {
      event.preventDefault();
      accept(activeIndex);
      return true;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      setDismissedFor(value);
      return true;
    }
    return false;
  }, [accept, activeIndex, items.length, open, value]);

  // For values the user didn't type (history recall), so the list doesn't
  // pop up and capture the next Up/Down press.
  const setValueQuietly = useCallback((next) => {
    setDismissedFor(next);
    setValue(next);
  }, [setValue]);

  return { open, items: open ? items : [], activeIndex, accept, handleKeyDown, setValueQuietly };
}
