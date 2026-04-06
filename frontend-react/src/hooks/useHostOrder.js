// frontend-react/src/hooks/useHostOrder.js
import { useState, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';

const BASE_KEY = 'qlds-host-order';

function storageKey(userId) {
    return userId ? `${BASE_KEY}-${userId}` : null;
}

function loadOrder(userId) {
    const key = storageKey(userId);
    if (!key) return [];
    try {
        const raw = localStorage.getItem(key);
        return raw ? JSON.parse(raw) : [];
    } catch {
        return [];
    }
}

function saveOrder(userId, order) {
    const key = storageKey(userId);
    if (!key) return;
    try {
        localStorage.setItem(key, JSON.stringify(order));
    } catch {
        // Storage full or unavailable — silently degrade
    }
}

/**
 * Manages custom host display order.
 * Persists ordered host IDs to localStorage, keyed by user ID; reconciles with live data.
 */
export function useHostOrder() {
    const { currentUser } = useAuth();
    const userId = currentUser?.id ?? null;

    const [order, setOrder] = useState(() => loadOrder(userId));

    const getOrderedHosts = useCallback(
        (hosts) => {
            if (!order.length) return hosts;

            const hostMap = new Map(hosts.map((h) => [h.id, h]));
            const ordered = [];

            for (const id of order) {
                const host = hostMap.get(id);
                if (host) {
                    ordered.push(host);
                    hostMap.delete(id);
                }
            }

            // Append any new hosts not in the saved order
            for (const host of hostMap.values()) {
                ordered.push(host);
            }

            return ordered;
        },
        [order]
    );

    const setHostOrder = useCallback(
        (reorderedHosts) => {
            const ids = reorderedHosts.map((h) => h.id);
            setOrder(ids);
            saveOrder(userId, ids);
        },
        [userId]
    );

    return { getOrderedHosts, setHostOrder };
}
