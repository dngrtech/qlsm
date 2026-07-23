import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react';

import { buildTargetKey, parseTargetKey } from '../utils/rconTargets';
import { acquireRconSocket, releaseRconSocket } from './rconSocketTransport';

export const FLEET_ACK_TIMEOUT_MS = 10_000;
const REASONS = {
  notReady: 'Target is not ready',
  timeout: 'Command acknowledgement timed out',
  disconnected: 'Socket disconnected',
  closed: 'Fleet session closed',
  malformed: 'Malformed command acknowledgement',
  ackError: 'Command acknowledgement error',
  missing: 'Missing command acknowledgement',
  rejected: 'Command rejected',
  rconError: 'RCON error',
};

function normalizeTargets(targets) {
  const refs = [];
  const seen = new Set();
  for (const target of Array.isArray(targets) ? targets : []) {
    try {
      const key = buildTargetKey(target);
      if (seen.has(key)) continue;
      seen.add(key);
      refs.push(parseTargetKey(key));
    } catch {
      // Invalid browser-side refs are outside the explicit target contract.
    }
  }
  return { refs, keys: seen, signature: refs.map(buildTargetKey).join(',') };
}

function eventTargetKey(target) {
  return target && Number.isSafeInteger(target.host_id) && target.host_id > 0
    && Number.isSafeInteger(target.instance_id) && target.instance_id > 0
    ? `${target.host_id}:${target.instance_id}` : null;
}

function rejected(target, reason) {
  return { ...target, state: 'rejected', reason };
}

function commandResults(runId, targets, immediate, settled = new Map()) {
  return { run_id: runId, targets: targets.map((target) => (
    immediate.get(buildTargetKey(target)) ?? settled.get(buildTargetKey(target))
  )) };
}

function normalizeCommandAck(ack, runId, emitted) {
  if (ack && typeof ack === 'object' && !Array.isArray(ack) && 'error' in ack) {
    return new Map(emitted.map((target) => [buildTargetKey(target), rejected(target, REASONS.ackError)]));
  }
  if (!ack || typeof ack !== 'object' || Array.isArray(ack)
      || ack.run_id !== runId || !Array.isArray(ack.targets)) {
    return new Map(emitted.map((target) => [buildTargetKey(target), rejected(target, REASONS.malformed)]));
  }
  const expected = new Map(emitted.map((target) => [buildTargetKey(target), target]));
  const results = new Map();
  for (const item of ack.targets) {
    const key = eventTargetKey(item);
    if (!key) continue;
    if (!expected.has(key) || results.has(key)) continue;
    const target = expected.get(key);
    if (item.state === 'queued') results.set(key, { ...target, state: 'queued' });
    else if (item.state === 'rejected') {
      const reason = typeof item.reason === 'string' && item.reason ? item.reason : REASONS.rejected;
      results.set(key, rejected(target, reason));
    }
  }
  for (const [key, target] of expected) {
    if (!results.has(key)) results.set(key, rejected(target, REASONS.missing));
  }
  return results;
}

