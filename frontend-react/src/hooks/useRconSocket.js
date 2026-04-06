/**
 * useRconSocket - React hook for RCON WebSocket communication.
 * 
 * Manages SocketIO connection to Flask-SocketIO backend for
 * RCON console functionality.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { io } from 'socket.io-client';

const SOCKET_URL = import.meta.env.VITE_API_BASE_URL || '';

// Global socket cache to strictly prevent React StrictMode double-connections
// NOTE: Module-level globals are not Vite HMR-safe. On hot-reload globalSocket resets 
// to null but the old socket stays connected; the next mount opens a second socket.
// The orphan killer in run-dev.sh provides a recovery path for this trade-off.
let globalSocket = null;
let globalSocketUsers = 0;
let globalDisconnectTimer = null;

/**
 * Hook for managing RCON WebSocket connection.
 * 
 * @param {Object} instance - Instance object with host_id, id, zmq_rcon_port
 * @param {boolean} isOpen - Whether the console modal is open
 * @param {Function} onMessage - Callback for incoming messages
 * @returns {Object} - { connected, status, sendCommand, subscribeStats, unsubscribeStats }
 */
export function useRconSocket(instance, isOpen, onMessage) {
    const [connected, setConnected] = useState(false);
    const [status, setStatus] = useState('disconnected');
    const socketRef = useRef(null);
    const statsEnabledRef = useRef(false);
    const statusRef = useRef(status);
    const instanceRef = useRef(instance);
    const onMessageRef = useRef(onMessage);

    // Keep refs fresh
    useEffect(() => {
        instanceRef.current = instance;
    }, [instance]);
    useEffect(() => {
        statusRef.current = status;
    }, [status]);
    useEffect(() => {
        onMessageRef.current = onMessage;
    }, [onMessage]);

    // Initialize socket connection
    useEffect(() => {
        if (!isOpen || !instance) {
            return;
        }

        // If remounting while a disconnect is pending, cancel the disconnect!
        if (globalDisconnectTimer) {
            clearTimeout(globalDisconnectTimer);
            globalDisconnectTimer = null;
        }

        // Use global socket to prevent StrictMode double-mounts from opening two WebSockets
        if (!globalSocket) {
            globalSocket = io(SOCKET_URL, {
                withCredentials: true,
                transports: import.meta.env.DEV ? ['polling'] : ['websocket', 'polling'],
                upgrade: !import.meta.env.DEV,
                reconnection: true,
                reconnectionAttempts: 3,
                reconnectionDelay: 1000,
            });
        }

        globalSocketUsers++;
        const socket = globalSocket;
        socketRef.current = socket;

        // Connection handlers
        const onConnect = () => {
            const inst = instanceRef.current;
            setConnected(true);
            setStatus('connected');

            // Join RCON room — credentials resolved server-side
            socket.emit('rcon:join', {
                host_id: inst.host_id,
                instance_id: inst.id,
            });
        };

        const onDisconnect = () => {
            setConnected(false);
            setStatus('disconnected');
        };

        const onConnectError = (error) => {
            console.error('RCON socket error:', error);
            setStatus('error');
            const timestamp = new Date().toLocaleTimeString();
            if (onMessageRef.current) onMessageRef.current({
                type: 'error',
                content: `Connection error: ${error.message || 'Unable to connect to server'}`,
                timestamp,
            });
        };

        const onRconStatus = (data) => {
            setStatus(data.status);
            if (data.status === 'connected') {
                if (statsEnabledRef.current) {
                    const inst = instanceRef.current;
                    socket.emit('rcon:subscribe_stats', {
                        host_id: inst.host_id,
                        instance_id: inst.id,
                    });
                }
            }
        };

        const onRconMessage = (data) => {
            const timestamp = new Date().toLocaleTimeString();
            if (onMessageRef.current) onMessageRef.current({
                type: 'response',
                content: data.content,
                timestamp,
            });
        };

        const onRconStats = (data) => {
            const timestamp = new Date().toLocaleTimeString();
            const eventType = data.event?.TYPE || 'UNKNOWN';
            if (onMessageRef.current) onMessageRef.current({
                type: 'stats',
                content: `[STATS] ${eventType}: ${JSON.stringify(data.event)}`,
                timestamp,
            });
        };

        const onRconError = (data) => {
            const timestamp = new Date().toLocaleTimeString();
            if (onMessageRef.current) onMessageRef.current({
                type: 'error',
                content: `Error: ${data.error}`,
                timestamp,
            });
        };

        // Attach listeners
        if (socket.connected) onConnect(); // Trigger if already connected via previous mount
        socket.on('connect', onConnect);
        socket.on('disconnect', onDisconnect);
        socket.on('connect_error', onConnectError);
        socket.on('rcon:status', onRconStatus);
        socket.on('rcon:message', onRconMessage);
        socket.on('rcon:stats', onRconStats);
        socket.on('rcon:error', onRconError);

        // Cleanup on unmount or when modal closes
        return () => {
            const inst = instanceRef.current;
            const wasStatsEnabled = statsEnabledRef.current;

            // Always detach this instance's event listeners immediately
            socket.off('connect', onConnect);
            socket.off('disconnect', onDisconnect);
            socket.off('connect_error', onConnectError);
            socket.off('rcon:status', onRconStatus);
            socket.off('rcon:message', onRconMessage);
            socket.off('rcon:stats', onRconStats);
            socket.off('rcon:error', onRconError);

            globalSocketUsers--;

            // If genuinely unmounting the whole tree, set a debounce timer to kill the socket
            // This allows React StrictMode to remount instantly without tearing down the connection
            if (globalSocketUsers <= 0 && globalSocket) {
                globalDisconnectTimer = setTimeout(() => {
                    if (globalSocketUsers <= 0 && globalSocket) {
                        globalSocket.emit('rcon:leave', {
                            host_id: inst.host_id,
                            instance_id: inst.id,
                        });

                        if (wasStatsEnabled) {
                            globalSocket.emit('rcon:unsubscribe_stats', {
                                host_id: inst.host_id,
                                instance_id: inst.id,
                            });
                        }

                        globalSocket.disconnect();
                        globalSocket = null;
                        globalSocketUsers = 0;
                        globalDisconnectTimer = null;
                    }
                }, 1000);
            }

            if (socketRef.current === socket) {
                socketRef.current = null;
            }
            setConnected(false);
            setStatus('disconnected');
        };
    }, [isOpen, instance?.id, instance?.host_id]);

    // Send RCON command
    const sendCommand = useCallback((cmd) => {
        if (!socketRef.current || !connected || !instance) {
            console.error('Cannot send command: not connected');
            return false;
        }

        // Add command to messages as input
        const timestamp = new Date().toLocaleTimeString();
        if (onMessageRef.current) onMessageRef.current({
            type: 'command',
            content: cmd,
            timestamp,
        });

        socketRef.current.emit('rcon:command', {
            host_id: instance.host_id,
            instance_id: instance.id,
            cmd,
        });

        return true;
    }, [connected, instance?.id, instance?.host_id]);

    // Subscribe to stats events
    const subscribeStats = useCallback(() => {
        if (!socketRef.current || !instance) return;

        statsEnabledRef.current = true;

        // Only emit if we are already connected to RCON
        // Otherwise, the rcon:status handler will do it when we connect
        if (statusRef.current === 'connected') {
            socketRef.current.emit('rcon:subscribe_stats', {
                host_id: instance.host_id,
                instance_id: instance.id,
            });
        }
    }, [instance?.id, instance?.host_id]);

    // Unsubscribe from stats events
    const unsubscribeStats = useCallback(() => {
        if (!socketRef.current || !instance) return;

        statsEnabledRef.current = false;
        socketRef.current.emit('rcon:unsubscribe_stats', {
            host_id: instance.host_id,
            instance_id: instance.id,
        });
    }, [instance?.id, instance?.host_id]);

    return {
        connected,
        status,
        sendCommand,
        subscribeStats,
        unsubscribeStats,
    };
}

export default useRconSocket;
