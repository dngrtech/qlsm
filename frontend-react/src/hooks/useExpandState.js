// frontend-react/src/hooks/useExpandState.js
import { useState, useCallback } from 'react';
import { useAuth } from '../contexts/AuthContext';

const BASE_KEY = 'qlds-expand-state';

function storageKey(userId) {
    return userId ? `${BASE_KEY}-${userId}` : null;
}

function loadExpandedIds(userId) {
    const key = storageKey(userId);
    if (!key) return null; // null = "not loaded yet"
    try {
        const raw = localStorage.getItem(key);
        return raw ? new Set(JSON.parse(raw)) : null; // null = "no saved state"
    } catch {
        return null;
    }
}

function saveExpandedIds(userId, ids) {
    const key = storageKey(userId);
    if (!key) return;
    try {
        localStorage.setItem(key, JSON.stringify([...ids]));
    } catch {
        // Storage full or unavailable — silently degrade
    }
}

/**
 * Manages which host rows are expanded.
 * Persists to localStorage, keyed by user ID.
 * Falls back to "all expanded" on first visit (no saved state).
 */
export function useExpandState(allHostIds) {
    const { currentUser } = useAuth();
    const userId = currentUser?.id ?? null;

    const [expandedIds, setExpandedIds] = useState(() => {
        const saved = loadExpandedIds(userId);
        // If we have saved state, use it; otherwise start with all expanded
        return saved ?? new Set(allHostIds);
    });

    // When hosts first load and we have no saved state, expand them all.
    // (handles the case where allHostIds is empty on first render)
    const initExpanded = useCallback(
        (hostIds) => {
            const saved = loadExpandedIds(userId);
            setExpandedIds((prev) => {
                if (prev.size === 0 && saved === null) {
                    return new Set(hostIds);
                }
                return prev;
            });
        },
        [userId]
    );

    const toggleExpand = useCallback(
        (hostId) => {
            setExpandedIds((prev) => {
                const next = new Set(prev);
                if (next.has(hostId)) {
                    next.delete(hostId);
                } else {
                    next.add(hostId);
                }
                saveExpandedIds(userId, next);
                return next;
            });
        },
        [userId]
    );

    const expandAll = useCallback(
        (hostIds) => {
            const next = new Set(hostIds);
            saveExpandedIds(userId, next);
            setExpandedIds(next);
        },
        [userId]
    );

    const collapseAll = useCallback(() => {
        const next = new Set();
        saveExpandedIds(userId, next);
        setExpandedIds(next);
    }, [userId]);

    return { expandedIds, initExpanded, toggleExpand, expandAll, collapseAll };
}
