import { useCallback, useEffect, useRef, useState } from 'react';

import { buildTargetKey, parseTargetKey } from '../utils/rconTargets';

export const QUIET_AFTER_MS = 1_500;
export const NO_RESPONSE_AFTER_MS = 5_000;
export const MAX_RUNS = 50;
export const MAX_RAW_LINES = 1_000;
// Compatibility aliases for existing consumers.
export const RCON_QUIET_MS = QUIET_AFTER_MS;
export const RCON_NO_RESPONSE_MS = NO_RESPONSE_AFTER_MS;
const ACTIVE_STATES = new Set(['pending_dispatch', 'queued', 'receiving', 'quiet', 'no_response']);

function nowTimestamp() {
  return new Date().toLocaleTimeString();
}

function safeReason(value, fallback) {
  return typeof value === 'string' && value.trim() ? value : fallback;
}

function descriptor(target) {
  try {
    const key = target?.key && parseTargetKey(target.key) ? target.key : buildTargetKey(target);
    const ids = parseTargetKey(key);
    if (!ids) return null;
    const name = safeReason(target?.name ?? target?.display_name ?? target?.label,
      `Target ${ids.host_id}:${ids.instance_id}`);
    return { key, name, display_name: name, label: name, ...ids };
  } catch {
    return null;
  }
}

function exactEventKey(value) {
  return value && Number.isSafeInteger(value.host_id) && value.host_id > 0
    && Number.isSafeInteger(value.instance_id) && value.instance_id > 0
    ? `${value.host_id}:${value.instance_id}` : null;
}

function ackKey(value) {
  return exactEventKey(value) ?? descriptor(value)?.key ?? null;
}

function eventFromMessage(message) {
  const type = message?.type === 'error' ? 'error' : 'response';
  const fallback = type === 'error' ? message?.error ?? message?.reason : '';
  const content = typeof message?.content === 'string' ? message.content
    : typeof fallback === 'string' ? fallback : String(message?.content ?? fallback ?? '');
  return { type, content, timestamp: message?.timestamp ?? nowTimestamp() };
}

export function countPhysicalLines(content) {
  return String(content ?? '').split('\n').length;
}

export function retainNewestRawLines(events, limit = MAX_RAW_LINES) {
  const retained = [...events];
  let overflow = retained.reduce(
    (total, event) => total + countPhysicalLines(event.content), 0,
  ) - limit;
  while (overflow > 0 && retained.length) {
    const oldestLines = String(retained[0].content ?? '').split('\n');
    if (oldestLines.length <= overflow) {
      overflow -= oldestLines.length;
      retained.shift();
    } else {
      retained[0] = { ...retained[0], content: oldestLines.slice(overflow).join('\n') };
      overflow = 0;
    }
  }
  return retained;
}

function cloneResult(target, state, reason) {
  return {
    ...target,
    state,
    ...(reason ? { reason } : {}),
    lines: [],
    ack_anomaly: false,
    dispatch_ack_applied: false,
  };
}