export function useFleetRconSession({ targets, enabled, onMessage, onStatus }) {
  const normalized = useMemo(() => normalizeTargets(targets), [targets]);
  const inputRef = useRef(normalized);
  inputRef.current = normalized;
  const [connected, setConnected] = useState(false);
  const [statuses, setStatuses] = useState(new Map());
  const socketRef = useRef(null);
  const connectedRef = useRef(false);
  const targetsRef = useRef({ refs: [], keys: new Set(), signature: '' });
  const statusRef = useRef(new Map());
  const generationsRef = useRef(new Map());
  const generationRef = useRef(0);
  const reconcileVersionRef = useRef(0);
  const pendingRef = useRef(new Set());
  const onMessageRef = useRef(onMessage);
  const onStatusRef = useRef(onStatus);
  onMessageRef.current = onMessage;
  onStatusRef.current = onStatus;

  const publishStatuses = useCallback((next) => {
    statusRef.current = next;
    setStatuses(next);
  }, []);

  const transition = useCallback((target, value, generation) => {
    const key = buildTargetKey(target);
    if (!targetsRef.current.keys.has(key)) return;
    if (generation !== undefined && generationsRef.current.get(key) !== generation) return;
    const previous = statusRef.current.get(key);
    if (previous?.state === value.state && previous?.reason === value.reason) return;
    const next = new Map(statusRef.current);
    next.set(key, value);
    publishStatuses(next);
    onStatusRef.current?.({ ...target, ...value });
  }, [publishStatuses]);

  const resetTargets = useCallback(() => {
    const next = new Map();
    const generations = new Map();
    for (const target of targetsRef.current.refs) {
      const key = buildTargetKey(target);
      next.set(key, { state: 'connecting' });
      generations.set(key, ++generationRef.current);
    }
    generationsRef.current = generations;
    publishStatuses(next);
  }, [publishStatuses]);

  const settlePending = useCallback((reason) => {
    for (const pending of [...pendingRef.current]) pending.fail(reason);
  }, []);

  const applyTargets = useCallback((nextTargets, emitChange) => {
    if (targetsRef.current.signature === nextTargets.signature) return;
    const previousStatuses = statusRef.current;
    const previousGenerations = generationsRef.current;
    const nextStatuses = new Map();
    const nextGenerations = new Map();
    for (const target of nextTargets.refs) {
      const key = buildTargetKey(target);
      if (targetsRef.current.keys.has(key)) {
        nextStatuses.set(key, previousStatuses.get(key) ?? { state: 'connecting' });
        nextGenerations.set(key, previousGenerations.get(key));
      } else {
        nextStatuses.set(key, { state: 'connecting' });
        nextGenerations.set(key, ++generationRef.current);
      }
    }
    targetsRef.current = nextTargets;
    generationsRef.current = nextGenerations;
    publishStatuses(nextStatuses);
    if (emitChange && connectedRef.current && socketRef.current) {
      const version = ++reconcileVersionRef.current;
      const generations = new Map(nextGenerations);
      socketRef.current.emit('rcon:fleet_targets', { targets: nextTargets.refs }, (ack) => {
        if (version !== reconcileVersionRef.current) return;
        if (!ack || !Array.isArray(ack.targets)) return;
        for (const item of ack.targets) {
          const key = eventTargetKey(item);
          if (!key) continue;
          if (item.state !== 'rejected' || statusRef.current.get(key)?.state !== 'connecting') continue;
          const target = parseTargetKey(key);
          const reason = typeof item.reason === 'string' && item.reason ? item.reason : REASONS.rejected;
          transition(target, { state: 'failed', reason }, generations.get(key));
        }
      });
    }
  }, [publishStatuses, transition]);

  useLayoutEffect(() => {
    if (!enabled) return undefined;
    applyTargets(inputRef.current, false);
    const socket = acquireRconSocket();
    socketRef.current = socket;

    const reconcileAck = (ack, generations, version) => {
      if (version !== reconcileVersionRef.current) return;
      if (!ack || !Array.isArray(ack.targets)) return;
      for (const item of ack.targets) {
        const key = eventTargetKey(item);
        if (!key) continue;
        if (item.state !== 'rejected' || statusRef.current.get(key)?.state !== 'connecting') continue;
        const reason = typeof item.reason === 'string' && item.reason ? item.reason : REASONS.rejected;
        transition(parseTargetKey(key), { state: 'failed', reason }, generations.get(key));
      }
    };
    const onConnect = () => {
      connectedRef.current = true;
      setConnected(true);
      resetTargets();
      const version = ++reconcileVersionRef.current;
      const generations = new Map(generationsRef.current);
      socket.emit('rcon:fleet_join', { targets: targetsRef.current.refs },
        (ack) => reconcileAck(ack, generations, version));
    };
    const loseConnection = (error) => {
      connectedRef.current = false;
      setConnected(false);
      reconcileVersionRef.current += 1;
      const reason = typeof error?.message === 'string' && error.message
        ? error.message : REASONS.disconnected;
      for (const target of targetsRef.current.refs) {
        transition(target, { state: 'failed', reason });
      }
      settlePending(REASONS.disconnected);
    };
    const onRconStatus = (data) => {
      if (!connectedRef.current) return;
      const key = eventTargetKey(data);
      if (!key || typeof data.status !== 'string') return;
      if (!targetsRef.current.keys.has(key)) return;
      const target = parseTargetKey(key);
      if (data.status === 'connected') transition(target, { state: 'ready' });
      else if (data.status === 'error' || data.status === 'disconnected') {
        const reason = typeof data.reason === 'string' && data.reason
          ? data.reason : (typeof data.error === 'string' && data.error ? data.error : data.status);
        transition(target, { state: 'failed', reason });
      } else transition(target, { state: 'connecting' });
    };
    const onRconMessage = (data) => {
      if (!connectedRef.current) return;
      const key = eventTargetKey(data);
      if (!key) return;
      if (targetsRef.current.keys.has(key)) onMessageRef.current?.(data);
    };
    const onRconError = (data) => {
      if (!connectedRef.current) return;
      const key = eventTargetKey(data);
      if (!key || !targetsRef.current.keys.has(key)) return;
      const target = parseTargetKey(key);
      const reason = typeof data.error === 'string' && data.error
        ? data.error : (typeof data.reason === 'string' && data.reason
          ? data.reason : REASONS.rconError);
      // Every error remains raw-stream evidence, including duplicate terminal errors.
      onMessageRef.current?.({ ...data, ...target, type: 'error', content: reason });
      transition(target, { state: 'failed', reason });
    };

    socket.on('connect', onConnect);
    socket.on('disconnect', loseConnection);
    socket.on('connect_error', loseConnection);
    socket.on('rcon:status', onRconStatus);
    socket.on('rcon:message', onRconMessage);
    socket.on('rcon:error', onRconError);
    if (socket.connected) onConnect();

    return () => {
      socket.emit('rcon:fleet_leave', {});
      socket.off('connect', onConnect);
      socket.off('disconnect', loseConnection);
      socket.off('connect_error', loseConnection);
      socket.off('rcon:status', onRconStatus);
      socket.off('rcon:message', onRconMessage);
      socket.off('rcon:error', onRconError);
      settlePending(REASONS.closed);
      socketRef.current = null;
      connectedRef.current = false;
      reconcileVersionRef.current += 1;
      setConnected(false);
      targetsRef.current = { refs: [], keys: new Set(), signature: '' };
      generationsRef.current = new Map();
      publishStatuses(new Map());
      releaseRconSocket();
    };
  }, [enabled, applyTargets, publishStatuses, resetTargets, settlePending, transition]);

  useLayoutEffect(() => {
    if (enabled) applyTargets(normalized, true);
  }, [enabled, normalized, applyTargets]);

  const sendCommand = useCallback((runId, cmd, readyTargets) => {
    const requested = normalizeTargets(readyTargets).refs;
    const emitted = requested.filter((target) => connectedRef.current
      && statusRef.current.get(buildTargetKey(target))?.state === 'ready');
    const immediate = new Map(requested.filter((target) => !emitted.some(
      (candidate) => buildTargetKey(candidate) === buildTargetKey(target),
    )).map((target) => [buildTargetKey(target), rejected(target, REASONS.notReady)]));
    if (!emitted.length) return Promise.resolve(commandResults(runId, requested, immediate));

    return new Promise((resolve) => {
      const pending = {
        done: false,
        fail(reason) {
          if (pending.done) return;
          pending.done = true;
          clearTimeout(pending.timer);
          pendingRef.current.delete(pending);
          const failed = new Map(emitted.map((target) => [
            buildTargetKey(target), rejected(target, reason),
          ]));
          resolve(commandResults(runId, requested, immediate, failed));
        },
      };
      const finish = (ack) => {
        if (pending.done) return;
        pending.done = true;
        clearTimeout(pending.timer);
        pendingRef.current.delete(pending);
        const acknowledged = normalizeCommandAck(ack, runId, emitted);
        resolve(commandResults(runId, requested, immediate, acknowledged));
      };
      pending.timer = setTimeout(() => pending.fail(REASONS.timeout), FLEET_ACK_TIMEOUT_MS);
      pendingRef.current.add(pending);
      socketRef.current.emit('rcon:fleet_command', {
        run_id: runId, cmd, targets: emitted,
      }, finish);
    });
  }, []);

  const readyTargets = targetsRef.current.refs.filter((target) =>
    statuses.get(buildTargetKey(target))?.state === 'ready');
  return { connected, statuses, readyTargets, sendCommand };
}

export default useFleetRconSession;
