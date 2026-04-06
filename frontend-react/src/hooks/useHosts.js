import { useState, useEffect, useCallback, useMemo } from 'react';
import { getHosts, deleteHost } from '../services/api';
import { useNotification } from '../components/NotificationProvider';
import { useLoading } from '../contexts/LoadingContext'; // Import useLoading

export const POLLING_INTERVAL = 3000; // 3 seconds
export const POLLABLE_HOST_STATUSES = ['pending', 'provisioning', 'provisioned_pending_setup', 'deleting', 'rebooting', 'configuring'];
// Define QLFilter statuses that indicate an ongoing background operation
export const POLLABLE_QLFILTER_STATUSES = ['installing', 'uninstalling'];

export function useHosts() {
  const [hosts, setHosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deleteError, setDeleteError] = useState(null);
  const [deleteSuccessMessage, setDeleteSuccessMessage] = useState(null);
  const { showSuccess, showError } = useNotification();
  const { setIsLoadingGlobal } = useLoading(); // Get setIsLoadingGlobal
  
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [selectedHost, setSelectedHost] = useState(null);
  
  const [sortColumn, setSortColumn] = useState('name');
  const [sortDirection, setSortDirection] = useState('asc');
  const [copiedIp, setCopiedIp] = useState(null);

  const fetchHostsData = useCallback(async (isInitialFetch = true) => {
    try {
      if (isInitialFetch) {
        setLoading(true);
        setIsLoadingGlobal(true); // Set global loading true
      }
      const data = await getHosts();
      setHosts(data);
      if (isInitialFetch) setError(null);
    } catch (err) {
      if (isInitialFetch) {
        setError(err.message || 'Failed to fetch hosts');
        setHosts([]);
      }
      console.error('Error fetching hosts:', err);
    } finally {
      if (isInitialFetch) {
        setLoading(false);
        setIsLoadingGlobal(false); // Set global loading false
      }
    }
  }, [setIsLoadingGlobal]); // Added setIsLoadingGlobal to dependencies

  useEffect(() => {
    fetchHostsData(true);
  }, [fetchHostsData]);

  useEffect(() => {
    let intervalId;
    const shouldPollForHostStatus = hosts.some(host => POLLABLE_HOST_STATUSES.includes(host.status));
    const shouldPollForQlfilterStatus = hosts.some(host => POLLABLE_QLFILTER_STATUSES.includes(host.qlfilter_status));
    
    const shouldPoll = shouldPollForHostStatus || shouldPollForQlfilterStatus;

    if (shouldPoll) {
      intervalId = setInterval(() => {
        fetchHostsData(false);
      }, POLLING_INTERVAL);
    }

    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [hosts, fetchHostsData]);

  const handleDeleteRequest = (hostId, hostName) => {
    setSelectedHost({ id: hostId, name: hostName });
    setIsDeleteModalOpen(true);
  };

  const confirmDeleteHost = async () => {
    if (!selectedHost) return;
    try {
      setDeleteError(null);
      setDeleteSuccessMessage(null);
      const response = await deleteHost(selectedHost.id);
      const message = response.message || `Host "${selectedHost.name}" deletion task queued.`;
      setDeleteSuccessMessage(message);
      showSuccess(message);
      setTimeout(() => setDeleteSuccessMessage(null), 5000);
      fetchHostsData(false);
    } catch (err) {
      const errorMessage = err.error?.message || err.message || `Failed to delete host "${selectedHost.name}".`;
      setDeleteError(errorMessage);
      showError(errorMessage);
      setDeleteSuccessMessage(null);
      setTimeout(() => setDeleteError(null), 7000);
      console.error(`Error deleting host ${selectedHost.id}:`, err);
    }
    setSelectedHost(null);
    setIsDeleteModalOpen(false);
  };

  const copyToClipboard = (text, hostId) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedIp(hostId);
      setTimeout(() => setCopiedIp(null), 2000);
    }).catch(err => {
      console.error('Failed to copy IP address: ', err);
    });
  };

  const handleSort = (columnKey) => {
    if (sortColumn === columnKey) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(columnKey);
      setSortDirection('asc');
    }
  };

  const sortedHosts = useMemo(() => {
    if (!sortColumn) return hosts;
    return [...hosts].sort((a, b) => {
      let valA = a[sortColumn];
      let valB = b[sortColumn];
      if (sortColumn === 'instances') {
        valA = a.instances?.length || 0;
        valB = b.instances?.length || 0;
      } else if (typeof valA === 'string') {
        valA = valA.toLowerCase();
        valB = valB.toLowerCase();
      }
      if (valA < valB) return sortDirection === 'asc' ? -1 : 1;
      if (valA > valB) return sortDirection === 'asc' ? 1 : -1;
      return 0;
    });
  }, [hosts, sortColumn, sortDirection]);
  
  const closeDeleteModal = () => setIsDeleteModalOpen(false);

  return {
    loading,
    error,
    deleteError,
    deleteSuccessMessage,
    isDeleteModalOpen,
    selectedHost,
    sortColumn,
    sortDirection,
    copiedIp,
    sortedHosts,
    handleDeleteRequest,
    confirmDeleteHost,
    copyToClipboard,
    handleSort,
    closeDeleteModal,
    refreshHosts: fetchHostsData, // Expose fetchHostsData as refreshHosts
    // POLLABLE_STATUSES is exported directly
  };
}
