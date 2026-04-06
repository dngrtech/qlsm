import { useState, useEffect, useCallback, useMemo } from 'react';
import { getInstances, deleteInstance, restartInstance } from '../services/api';
import { useInstanceLanRate } from './useInstanceLanRate';
import { useNotification } from '../components/NotificationProvider';
import { useLoading } from '../contexts/LoadingContext'; // Import useLoading

export const POLLING_INTERVAL = 3000; // 3 seconds
export const POLLABLE_INSTANCE_STATUSES = ['deploying', 'deleting', 'restarting', 'configuring', 'stopping', 'starting'];

export function useInstances() {
  const [instances, setInstances] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deleteError, setDeleteError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [actionSuccessMessage, setActionSuccessMessage] = useState(null);
  const { showSuccess, showError } = useNotification();
  const { setIsLoadingGlobal } = useLoading(); // Get setIsLoadingGlobal
  
  const [isRestartModalOpen, setIsRestartModalOpen] = useState(false);
  const [isDeleteModalOpen, setIsDeleteModalOpen] = useState(false);
  const [selectedInstance, setSelectedInstance] = useState(null);

  // State for Edit Config Modal
  const [isEditConfigModalOpen, setIsEditConfigModalOpen] = useState(false);
  const [selectedInstanceForEdit, setSelectedInstanceForEdit] = useState(null); // Can store { id, name }

  const [sortColumn, setSortColumn] = useState('name');
  const [sortDirection, setSortDirection] = useState('asc');

  const refreshInstances = useCallback(async (isInitialFetch = true) => {
    try {
      if (isInitialFetch) {
        setLoading(true);
        setIsLoadingGlobal(true); // Set global loading true
      }
      const data = await getInstances();
      setInstances(data);
      if (isInitialFetch) setError(null);
    } catch (err) {
      if (isInitialFetch) {
        setError(err.message || 'Failed to fetch instances');
        setInstances([]);
      }
      console.error('Error fetching instances:', err);
    } finally {
      if (isInitialFetch) {
        setLoading(false);
        setIsLoadingGlobal(false); // Set global loading false
      }
    }
  }, [setIsLoadingGlobal]); // Added setIsLoadingGlobal to dependencies

  useEffect(() => {
    refreshInstances(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Ensure initial fetch runs only once on mount

  useEffect(() => {
    let intervalId;
    const shouldPoll = instances.some(instance => POLLABLE_INSTANCE_STATUSES.includes(instance.status));

    if (shouldPoll) {
      intervalId = setInterval(() => {
        refreshInstances(false);
      }, POLLING_INTERVAL);
    }

    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [instances, refreshInstances]);

  const handleDeleteRequest = (instanceId, instanceName) => {
    setSelectedInstance({ id: instanceId, name: instanceName });
    setIsDeleteModalOpen(true);
  };

  const confirmDeleteInstance = async () => {
    if (!selectedInstance) return;
    try {
      setDeleteError(null);
      setActionError(null);
      setActionSuccessMessage(null);
      const response = await deleteInstance(selectedInstance.id);
      const message = response.message || `Instance "${selectedInstance.name}" deletion initiated.`;
      setActionSuccessMessage(message);
      showSuccess(message);
      setTimeout(() => setActionSuccessMessage(null), 5000);
      refreshInstances(false);
    } catch (err) {
      const errorMessage = err.error?.message || err.message || `Failed to delete instance "${selectedInstance.name}".`;
      setDeleteError(errorMessage);
      showError(errorMessage);
      setTimeout(() => setDeleteError(null), 7000);
      console.error(`Error deleting instance ${selectedInstance.id}:`, err);
    }
    setSelectedInstance(null);
    setIsDeleteModalOpen(false); // Close modal after action
  };

  const handleRestartRequest = (instanceId, instanceName) => {
    setSelectedInstance({ id: instanceId, name: instanceName });
    setIsRestartModalOpen(true);
  };

  const confirmRestartInstance = async () => {
    if (!selectedInstance) return;
    try {
      setActionError(null);
      setDeleteError(null);
      setActionSuccessMessage(null);
      const response = await restartInstance(selectedInstance.id);
      const message = response.message || `Instance "${selectedInstance.name}" restart task queued.`;
      setActionSuccessMessage(message);
      showSuccess(message);
      setTimeout(() => setActionSuccessMessage(null), 5000);
      refreshInstances(false);
    } catch (err) {
      const errorMessage = err.error?.message || err.message || `Failed to restart instance "${selectedInstance.name}".`;
      setActionError(errorMessage);
      showError(errorMessage);
      setTimeout(() => setActionError(null), 7000);
      console.error(`Error restarting instance ${selectedInstance.id}:`, err);
    }
    setSelectedInstance(null);
    setIsRestartModalOpen(false); // Close modal after action
  };

  const handleSort = (columnKey) => {
    if (sortColumn === columnKey) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(columnKey);
      setSortDirection('asc');
    }
  };

  const sortedInstances = useMemo(() => {
    if (!sortColumn) return instances;
    return [...instances].sort((a, b) => {
      let valA = a[sortColumn];
      let valB = b[sortColumn];
      if (sortColumn === 'port') {
        valA = parseInt(valA, 10);
        valB = parseInt(valB, 10);
      } else if (typeof valA === 'string') {
        valA = valA.toLowerCase();
        valB = valB.toLowerCase();
      }
      if (valA < valB) return sortDirection === 'asc' ? -1 : 1;
      if (valA > valB) return sortDirection === 'asc' ? 1 : -1;
      return 0;
    });
  }, [instances, sortColumn, sortDirection]);
  
  // Functions to close modals, to be called from the page component
  const closeDeleteModal = () => setIsDeleteModalOpen(false);
  const closeRestartModal = () => setIsRestartModalOpen(false);

  // Handlers for Edit Config Modal
  const handleEditConfigRequest = (instanceToEdit) => {
    setSelectedInstanceForEdit(instanceToEdit); // Store the whole instance or just id/name
    setIsEditConfigModalOpen(true);
  };

  const closeEditConfigModal = () => {
    setIsEditConfigModalOpen(false);
    setSelectedInstanceForEdit(null);
  };

  const handleConfigSaved = () => {
    refreshInstances(false); // Refresh instance list after saving config
    // Optionally show a success notification here if desired
    // showSuccess('Configuration saved successfully and update task queued.');
    closeEditConfigModal();
  };

  const {
    lanRateAction, isLanRateModalOpen,
    requestToggleLanRate: handleToggleLanRateRequest,
    confirmToggleLanRate, closeLanRateModal,
  } = useInstanceLanRate(showSuccess, showError, () => refreshInstances(false));

  return {
    instances, // Though sortedInstances will likely be used more
    loading,
    error,
    deleteError,
    actionError,
    actionSuccessMessage,
    isRestartModalOpen,
    isDeleteModalOpen,
    selectedInstance,
    sortColumn,
    sortDirection,
    sortedInstances,
    handleDeleteRequest,
    confirmDeleteInstance,
    handleRestartRequest,
    confirmRestartInstance,
    handleSort,
    closeDeleteModal,
    closeRestartModal,
    refreshInstances, // Export refreshInstances
    
    // Edit Config Modal state and handlers
    isEditConfigModalOpen,
    selectedInstanceForEdit,
    handleEditConfigRequest,
    closeEditConfigModal,
    handleConfigSaved,

    // LAN Rate Toggle Modal state and handlers
    isLanRateModalOpen,
    lanRateAction,
    handleToggleLanRateRequest,
    confirmToggleLanRate,
    closeLanRateModal,
    // POLLABLE_INSTANCE_STATUSES and POLLING_INTERVAL are exported directly if needed elsewhere,
    // or can be returned if only used by the consuming component.
    // For now, they are exported constants from the module.
  };
}
