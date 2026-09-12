import React, { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, Crown, ExternalLink, RotateCw, ShieldPlus } from 'lucide-react';
import { createOperator, getOperators } from '../../services/api';
import { setOperatorsCache } from '../../utils/operatorsCache';
import { readOwnerFromConfig, writeOwnerToConfig } from '../../utils/operatorConfigSync';
import OperatorCombobox from './OperatorCombobox';
import AdminRow from './AdminRow';
import AddOperatorModal from './AddOperatorModal';
import useInstanceAdmins from './useInstanceAdmins';

// Owner comes from qlx_owner in server.cfg (minqlx reads the cvar). Admin
// levels live in the instance's minqlx Redis database; QLSM stores its own
// list per instance and pushes it on save. `instanceId` is null wherever there
// is no running server to read -- Add Instance and the preset pages.
function OwnerAdminEditor({
  serverCfgContent,
  onServerCfgChange,
  instanceId = null,
  visible = true,
  adminEntries = null,
  onAdminEntriesChange,
  onAdminEntriesLoaded,
}) {
  const [operators, setOperators] = useState([]);
  const [pendingAdmin, setPendingAdmin] = useState('');
  const [pendingLevel, setPendingLevel] = useState('5');
  // The admin row whose SteamID is being added to the directory, or null.
  const [directoryRow, setDirectoryRow] = useState(null);

  const applyOperators = (data) => {
    const list = data || [];
    setOperators(list);
    setOperatorsCache(list);
  };

  useEffect(() => {
    let cancelled = false;
    getOperators()
      .then((data) => { if (!cancelled) applyOperators(data); })
      .catch(() => { if (!cancelled) setOperators([]); });
    return () => { cancelled = true; };
  }, []);

  // Errors propagate so AddOperatorModal shows them inline and stays open.
  const handleCreateOperator = async (operatorData) => {
    await createOperator(operatorData);
    applyOperators(await getOperators());
  };

  // The parent owns the list: it passes adminEntries in and the hook's mutators
  // call onAdminEntriesChange. Nothing is mirrored upward from an effect -- that
  // loops forever and marks the modal dirty on open.
  // `visible` keeps the SSH read off every modal open: this component stays
  // mounted behind a hidden class to fill the operators cache.
  const {
    rows, loading, liveError, refresh, addAdmin, removeAdmin, adoptAdmin,
  } = useInstanceAdmins({
    instanceId,
    active: Boolean(instanceId) && visible,
    entries: adminEntries,
    onChange: onAdminEntriesChange,
    onLoaded: onAdminEntriesLoaded,
  });

  const operatorsById = useMemo(() => {
    const map = new Map();
    operators.forEach((op) => map.set(op.steam_id64, op));
    return map;
  }, [operators]);

  const ownerSteamId = readOwnerFromConfig(serverCfgContent);
  const handleOwnerChange = (steamId) => onServerCfgChange(writeOwnerToConfig(serverCfgContent, steamId));

  const handleSelectPendingAdmin = (steamId) => {
    setPendingAdmin(steamId);
    const operator = operatorsById.get(steamId);
    if (operator && operator.default_level != null) setPendingLevel(String(operator.default_level));
  };

  const handleAddAdmin = () => {
    if (!pendingAdmin) return;
    addAdmin(pendingAdmin, pendingLevel);
    setPendingAdmin('');
    setPendingLevel('5');
  };

  const assignable = operators.filter((op) => !rows.some((row) => row.steamId === op.steam_id64));

  return (
    <div className="rounded-xl border border-[var(--surface-border)] bg-[var(--surface-elevated)] p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <span className="font-display text-xs font-semibold tracking-wider uppercase text-[var(--text-secondary)]">
          Owner &amp; Admins
        </span>
        <a href="/settings/operators" target="_blank" rel="noopener noreferrer"
           className="flex items-center gap-1 text-xs text-[var(--accent-primary)] hover:underline">
          Manage operators <ExternalLink size={12} />
        </a>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <label className="label-tech mb-1.5 flex items-center gap-1.5">
            <Crown size={14} />
            Owner
          </label>
          <OperatorCombobox
            value={ownerSteamId}
            onChange={handleOwnerChange}
            operators={operators}
            placeholder="Select owner…"
          />
          <p className="mt-1 text-xs text-[var(--text-muted)]">
            Writes <code className="text-[var(--text-secondary)]">qlx_owner</code> in server.cfg. Applies on restart.
          </p>
        </div>

        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <label className="label-tech flex items-center gap-1.5">
              <ShieldPlus size={14} />
              Admins
            </label>
            {instanceId && (
              <button type="button" onClick={refresh} disabled={loading}
                      className="flex items-center gap-1 text-xs text-[var(--accent-primary)] hover:underline disabled:opacity-50">
                <RotateCw size={12} className={loading ? 'animate-spin' : undefined} /> Refresh
              </button>
            )}
          </div>

          {liveError && (
            <div className="mb-2 flex items-start gap-2 rounded-md border border-[var(--accent-warning)]/40 bg-[var(--accent-warning)]/10 px-2.5 py-1.5 text-xs text-[var(--text-secondary)]">
              <AlertTriangle size={14} className="mt-0.5 flex-shrink-0 text-[var(--accent-warning)]" />
              <span>{liveError} Showing the list QLSM has stored; changes apply on the next successful save.</span>
            </div>
          )}

          <div className="flex gap-2">
            <div className="flex-1 min-w-0">
              <OperatorCombobox
                value={pendingAdmin}
                onChange={handleSelectPendingAdmin}
                operators={assignable}
                placeholder="Add operator as admin…"
                allowClear={false}
              />
            </div>
            <div className="w-16 flex-shrink-0">
              <select value={pendingLevel} onChange={(e) => setPendingLevel(e.target.value)} className="input-base">
                {/* No 0: a level-0 entry is "not an admin", and removal is how
                    a level is revoked. The API still accepts 0 so rows imported
                    from legacy "steamid|0" lines stay valid. */}
                {[1, 2, 3, 4, 5].map((lvl) => <option key={lvl} value={lvl}>{lvl}</option>)}
              </select>
            </div>
            <button type="button" onClick={handleAddAdmin} disabled={!pendingAdmin}
                    className="btn btn-secondary flex-shrink-0 px-3">
              Add
            </button>
          </div>

          {rows.length > 0 && (
            <ul className="mt-2 space-y-1">
              {rows.map((row) => (
                <AdminRow
                  key={row.steamId}
                  row={row}
                  operator={operatorsById.get(row.steamId) || null}
                  onRemove={removeAdmin}
                  onAdopt={adoptAdmin}
                  onAddToDirectory={() => setDirectoryRow(row)}
                />
              ))}
            </ul>
          )}

          <p className="mt-1 text-xs text-[var(--text-muted)]">
            Applies the in-game permission level on Save (may take up to ~30s to take effect).
          </p>
        </div>
      </div>

      <AddOperatorModal
        isOpen={directoryRow !== null}
        onClose={() => setDirectoryRow(null)}
        onSubmit={handleCreateOperator}
        initialSteamId={directoryRow?.steamId || ''}
        initialLevel={directoryRow?.level ?? null}
      />
    </div>
  );
}

export default OwnerAdminEditor;