export function useRconCommandRuns() {
  const [runs, setRuns] = useState([]);
  const [rawStreams, setRawStreams] = useState(new Map());
  const runsRef = useRef([]);
  const rawRef = useRef(new Map());
  const activeRef = useRef(new Map());
  const timersRef = useRef(new Map());

  const publishRuns = useCallback((next) => {
    runsRef.current = next;
    setRuns(next);
  }, []);
  const publishRaw = useCallback((next) => {
    rawRef.current = next;
    setRawStreams(next);
  }, []);
  const clearTimersFor = useCallback((runId, key) => {
    const token = JSON.stringify([runId, key]);
    const timers = timersRef.current.get(token);
    if (timers) {
      clearTimeout(timers.quiet);
      clearTimeout(timers.noResponse);
      timersRef.current.delete(token);
    }
  }, []);
  const clearTimersForRun = useCallback((runId) => {
    for (const [token, timers] of timersRef.current) {
      if (timers.runId !== runId) continue;
      clearTimeout(timers.quiet);
      clearTimeout(timers.noResponse);
      timersRef.current.delete(token);
    }
  }, []);
  const replaceResult = useCallback((runId, key, change) => {
    let changed = false;
    const next = runsRef.current.map((run) => {
      if (run.id !== runId) return run;
      const results = run.results.map((result) => {
        if (result.key !== key) return result;
        const replacement = change(result);
        if (replacement === result) return result;
        changed = true;
        return replacement;
      });
      return changed ? { ...run, results } : run;
    });
    if (changed) publishRuns(next);
    return changed;
  }, [publishRuns]);
  const appendRaw = useCallback((key, event) => {
    const next = new Map(rawRef.current);
    const events = retainNewestRawLines([...(next.get(key) ?? []), event]);
    next.set(key, events);
    publishRaw(next);
  }, [publishRaw]);

  const armQuiet = useCallback((key, runId) => {
    clearTimersFor(runId, key);
    const token = JSON.stringify([runId, key]);
    const timer = setTimeout(() => {
      replaceResult(runId, key, (result) => result.state === 'receiving'
        ? { ...result, state: 'quiet' } : result);
      if (timersRef.current.get(token)?.quiet === timer) timersRef.current.delete(token);
    }, RCON_QUIET_MS);
    timersRef.current.set(token, { runId, key, quiet: timer });
  }, [clearTimersFor, replaceResult]);

  const armNoResponse = useCallback((key, runId) => {
    clearTimersFor(runId, key);
    const token = JSON.stringify([runId, key]);
    const timer = setTimeout(() => {
      replaceResult(runId, key, (result) => result.state === 'queued'
        ? { ...result, state: 'no_response' } : result);
      if (timersRef.current.get(token)?.noResponse === timer) timersRef.current.delete(token);
    }, RCON_NO_RESPONSE_MS);
    timersRef.current.set(token, { runId, key, noResponse: timer });
  }, [clearTimersFor, replaceResult]);

  const startRun = useCallback(({ id, command, readyTargets, skippedTargets, timestamp }) => {
    const at = timestamp ?? nowTimestamp();
    const ready = [];
    const skipped = [];
    const seen = new Set();
    for (const candidate of Array.isArray(readyTargets) ? readyTargets : []) {
      const target = descriptor(candidate);
      if (!target || seen.has(target.key)) continue;
      seen.add(target.key);
      ready.push(target);
    }
    for (const candidate of Array.isArray(skippedTargets) ? skippedTargets : []) {
      const target = descriptor(candidate);
      if (!target || seen.has(target.key)) continue;
      seen.add(target.key);
      skipped.push({ target, reason: safeReason(candidate.reason, 'Target skipped') });
    }
    clearTimersForRun(id);
    for (const target of [...ready, ...skipped.map((item) => item.target)]) {
      activeRef.current.delete(target.key);
    }
    for (const target of ready) {
      activeRef.current.set(target.key, id);
      appendRaw(target.key, {
        type: 'command', content: command, attempted: true, timestamp: at,
      });
    }
    const run = {
      id,
      command,
      timestamp: at,
      results: [
        ...ready.map((target) => cloneResult(target, 'pending_dispatch')),
        ...skipped.map(({ target, reason }) => cloneResult(target, 'skipped', reason)),
      ],
    };
    const next = [run, ...runsRef.current.filter((item) => item.id !== id)].slice(0, MAX_RUNS);
    const retained = new Set(next.map((item) => item.id));
    for (const previous of runsRef.current) {
      if (!retained.has(previous.id)) clearTimersForRun(previous.id);
    }
    for (const [key, runId] of activeRef.current) {
      if (!retained.has(runId)) activeRef.current.delete(key);
    }
    publishRuns(next);
    return run;
  }, [appendRaw, clearTimersForRun, publishRuns]);

  const applyDispatchAck = useCallback((runId, ack) => {
    const run = runsRef.current.find((item) => item.id === runId);
    if (!run) return;
    const items = Array.isArray(ack?.targets) ? ack.targets : [];
    const byKey = new Map(items.map((item) => [ackKey(item), item]).filter(([key]) => key));
    const malformed = !ack || typeof ack !== 'object' || !Array.isArray(ack.targets)
      || 'error' in ack || ('run_id' in ack && ack.run_id !== runId);
    let nextRuns = runsRef.current;
    let changed = false;
    const nextResults = run.results.map((result) => {
      if (result.state === 'skipped' || result.dispatch_ack_applied) return result;
      const item = byKey.get(result.key);
      const queued = !malformed && item?.state === 'queued';
      if (queued) {
        if (result.state === 'pending_dispatch') {
          changed = true;
          armNoResponse(result.key, runId);
          return { ...result, state: 'queued', dispatch_ack_applied: true };
        }
        if (['failed', 'rejected'].includes(result.state)) return result;
        changed = true;
        return { ...result, dispatch_ack_applied: true };
      }
      const reason = malformed
        ? (ack && typeof ack === 'object' && 'error' in ack
          ? 'Command acknowledgement error' : 'Malformed command acknowledgement')
        : item?.state === 'rejected'
          ? safeReason(item.reason, 'Command rejected') : 'Missing command acknowledgement';
      if (result.state === 'rejected' || result.state === 'failed') return result;
      clearTimersFor(runId, result.key);
      if (activeRef.current.get(result.key) === runId) {
        activeRef.current.delete(result.key);
      }
      changed = true;
      return {
        ...result,
        state: 'rejected',
        reason,
        ack_anomaly: result.lines.length > 0,
        dispatch_ack_applied: true,
      };
    });
    if (changed) {
      nextRuns = runsRef.current.map((item) => item.id === runId ? { ...item, results: nextResults } : item);
      publishRuns(nextRuns);
    }
  }, [armNoResponse, clearTimersFor, publishRuns]);

  const appendMessage = useCallback((message) => {
    const key = exactEventKey(message);
    if (!key) return;
    const event = eventFromMessage(message);
    appendRaw(key, event);
    const runId = activeRef.current.get(key);
    if (!runId) return;
    clearTimersFor(runId, key);
    const changed = replaceResult(runId, key, (result) => {
      const state = result.state === 'failed' || result.state === 'rejected'
        ? result.state : 'receiving';
      return { ...result, state, lines: retainNewestRawLines([...result.lines, event]) };
    });
    const current = runsRef.current.find((run) => run.id === runId)?.results.find((item) => item.key === key);
    if (changed && current?.state === 'receiving') armQuiet(key, runId);
  }, [appendRaw, armQuiet, clearTimersFor, replaceResult]);

  const applyTargetStatus = useCallback((status) => {
    const key = exactEventKey(status);
    const runId = key && activeRef.current.get(key);
    if (!runId) return;
    const state = String(status.state ?? status.status ?? '').toLowerCase();
    if (!['error', 'disconnected', 'failed'].includes(state)) return;
    replaceResult(runId, key, (result) => ACTIVE_STATES.has(result.state)
      ? { ...result, state: 'failed', reason: safeReason(status.reason ?? status.error, state) }
      : result);
    if (activeRef.current.get(key) === runId) {
      clearTimersFor(runId, key);
      activeRef.current.delete(key);
    }
  }, [clearTimersFor, replaceResult]);

  const clearRuns = useCallback(() => {
    for (const timers of timersRef.current.values()) {
      clearTimeout(timers.quiet);
      clearTimeout(timers.noResponse);
    }
    timersRef.current.clear();
    activeRef.current.clear();
    publishRuns([]);
  }, [publishRuns]);
  const clearRaw = useCallback((key) => {
    const next = new Map(rawRef.current);
    if (key == null) next.clear();
    else next.delete(key);
    publishRaw(next);
  }, [publishRaw]);

  useEffect(() => () => {
    for (const timers of timersRef.current.values()) {
      clearTimeout(timers.quiet);
      clearTimeout(timers.noResponse);
    }
    timersRef.current.clear();
  }, []);

  return { runs, rawStreams, startRun, applyDispatchAck, appendMessage, applyTargetStatus, clearRuns, clearRaw };
}

export default useRconCommandRuns;
