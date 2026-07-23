import { useCallback, useMemo, useState } from 'react';
import { AlertTriangle, Radio, Target, Terminal } from 'lucide-react';

import RconCommandInput from '../components/rcon/RconCommandInput';
import GlobalRconOutput from '../components/rcon/GlobalRconOutput';
import RconTargetTree from '../components/rcon/RconTargetTree';
import { useFleetRconSession } from '../hooks/useFleetRconSession';
import useGlobalRconPreferences from '../hooks/useGlobalRconPreferences';
import { useHostOrder } from '../hooks/useHostOrder';
import useRconCommandRuns from '../hooks/useRconCommandRuns';
import { useServers } from '../hooks/useServers';
import { useServerStatus } from '../hooks/useServerStatus';
import { buildRconHosts, selectedEligibleTargetRefs } from '../utils/rconTargets';

function runId() {
  return globalThis.crypto?.randomUUID?.() ?? `rcon-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function statusReason(status) {
  if (!status) return 'not ready';
  return status.reason || status.state || 'not ready';
}

// useServers surfaces inventory failures as plain strings; tolerate Error shapes too.
function inventoryErrorText(error) {
  if (typeof error === 'string') return error.trim() || 'unknown error';
  return error?.message || 'unknown error';
}

export default function GlobalRconPage() {
  const { serversData = [], loading, error } = useServers();
  const serverStatuses = useServerStatus();
  const { getOrderedHosts } = useHostOrder();
  const hosts = useMemo(() => getOrderedHosts(serversData), [getOrderedHosts, serversData]);
  const instances = useMemo(() => hosts.flatMap((host) => host.instances ?? []), [hosts]);
  const inventoryReady = !loading && !error;
  const hostOrder = useMemo(() => hosts.map((host) => host.id), [hosts]);
  const preferences = useGlobalRconPreferences({ hosts, instances, hostOrder, inventoryReady });
  const rconHosts = useMemo(() => buildRconHosts(hosts, instances, { hostOrder }), [hosts, instances, hostOrder]);
  const selectedTargets = useMemo(() => rconHosts.flatMap((host) => host.instances)
    .filter((target) => preferences.selectedKeys.has(target.key)), [preferences.selectedKeys, rconHosts]);
  const desiredTargets = useMemo(() => selectedEligibleTargetRefs(
    rconHosts.flatMap((host) => host.instances.filter((target) => target.eligible).map((target) => target.key)),
    preferences.selectedKeys,
  ), [preferences.selectedKeys, rconHosts]);
  const runs = useRconCommandRuns();
  const [activeFilter, setActiveFilter] = useState('all');
  const [targetsOpen, setTargetsOpen] = useState(true);
  const session = useFleetRconSession({
    targets: desiredTargets,
    enabled: inventoryReady,
    onMessage: runs.appendMessage,
    onStatus: runs.applyTargetStatus,
  });
  const runtimeStates = session.statuses;
  const readyTargets = useMemo(() => selectedTargets.filter((target) => target.eligible
    && runtimeStates.get(target.key)?.state === 'ready'), [runtimeStates, selectedTargets]);
  const selectedEligible = selectedTargets.filter((target) => target.eligible);
  // Viewing the ALL tab sends to the whole selection; viewing one instance's
  // tab scopes Send to just that instance, even if others are also selected.
  const activeTarget = activeFilter !== 'all'
    ? selectedTargets.find((target) => target.key === activeFilter) : null;
  const dispatchTargets = useMemo(
    () => (activeFilter === 'all' ? selectedTargets : (activeTarget ? [activeTarget] : [])),
    [activeFilter, activeTarget, selectedTargets],
  );
  const dispatchReady = useMemo(() => dispatchTargets.filter((target) => target.eligible
    && runtimeStates.get(target.key)?.state === 'ready'), [dispatchTargets, runtimeStates]);
  const sendButtonLabel = activeTarget
    ? `Send to ${activeTarget.label}`
    : `Send to ${dispatchReady.length} ${dispatchReady.length === 1 ? 'target' : 'targets'}`;

  const send = useCallback(async (command) => {
    const snapshot = dispatchTargets.filter((target) => target.eligible);
    const ready = snapshot.filter((target) => runtimeStates.get(target.key)?.state === 'ready');
    const skipped = snapshot.filter((target) => !ready.some((item) => item.key === target.key))
      .map((target) => ({ ...target, reason: statusReason(runtimeStates.get(target.key)) }));
    const id = runId();
    runs.startRun({ id, command, readyTargets: ready, skippedTargets: skipped });
    // Tree items carry the instance id as `id` (see buildRconHosts), not `instance_id`.
    const acknowledgement = await session.sendCommand(id, command, ready.map(({ host_id, id: instanceId }) => ({
      host_id, instance_id: instanceId,
    })));
    runs.applyDispatchAck(id, acknowledgement);
    return true;
  }, [dispatchTargets, runs, runtimeStates, session]);

  if (loading) return <div className="global-rcon-page"><p className="global-rcon-state">Loading Global RCON inventory…</p></div>;
  if (error) return (
    <div className="global-rcon-page"><div className="global-rcon-state global-rcon-error">
      <AlertTriangle size={20} /><span>Unable to load server inventory: {inventoryErrorText(error)}</span>
    </div></div>
  );

  return (
    <div className="global-rcon-page">
      <header className="global-rcon-header">
        <div><h1><Terminal size={24} /> Global RCON</h1></div>
        <div className="global-rcon-summary"><Radio size={15} className={session.connected ? 'text-emerald-500' : 'text-theme-muted'} />
          {readyTargets.length} ready / {selectedEligible.length} eligible selected</div>
      </header>
      <div className="global-rcon-layout">
        <aside className={`global-rcon-targets scrollbar-thin ${targetsOpen ? '' : 'global-rcon-targets-collapsed'}`}>
          <div className="global-rcon-targets-title">
            <div className="flex flex-1 overflow-hidden rounded-t-xl border border-[var(--surface-border)] bg-[var(--surface-elevated)]">
              <span className="flex flex-1 items-center gap-2 border-b-2 border-b-[var(--accent-primary)] bg-[var(--accent-primary)]/5 px-4 py-2.5 text-[13px] font-display font-semibold uppercase tracking-wide text-[var(--accent-primary)]">
                <Target size={16} />
                Targets
              </span>
            </div>
            <button type="button" className="global-rcon-target-toggle"
              aria-expanded={targetsOpen} onClick={() => setTargetsOpen((open) => !open)}>{targetsOpen ? 'Hide targets' : 'Show targets'}</button>
          </div>
          {targetsOpen && <RconTargetTree
            hosts={rconHosts} selectedKeys={preferences.selectedKeys} expandedHostIds={preferences.expandedHostIds}
            runtimeStates={runtimeStates} serverStatuses={serverStatuses} setTargetChecked={preferences.setTargetChecked}
            setHostChecked={preferences.setHostChecked} selectAllEligible={preferences.selectAllEligible}
            selectNone={preferences.selectNone} toggleHostExpanded={preferences.toggleHostExpanded}
            setAllHostsExpanded={preferences.setAllHostsExpanded}
          />}
        </aside>
        <section className="global-rcon-output"><GlobalRconOutput activeFilter={activeFilter} onFilterChange={setActiveFilter}
          selectedTargets={selectedTargets} runs={runs.runs} rawStreams={runs.rawStreams}
          commandInput={<RconCommandInput disabled={!dispatchReady.length} className="border-t border-theme"
            buttonLabel={sendButtonLabel} onSend={send}
          />}
        /></section>
      </div>
    </div>
  );
}
