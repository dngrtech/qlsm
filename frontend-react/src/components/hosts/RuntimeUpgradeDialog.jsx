import React, { useEffect, useState } from 'react';
import { Dialog, DialogBackdrop } from '@headlessui/react';
import { ArrowUpCircle, Loader2 } from 'lucide-react';
import CompatibilityRow from '../presetManager/CompatibilityRow';
import { getRuntimeUpgrade, startRuntimeUpgrade } from '../../services/runtimeUpgradeApi';

// Confirmation (and, when needed, compatibility) dialog for upgrading a host
// from minqlx to minqlxtended. Replaceable rows start ticked, matching the
// preset-load dialog. The backend already treats `auto_accepted` paths as
// accepted, so only the operator's ticks are sent.

const SOURCE_RUNTIME = 'minqlx';
const TARGET_RUNTIME = 'minqlxtended';

const errorMessage = (err, fallback) => err?.response?.data?.error?.message || err?.message || fallback;
const isReplaceable = (row) => row.kind === 'replaceable' || Boolean(row.replacement);
// Plugins the instance has enabled first: those are what can break a running
// server. Disabled ones follow, toned down by CompatibilityRow. Stable sort, so
// each group keeps the backend's path order.
const enabledFirst = (rows) => [...rows].sort(
  (a, b) => Number(!a.originally_checked) - Number(!b.originally_checked));

const tickedDefaults = (instances) => {
  const ticked = {};
  instances.forEach((inst) => {
    ticked[inst.instance_id] = new Set((inst.stripped || []).filter(isReplaceable).map((row) => row.path));
  });
  return ticked;
};

function RuntimeUpgradeDialog({ isOpen, host, onClose, onStarted }) {
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [plan, setPlan] = useState(null);
  const [ticked, setTicked] = useState({});

  const hostId = host?.id;
  const hostName = host?.name || 'this host';

  useEffect(() => {
    if (!isOpen || hostId == null) return undefined;
    let cancelled = false;
    setPlan(null);
    setError(null);
    setLoading(true);
    getRuntimeUpgrade(hostId)
      .then((data) => {
        if (cancelled) return;
        setPlan(data);
        setTicked(tickedDefaults(data.instances || []));
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err, 'Could not check this host for upgrade.'));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [isOpen, hostId]);

  const instancesWithRows = (plan?.instances || []).filter((inst) => (inst.stripped || []).length > 0);

  const toggle = (instanceId, path) => {
    setTicked((prev) => {
      const next = new Set(prev[instanceId] || []);
      if (next.has(path)) next.delete(path); else next.add(path);
      return { ...prev, [instanceId]: next };
    });
  };

  const handleUpgrade = async () => {
    if (!plan) return;
    const accepted = {};
    (plan.instances || []).forEach((inst) => {
      accepted[inst.instance_id] = (inst.stripped || [])
        .filter((row) => isReplaceable(row) && ticked[inst.instance_id]?.has(row.path))
        .map((row) => row.path);
    });
    setSubmitting(true);
    setError(null);
    try {
      await startRuntimeUpgrade(hostId, { fingerprint: plan.fingerprint, accepted_replacements: accepted });
      if (onStarted) onStarted(hostId);
      onClose();
    } catch (err) {
      setError(errorMessage(err, 'Could not start the upgrade.'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={isOpen} as="div" className="relative z-[70]" onClose={onClose}>
      <DialogBackdrop transition className="modal-backdrop fixed inset-0 transition data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0" />
      <div className="fixed inset-0 overflow-y-auto">
        <div className="flex min-h-full items-center justify-center p-4 text-center">
          <Dialog.Panel transition className="modal-panel w-full max-w-lg transform overflow-hidden p-6 text-left align-middle transition-all data-[enter]:ease-out data-[enter]:duration-300 data-[leave]:ease-in data-[leave]:duration-200 data-[closed]:opacity-0 data-[closed]:translate-y-4 data-[closed]:scale-95">
            <div className="accent-line-top" />

            <Dialog.Title as="h3" className="font-display text-lg font-semibold tracking-wide text-theme-primary">
              Upgrade to minqlxtended
            </Dialog.Title>

            {loading && (
              <p className="mt-3 flex items-center gap-2 text-sm text-theme-secondary">
                <Loader2 className="h-4 w-4 animate-spin" /> Checking plugin compatibility...
              </p>
            )}

            {plan && instancesWithRows.length === 0 && (
              <p className="mt-2 text-sm text-theme-secondary">
                Running instances on {hostName} will stop during the upgrade and start again.
                Stopped instances stay stopped. If the upgrade fails, QLSM restores minqlx and the
                original instance states. Interrupted recovery continues when the host is reachable.
              </p>
            )}

            {plan && instancesWithRows.length > 0 && (
              <>
                <p className="mt-2 text-sm text-theme-secondary">
                  Running instances on {hostName} will stop during the upgrade and start again.
                  Stopped instances stay stopped. If the upgrade fails, QLSM restores minqlx and the
                  original instance states. Interrupted recovery continues when the host is reachable.
                </p>
                <p className="mt-2 text-sm text-theme-secondary">
                  Standard plugins are swapped for {TARGET_RUNTIME}&apos;s own version automatically.
                  Listed below is what that leaves: files that can&apos;t run on {TARGET_RUNTIME} and
                  aren&apos;t the standard copy, so QLSM won&apos;t decide for you.
                </p>
                <div className="mt-4 max-h-[50vh] space-y-4 overflow-y-auto pr-1 scrollbar-thin">
                  {instancesWithRows.map((inst) => (
                    <section key={inst.instance_id} aria-label={inst.instance_name}>
                      <h4 className="mb-2 text-sm font-semibold text-theme-primary">{inst.instance_name}</h4>
                      <ul className="space-y-2">
                        {enabledFirst(inst.stripped).map((row) => (
                          <CompatibilityRow
                            key={row.path}
                            entry={row}
                            sourceNoun="instance"
                            showEnablement
                            sourceRuntime={SOURCE_RUNTIME}
                            targetRuntime={TARGET_RUNTIME}
                            checked={Boolean(ticked[inst.instance_id]?.has(row.path))}
                            onToggle={() => toggle(inst.instance_id, row.path)}
                          />
                        ))}
                      </ul>
                    </section>
                  ))}
                </div>
              </>
            )}

            {error && (
              <p role="alert" className="mt-3 text-sm text-[var(--accent-danger)]">{error}</p>
            )}

            <div className="mt-6 flex justify-end gap-3">
              <button type="button" className="btn btn-secondary" onClick={onClose} disabled={submitting}>
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleUpgrade}
                disabled={!plan || loading || submitting}
              >
                {submitting
                  ? <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                  : <ArrowUpCircle className="mr-1 h-4 w-4" />}
                Upgrade
              </button>
            </div>
          </Dialog.Panel>
        </div>
      </div>
    </Dialog>
  );
}

export default RuntimeUpgradeDialog;
