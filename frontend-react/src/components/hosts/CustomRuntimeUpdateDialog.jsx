import React, { useEffect, useRef, useState } from 'react';
import { Dialog, DialogBackdrop, DialogPanel, DialogTitle } from '@headlessui/react';
import { Loader2 } from 'lucide-react';
import { getCustomRuntimeUpdate, startCustomRuntimeUpdate } from '../../services/customRuntimeUpdateApi';

const errorMessage = (error, fallback) => error?.response?.data?.error?.message || error?.message || fallback;

function ReleaseSummary({ title, release }) {
  return (
    <div className="min-w-0 rounded-lg border border-[var(--surface-border)] bg-[var(--surface-elevated)] p-3">
      <dt className="text-sm font-medium text-theme-secondary">{title}</dt>
      <dd className="mt-1 text-sm text-theme-primary">
        {release.build
          ? <>Build <span className="font-mono">{release.build}</span></>
          : 'Build unavailable'}
        <span className="mt-1 block break-all text-xs">
          SHA-256 <code>{release.sha256}</code>
        </span>
      </dd>
    </div>
  );
}

export default function CustomRuntimeUpdateDialog({ host, onClose, onStarted }) {
  const [preview, setPreview] = useState(null);
  const [previewAttempt, setPreviewAttempt] = useState(0);
  const [action, setAction] = useState('update');
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const submitInFlight = useRef(false);
  const hostId = host.id;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setPreview(null);
    setError(null);
    getCustomRuntimeUpdate(hostId)
      .then((data) => {
        if (cancelled) return;
        setPreview(data);
        setAction(!data.target && data.rollback ? 'rollback' : 'update');
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err, 'Could not load the Custom runtime preview.'));
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [hostId, previewAttempt]);

  const pinnedRelease = preview?.current ?? (host.runtime_release_sha256
    ? { build: host.runtime_build, sha256: host.runtime_release_sha256 }
    : null);
  const selectedRelease = action === 'rollback' ? preview?.rollback : preview?.target;
  const canReload = !loading && (preview ? !preview.eligibility.enabled : Boolean(error));
  const canConfirm = preview?.eligibility.enabled && preview.fingerprint && selectedRelease && !loading && !submitting;
  const hasRunningInstances = preview?.instances.some(({ status }) => status?.toLowerCase() === 'running');
  const provider = preview?.current?.label || host.runtime_provider_label || host.runtime_provider_id;

  const handleConfirm = async () => {
    if (!canConfirm || submitInFlight.current) return;
    submitInFlight.current = true;
    setSubmitting(true);
    setError(null);

    try {
      await startCustomRuntimeUpdate(hostId, {
        fingerprint: preview.fingerprint,
        target_sha256: selectedRelease.sha256,
        action,
      });
    } catch (err) {
      if (err.response?.status === 409) setPreview(null);
      setError(errorMessage(err, 'Could not queue this Custom runtime change.'));
      return;
    } finally {
      submitInFlight.current = false;
      setSubmitting(false);
    }
    onStarted(action);
  };

  return (
    <Dialog open onClose={() => { if (!submitInFlight.current) onClose(); }} className="relative z-50">
      <DialogBackdrop className="modal-backdrop" />
      <div className="fixed inset-0 overflow-y-auto p-4">
        <div className="flex min-h-full items-center justify-center">
          <DialogPanel className="modal-panel w-full max-w-xl p-5 sm:p-6">
            <DialogTitle className="heading-display text-lg text-theme-primary">Update Custom runtime</DialogTitle>
            <p className="mt-1 text-sm text-theme-secondary">{host.name}</p>
            {provider && <p className="mt-2 text-base font-semibold text-theme-primary">{provider}</p>}

            {loading && (
              <p role="status" className="mt-4 flex items-center gap-2 text-sm text-theme-secondary">
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Loading release preview…
              </p>
            )}

            {preview && (
              <div className="mt-4 space-y-4">
                {preview.eligibility.reason && (
                  <p role="status" className="text-sm text-theme-secondary">{preview.eligibility.reason}</p>
                )}
                {!preview.target && preview.eligibility.enabled && (
                  <p role="status" className="text-sm text-theme-secondary">
                    {preview.reason || 'An approved update is currently unavailable.'}
                  </p>
                )}

                {preview.eligibility.enabled && (preview.target || preview.rollback) && (
                  <fieldset className="space-y-2 text-sm text-theme-primary" disabled={submitting}>
                    <legend className="mb-1 font-medium">Choose a release</legend>
                    {preview.target && (
                      <label className="flex items-center gap-2">
                        <input type="radio" name="custom-runtime-release" checked={action === 'update'}
                          onChange={() => setAction('update')} />
                        Approved update ({preview.target.build})
                      </label>
                    )}
                    {preview.rollback && (
                      <label className="flex items-center gap-2">
                        <input type="radio" name="custom-runtime-release" checked={action === 'rollback'}
                          onChange={() => setAction('rollback')} />
                        Previous release ({preview.rollback.build})
                      </label>
                    )}
                  </fieldset>
                )}

                {(pinnedRelease || selectedRelease) && (
                  <dl className="grid gap-2 sm:grid-cols-2">
                    {pinnedRelease && <ReleaseSummary title="Pinned release" release={pinnedRelease} />}
                    {selectedRelease && <ReleaseSummary title="Selected release" release={selectedRelease} />}
                  </dl>
                )}

                <section aria-label="Affected instances">
                  <h3 className="text-sm font-medium text-theme-primary">Affected instances</h3>
                  {preview.instances.length > 0 ? (
                    <ul className="mt-1 list-inside list-disc text-sm text-theme-secondary">
                      {preview.instances.map(({ id, name, status }) => (
                        <li key={id}>
                          {name} <span className="capitalize">({status?.toLowerCase() || 'unknown'})</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-1 text-sm text-theme-secondary">This host has no instances.</p>
                  )}
                </section>

                {preview.eligibility.enabled && selectedRelease && (
                  <div className="space-y-1 text-sm text-theme-secondary">
                    {hasRunningInstances && (
                      <p className="font-medium text-[var(--accent-warning)]">
                        Plan for downtime while QLSM restarts running instances and verifies readiness.
                      </p>
                    )}
                    <p>Stopped instances stay stopped. Instance configs, plugins, and data are preserved.</p>
                    <p>QLSM automatically attempts to restore the pinned release and original instance states if the change fails.</p>
                  </div>
                )}
              </div>
            )}

            {error && <p role="alert" className="mt-4 text-sm text-[var(--accent-danger)]">{error}</p>}

            <div className="mt-5 flex flex-wrap justify-end gap-2">
              {canReload && (
                <button type="button" className="btn btn-secondary"
                  onClick={() => setPreviewAttempt((attempt) => attempt + 1)}>
                  Reload preview
                </button>
              )}
              <button type="button" className="btn btn-secondary" onClick={onClose} disabled={submitting}>Cancel</button>
              <button type="button" className="btn btn-primary" onClick={handleConfirm} disabled={!canConfirm}>
                {submitting && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                Confirm {action}
              </button>
            </div>
          </DialogPanel>
        </div>
      </div>
    </Dialog>
  );
}
