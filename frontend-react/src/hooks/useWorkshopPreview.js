import { useEffect, useState } from 'react';
import { getWorkshopPreview } from '../services/api';

const CACHE_TTL_MS = 6 * 60 * 60 * 1000; // 6 hours
const ERROR_CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes
const previewCache = new Map();

const normalizeWorkshopId = (workshopItemId) => {
    if (workshopItemId === null || workshopItemId === undefined) return null;
    const value = String(workshopItemId).trim();
    return /^\d+$/.test(value) ? value : null;
};

const cacheEntry = (id, previewUrl, ttlMs) => {
    previewCache.set(id, {
        previewUrl,
        expiresAt: Date.now() + ttlMs,
    });
};

export const __clearWorkshopPreviewCacheForTests = () => {
    previewCache.clear();
};

export function useWorkshopPreview(workshopItemId, enabled = true) {
    const [previewUrl, setPreviewUrl] = useState(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        const normalizedId = normalizeWorkshopId(workshopItemId);
        if (!enabled || !normalizedId) {
            setPreviewUrl(null);
            setLoading(false);
            return;
        }

        const cached = previewCache.get(normalizedId);
        if (cached && cached.expiresAt > Date.now()) {
            setPreviewUrl(cached.previewUrl);
            setLoading(false);
            return;
        }

        let cancelled = false;
        setLoading(true);

        const loadPreview = async () => {
            try {
                const result = await getWorkshopPreview(normalizedId);
                const nextUrl = typeof result?.preview_url === 'string' && result.preview_url.trim()
                    ? result.preview_url.trim()
                    : null;
                cacheEntry(normalizedId, nextUrl, CACHE_TTL_MS);
                if (!cancelled) setPreviewUrl(nextUrl);
            } catch {
                cacheEntry(normalizedId, null, ERROR_CACHE_TTL_MS);
                if (!cancelled) setPreviewUrl(null);
            } finally {
                if (!cancelled) setLoading(false);
            }
        };

        loadPreview();

        return () => {
            cancelled = true;
        };
    }, [workshopItemId, enabled]);

    return { previewUrl, loading };
}
