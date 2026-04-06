import { useMemo, useEffect } from 'react';
import { useHosts, POLLABLE_HOST_STATUSES } from './useHosts';
import { useInstances, POLLABLE_INSTANCE_STATUSES } from './useInstances';
import { useExpandState } from './useExpandState';

// Re-export constants
export { POLLABLE_HOST_STATUSES, POLLABLE_INSTANCE_STATUSES };

export function useServers() {
    const {
        sortedHosts: hosts,
        loading: hostsLoading,
        error: hostsError,
        refreshHosts,
        handleDeleteRequest: requestDeleteHost,
        confirmDeleteHost,
        isDeleteModalOpen: isHostDeleteModalOpen,
        selectedHost,
        closeDeleteModal: closeHostDeleteModal,
        // Host specific actions
        handleDeleteRequest: requestDeleteHostAction,
    } = useHosts();

    const {
        instances,
        loading: instancesLoading,
        error: instancesError,
        refreshInstances, // We need to be able to refresh instances
        handleDeleteRequest: requestDeleteInstance,
        confirmDeleteInstance,
        isDeleteModalOpen: isInstanceDeleteModalOpen,
        selectedInstance,
        closeDeleteModal: closeInstanceDeleteModal,
        // Instance specific actions
        handleRestartRequest: requestRestartInstance,
        confirmRestartInstance,
        isRestartModalOpen: isInstanceRestartModalOpen,
        closeRestartModal: closeInstanceRestartModal,
    } = useInstances();

    const {
        expandedIds: expandedHostIds,
        initExpanded,
        toggleExpand,
        expandAll: expandAllHosts,
        collapseAll,
    } = useExpandState([]);

    // Initialize with all host IDs once hosts load
    useEffect(() => {
        if (hosts.length > 0) {
            initExpanded(hosts.map((h) => h.id));
        }
    }, [hosts, initExpanded]);

    const expandAll = () => expandAllHosts(hosts.map((h) => h.id));

    // Combined stats
    const stats = useMemo(() => {
        const totalHosts = hosts.length;
        const totalInstances = instances.length;
        const runningInstances = instances.filter(
            (i) => i.status && i.status.toLowerCase() === 'running'
        ).length;

        return { totalHosts, totalInstances, runningInstances };
    }, [hosts, instances]);

    // Merge instances into their respective hosts
    const serversData = useMemo(() => {
        return hosts.map((host) => {
            const hostInstances = instances.filter(
                (inst) =>
                    (inst.host_id === host.id) ||
                    (inst.host && inst.host.id === host.id)
            );

            return {
                ...host,
                instances: hostInstances,
                expanded: expandedHostIds.has(host.id),
            };
        });
    }, [hosts, instances, expandedHostIds]);

    const refreshData = async (fullReload = false) => {
        await Promise.all([
            refreshHosts(fullReload),
            refreshInstances(fullReload)
        ]);
    };

    // Provide a unified interface for the UI
    // Note: For delete modals, useServers synthesizes a single interface 
    // that delegates to the underlying hooks based on what's active.

    const deleteModal = {
        open: isHostDeleteModalOpen || isInstanceDeleteModalOpen,
        type: isHostDeleteModalOpen ? 'host' : 'instance',
        item: isHostDeleteModalOpen ? selectedHost : selectedInstance,
    };

    const closeDeleteModal = () => {
        if (isHostDeleteModalOpen) closeHostDeleteModal();
        if (isInstanceDeleteModalOpen) closeInstanceDeleteModal();
    };

    const confirmDelete = () => {
        if (isHostDeleteModalOpen) confirmDeleteHost();
        if (isInstanceDeleteModalOpen) confirmDeleteInstance();
    };

    // Restart modal for instances only (Hosts have their own flow in the component via actions menu)
    const restartModal = {
        open: isInstanceRestartModalOpen,
        instance: selectedInstance, // Reusing selectedInstance from useInstances for restart too if hook supports it, waiting for verify.
        // Actually useInstances separates restart logic.
        // Let's verify useInstances implementation.
    };

    // Checking useInstances in previous turn:
    // It has handleRestartRequest, confirmRestartInstance, isRestartModalOpen.
    // It uses selectedInstance state for both delete and restart? 
    // "const [selectedInstance, setSelectedInstance] = useState(null);" -> Yes, shared state.

    return {
        serversData,
        stats,
        loading: hostsLoading || instancesLoading,
        error: hostsError || instancesError,
        toggleExpand,
        expandAll,
        collapseAll,
        refreshData,

        // Deletion
        deleteModal,
        requestDeleteHost,
        requestDeleteInstance,
        confirmDelete,
        closeDeleteModal,

        // Instance Restart
        restartModal,
        requestRestartInstance,
        confirmRestart: confirmRestartInstance,
        closeRestartModal: closeInstanceRestartModal,
    };
}
