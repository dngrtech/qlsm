import { useState, useEffect, useRef } from 'react';
import { getServerStatus } from '../services/api';

const POLL_INTERVAL = 15000; // 15 seconds

export function useServerStatus() {
    const [statusMap, setStatusMap] = useState({}); // {instanceId: statusData}
    const intervalRef = useRef(null);

    const fetchStatus = async () => {
        try {
            const data = await getServerStatus();
            setStatusMap(data || {});
        } catch {
            // On error, keep existing statusMap — don't clear live data
        }
    };

    useEffect(() => {
        fetchStatus();
        intervalRef.current = setInterval(fetchStatus, POLL_INTERVAL);
        return () => clearInterval(intervalRef.current);
    }, []);

    return statusMap;
}
