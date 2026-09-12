// Read/write the owner (qlx_owner in server.cfg) and admins (access.txt lines,
// "steamid|level") for the structured Owner/Admins controls. Mirrors the
// existing sv_hostname <-> server.cfg sync pattern (see serverCfgCvars.js).
import { readCvarFromConfig, upsertCvarInConfig } from './serverCfgCvars';

export const STEAMID64_RE = /^7656119\d{10}$/;

export function readOwnerFromConfig(serverCfgText) {
  return readCvarFromConfig(serverCfgText, 'qlx_owner') || '';
}

export function writeOwnerToConfig(serverCfgText, steamId64) {
  return upsertCvarInConfig(serverCfgText, 'qlx_owner', steamId64 || '');
}
