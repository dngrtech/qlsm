import apiClient from './api';

// The catalog of engine/server cvars and console commands the config editor
// suggests. It is generated data served by the backend
// (ui/data/ql_cvar_catalog.json), not part of the frontend bundle, so it can
// be regenerated against a newer QLDS dump without rebuilding the UI.
//
// Fetched once per page load: it is a few hundred KB of static data and every
// editor in the app wants the same copy.
let pending = null;

export function fetchCvarCatalog() {
  if (!pending) {
    pending = apiClient.get('/cvar-catalog')
      .then(response => response.data.data)
      .catch(error => {
        pending = null; // let a later editor try again
        throw error;
      });
  }
  return pending;
}

export function resetCvarCatalogCache() {
  pending = null;
}
