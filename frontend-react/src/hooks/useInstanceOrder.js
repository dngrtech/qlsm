// frontend-react/src/hooks/useInstanceOrder.js
import { useState, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';

const BASE_KEY = 'qlds-instance-order';

function storageKey(userId) {
    return userId ? `${BASE_KEY}-${userId}` : null;
}

function loadOrderMap(userId) {
    const key = storageKey(userId);
    if (!key) return {};
    try {
        const raw = localStorage.getItem(key);
        return raw ? JSON.parse(raw) : {};
    } catch {
        return {};
    }
}

function saveOrderMap(userId, orderMap) {
    const key = storageKey(userId);
    if (!key) return;
    try {
        localStorage.setItem(key, JSON.stringify(orderMap));
    } catch {
        // Storage full or unavailable — silently degrade
    }
}

/**
 * Manages custom instance display order per host.
 * Persists ordered instance IDs to localStorage, keyed by user ID; reconciles with live data.
 */
export function useInstanceOrder() {
    const { currentUser } = useAuth();
    const userId = currentUser?.id ?? null;

    const [orderMap, setOrderMap] = useState(() => loadOrderMap(userId));

    const getOrderedInstances = useCallback(
        (hostId, instances) => {
            const savedOrder = orderMap[hostId];
            if (!savedOrder) return instances;

            const instanceMap = new Map(instances.map((i) => [i.id, i]));
            const ordered = [];

            // Add instances in saved order (skip removed ones)
            for (const id of savedOrder) {
                const inst = instanceMap.get(id);
                if (inst) {
                    ordered.push(inst);
                    instanceMap.delete(id);
                }
            }

            // Append any new instances not in the saved order
            for (const inst of instanceMap.values()) {
                ordered.push(inst);
            }

            return ordered;
        },
        [orderMap]
    );

    const setInstanceOrder = useCallback(
        (hostId, reorderedInstances) => {
            setOrderMap((prev) => {
                const next = {
                    ...prev,
                    [hostId]: reorderedInstances.map((i) => i.id),
                };
                saveOrderMap(userId, next);
                return next;
            });
        },
        [userId]
    );

    return { getOrderedInstances, setInstanceOrder };
}
