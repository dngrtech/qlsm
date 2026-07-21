import { useCallback, useEffect, useRef, useState } from 'react';
import { acquireRconSocket, releaseRconSocket } from './rconSocketTransport';

function targetFor(hostId, instanceId) {
  return { host_id: hostId, instance_id: instanceId };
}

export function useRconSocket(instance, isOpen, onMessage) {
  const [connected, setConnected] = useState(false);
  const [status, setStatus] = useState('disconnected');
  const socketRef = useRef(null);
  const statsEnabledRef = useRef(false);
  const statusRef = useRef(status);
  const onMessageRef = useRef(onMessage);
  const hostId = instance?.host_id;
  const instanceId = instance?.id;

  useEffect(() => { statusRef.current = status; }, [status]);
  useEffect(() => { onMessageRef.current = onMessage; }, [onMessage]);

  useEffect(() => {
    if (!isOpen || hostId == null || instanceId == null) return undefined;

    const socket = acquireRconSocket();
    const joinedTarget = targetFor(hostId, instanceId);
    socketRef.current = socket;

    const emitMessage = (message) => onMessageRef.current?.(message);
    const belongsToInstance = (data) => (
      data.host_id === joinedTarget.host_id
      && data.instance_id === joinedTarget.instance_id
    );
    const timestamp = () => new Date().toLocaleTimeString();
    const onConnect = () => {
      setConnected(true);
      statusRef.current = 'connected';
      setStatus('connected');
      socket.emit('rcon:join', targetFor(hostId, instanceId));
    };
    const onDisconnect = () => {
      setConnected(false);
      statusRef.current = 'disconnected';
      setStatus('disconnected');
    };
    const onConnectError = (error) => {
      console.error('RCON socket error:', error);
      statusRef.current = 'error';
      setStatus('error');
      emitMessage({
        type: 'error',
        content: `Connection error: ${error.message || 'Unable to connect to server'}`,
        timestamp: timestamp(),
      });
    };
    const onRconStatus = (data) => {
      if (!belongsToInstance(data)) return;
      statusRef.current = data.status;
      setStatus(data.status);
      if (data.status === 'connected' && statsEnabledRef.current) {
        socket.emit('rcon:subscribe_stats', targetFor(hostId, instanceId));
      }
    };
    const onRconMessage = (data) => {
      if (!belongsToInstance(data)) return;
      emitMessage({ type: 'response', content: data.content, timestamp: timestamp() });
    };
    const onRconStats = (data) => {
      if (!belongsToInstance(data)) return;
      emitMessage({
        type: 'stats',
        content: `[STATS] ${data.event?.TYPE || 'UNKNOWN'}: ${JSON.stringify(data.event)}`,
        timestamp: timestamp(),
      });
    };
    const onRconError = (data) => {
      if (!belongsToInstance(data)) return;
      emitMessage({ type: 'error', content: `Error: ${data.error}`, timestamp: timestamp() });
    };

    socket.on('connect', onConnect);
    socket.on('disconnect', onDisconnect);
    socket.on('connect_error', onConnectError);
    socket.on('rcon:status', onRconStatus);
    socket.on('rcon:message', onRconMessage);
    socket.on('rcon:stats', onRconStats);
    socket.on('rcon:error', onRconError);
    if (socket.connected) onConnect();

    return () => {
      socket.off('connect', onConnect);
      socket.off('disconnect', onDisconnect);
      socket.off('connect_error', onConnectError);
      socket.off('rcon:status', onRconStatus);
      socket.off('rcon:message', onRconMessage);
      socket.off('rcon:stats', onRconStats);
      socket.off('rcon:error', onRconError);
      socket.emit('rcon:unsubscribe_stats', joinedTarget);
      socket.emit('rcon:leave', joinedTarget);
      releaseRconSocket();
      if (socketRef.current === socket) socketRef.current = null;
      setConnected(false);
      statusRef.current = 'disconnected';
      setStatus('disconnected');
    };
  }, [isOpen, hostId, instanceId]);

  const sendCommand = useCallback((cmd) => {
    if (!socketRef.current || !connected || hostId == null || instanceId == null) {
      console.error('Cannot send command: not connected');
      return false;
    }
    onMessageRef.current?.({ type: 'command', content: cmd, timestamp: new Date().toLocaleTimeString() });
    socketRef.current.emit('rcon:command', { ...targetFor(hostId, instanceId), cmd });
    return true;
  }, [connected, hostId, instanceId]);

  const subscribeStats = useCallback(() => {
    if (!socketRef.current || hostId == null || instanceId == null) return;
    statsEnabledRef.current = true;
    if (statusRef.current === 'connected') {
      socketRef.current.emit('rcon:subscribe_stats', targetFor(hostId, instanceId));
    }
  }, [hostId, instanceId]);

  const unsubscribeStats = useCallback(() => {
    if (!socketRef.current || hostId == null || instanceId == null) return;
    statsEnabledRef.current = false;
    socketRef.current.emit('rcon:unsubscribe_stats', targetFor(hostId, instanceId));
  }, [hostId, instanceId]);

  return { connected, status, sendCommand, subscribeStats, unsubscribeStats };
}

export default useRconSocket;
