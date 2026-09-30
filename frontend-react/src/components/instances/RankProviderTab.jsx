import React, { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { getRankProvider, saveRankProvider, deleteRankProvider } from '../../services/api';

const PROVIDERS = [
  { value: '', label: 'None' },
  { value: 'qlstats', label: 'qlstats' },
  { value: 'slipgate', label: 'Slipgate' },
  { value: 'elo_service', label: 'Thunderdome elo-service' },
];

// qlstats has no auth; every other provider needs a credential.
const NEEDS_API_KEY = { qlstats: false, slipgate: true, elo_service: true };

const BASE_URL_PLACEHOLDER = {
  qlstats: 'https://qlstats.net',
  slipgate: 'https://slipgate.gg/api/v1',
  elo_service: 'http://host:5002',
};

const EMPTY = {
  provider_type: '', base_url: '', api_key: '', game_type: '',
  extra: {}, enabled: true,
};

export default function RankProviderTab({ instanceId }) {
  const [form, setForm] = useState(EMPTY);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  // Save with an unloaded (empty) form would delete the real config.
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadFailed(false);
    getRankProvider(instanceId)
      .then((config) => {
        if (cancelled) return;
        setForm(config ? { ...EMPTY, ...config, extra: config.extra || {} } : EMPTY);
      })
      .catch(() => {
        if (cancelled) return;
        setLoadFailed(true);
        setError('Could not load the rank provider settings. Reopen this tab to retry.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [instanceId]);

  const update = useCallback((field, value) => {
    setForm((previous) => ({ ...previous, [field]: value }));
    setStatus(null);
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setStatus(null);
    try {
      if (!form.provider_type) {
        await deleteRankProvider(instanceId);
        setForm(EMPTY);
        setStatus('Rank provider removed.');
      } else {
        const saved = await saveRankProvider(instanceId, form);
        setForm({ ...EMPTY, ...saved, extra: saved.extra || {} });
        setStatus('Rank provider saved.');
      }
    } catch (err) {
      setError(err?.error?.message || 'Could not save the rank provider settings.');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-[var(--text-secondary)] italic p-4">Loading…</p>;
  }

  const needsKey = NEEDS_API_KEY[form.provider_type];

  return (
    <div className="p-4 space-y-4 max-w-xl">
      <p className="text-sm text-[var(--text-secondary)]">
        Show each connected player&apos;s rating in this instance&apos;s Live Status table.
      </p>

      <label className="block">
        <span className="block text-xs uppercase tracking-wide text-[var(--text-secondary)] mb-1">
          Provider
        </span>
        <select
          className="w-full bg-[var(--surface-base)] border border-[var(--surface-border)] rounded px-3 py-2 text-sm"
          value={form.provider_type}
          onChange={(e) => update('provider_type', e.target.value)}
        >
          {PROVIDERS.map((p) => (
            <option key={p.value} value={p.value}>{p.label}</option>
          ))}
        </select>
      </label>

      {form.provider_type && (
        <>
          <label className="block">
            <span className="block text-xs uppercase tracking-wide text-[var(--text-secondary)] mb-1">
              Base URL
            </span>
            <input
              type="text"
              className="w-full bg-[var(--surface-base)] border border-[var(--surface-border)] rounded px-3 py-2 text-sm font-mono"
              value={form.base_url || ''}
              placeholder={BASE_URL_PLACEHOLDER[form.provider_type]}
              onChange={(e) => update('base_url', e.target.value)}
            />
          </label>

          {needsKey && (
            <label className="block">
              <span className="block text-xs uppercase tracking-wide text-[var(--text-secondary)] mb-1">
                {form.provider_type === 'slipgate' ? 'Upload token' : 'API key'}
              </span>
              <input
                type="text"
                className="w-full bg-[var(--surface-base)] border border-[var(--surface-border)] rounded px-3 py-2 text-sm font-mono"
                value={form.api_key || ''}
                onChange={(e) => update('api_key', e.target.value)}
              />
            </label>
          )}

          {form.provider_type === 'qlstats' && (
            <label className="block">
              <span className="block text-xs uppercase tracking-wide text-[var(--text-secondary)] mb-1">
                Rating system
              </span>
              <select
                className="w-full bg-[var(--surface-base)] border border-[var(--surface-border)] rounded px-3 py-2 text-sm"
                value={form.extra?.rating_system || 'elo'}
                onChange={(e) => update('extra', { ...form.extra, rating_system: e.target.value })}
              >
                <option value="elo">elo</option>
                <option value="elo_b">elo_b</option>
              </select>
            </label>
          )}

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={!!form.enabled}
              onChange={(e) => update('enabled', e.target.checked)}
            />
            Enabled
          </label>

          <div>
            <button
              type="button"
              className="flex items-center gap-1 text-xs uppercase tracking-wide text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              onClick={() => setAdvancedOpen((open) => !open)}
            >
              {advancedOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              Advanced
            </button>
            {advancedOpen && (
              <label className="block mt-2">
                <span className="block text-xs uppercase tracking-wide text-[var(--text-secondary)] mb-1">
                  Game type override
                </span>
                <input
                  type="text"
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-border)] rounded px-3 py-2 text-sm font-mono"
                  value={form.game_type || ''}
                  placeholder="ffa_auto"
                  onChange={(e) => update('game_type', e.target.value)}
                />
                <span className="block mt-1 text-xs text-[var(--text-secondary)]">
                  Leave blank to follow the server&apos;s current game type. Set this
                  only for providers with their own pool names, such as
                  elo-service&apos;s <code>ffa_auto</code>.
                </span>
              </label>
            )}
          </div>
        </>
      )}

      {error && <p className="text-sm text-red-500">{error}</p>}
      {status && <p className="text-sm text-[var(--accent-primary)]">{status}</p>}

      <button
        type="button"
        onClick={handleSave}
        disabled={saving || loadFailed}
        className="px-4 py-2 rounded bg-[var(--accent-primary)] text-black text-sm font-semibold disabled:opacity-50"
      >
        {saving ? 'Saving…' : 'Save'}
      </button>
    </div>
  );
}
