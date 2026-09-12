import { useEffect, useRef } from 'react';
import { fetchCvarCatalog } from '../services/cvarCatalogApi';
import { setCvarCatalog, registerPluginCvarProvider } from '../codemirror-lang-qlcfg';
import { collectPluginCvars } from '../components/fileManager/pluginManifest';

// Feeds the config editor's autocomplete for one screen: the engine cvar
// catalog from the backend, and the qlx_ cvars of the plugins that this
// particular server carries (enabled ones first).
//
// Pass the Plugins tab's own file tree and the set of enabled plugin paths -
// the tree nodes already carry each plugin's manifest, so nothing extra is
// fetched and a freshly uploaded plugin shows up as soon as the tree reloads.
export function useCvarAutocomplete({ pluginTree, checkedPlugins, enabled = true } = {}) {
  const latest = useRef({ pluginTree, checkedPlugins });
  latest.current = { pluginTree, checkedPlugins };

  useEffect(() => {
    if (!enabled) return undefined;
    let active = true;
    // Promise.resolve() so a transport that throws synchronously (a stubbed
    // api client in a component test, for instance) lands in the catch below
    // instead of taking the whole screen down.
    Promise.resolve().then(fetchCvarCatalog)
      .then((catalog) => { if (active) setCvarCatalog(catalog); })
      // Autocomplete without the engine catalog still offers plugin cvars and
      // app-managed ones; a failed fetch must not break the editor.
      .catch(() => {});
    return () => { active = false; };
  }, [enabled]);

  useEffect(() => {
    if (!enabled) return undefined;
    return registerPluginCvarProvider(() => collectPluginCvars(
      latest.current.pluginTree || [],
      latest.current.checkedPlugins || [],
    ));
  }, [enabled]);
}

export default useCvarAutocomplete;
