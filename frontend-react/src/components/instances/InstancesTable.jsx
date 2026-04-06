import React from 'react';
// Link, LoaderCircle, AlertTriangle, formatStatus, InstanceActionsMenu are used by InstancesTableRow
import InstancesTableRow from './InstancesTableRow'; // Import the new component

function InstancesTable({
  sortedInstances,
  handleSort,
  getSortIcon,
  handleRestartRequest,
  handleDeleteRequest,
  handleToggleLanRate, // Added for LAN rate toggle
  onOpenEditConfigModal, // Added new prop
  onViewInstanceDetails, // Added for the details drawer
  onOpenHostDrawer, // Added for host drawer
  onViewLogs, // Added for view logs modal
  onViewChatLogs, // Added for chat logs modal
  onOpenRconConsole, // RCON console callback
  POLLABLE_INSTANCE_STATUSES,
}) {
  if (!sortedInstances || sortedInstances.length === 0) {
    // This case should ideally be handled by the parent (InstancesPage)
    // before rendering this table, e.g., showing "No instances found."
    // However, as a safeguard or if this component could be used standalone:
    return <p>No instances to display in table.</p>;
  }

  return (
    <div className="overflow-x-auto shadow-md rounded-lg">
      {/* Added dark mode styles */}
      <table className="w-full bg-white dark:bg-slate-800">
        {/* Added dark mode styles */}
        <thead className="bg-gray-200 dark:bg-slate-700">
          <tr>
            {/* Added dark mode styles and increased font weight */}
            <th className="py-2 px-2 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider w-[20%]">
              <button onClick={() => handleSort('name')} className="flex items-center hover:text-gray-700 dark:hover:text-gray-200">
                Name {getSortIcon('name')}
              </button>
            </th>
            {/* Added dark mode styles and increased font weight */}
            <th className="py-2 px-2 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider w-[15%]">
              <button onClick={() => handleSort('host_name')} className="flex items-center hover:text-gray-700 dark:hover:text-gray-200">
                Host {getSortIcon('host_name')}
              </button>
            </th>
            {/* Added IP Address column */}
            <th className="py-2 px-2 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider w-[15%]">
              <button onClick={() => handleSort('host_ip_address')} className="flex items-center hover:text-gray-700 dark:hover:text-gray-200">
                IP Address {getSortIcon('host_ip_address')}
              </button>
            </th>
            {/* Added dark mode styles and increased font weight */}
            <th className="py-2 px-2 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider w-[10%]">
              <button onClick={() => handleSort('port')} className="flex items-center hover:text-gray-700 dark:hover:text-gray-200">
                Port {getSortIcon('port')}
              </button>
            </th>
            {/* Added dark mode styles and increased font weight */}
            <th className="py-2 px-2 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider w-[20%]">
              <button onClick={() => handleSort('hostname')} className="flex items-center hover:text-gray-700 dark:hover:text-gray-200">
                Server Hostname {getSortIcon('hostname')}
              </button>
            </th>
            {/* Added dark mode styles and increased font weight */}
            <th className="py-2 px-2 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider w-[15%]">
              <button onClick={() => handleSort('status')} className="flex items-center hover:text-gray-700 dark:hover:text-gray-200">
                Status {getSortIcon('status')}
              </button>
            </th>
            {/* Added dark mode styles and increased font weight */}
            <th className="py-2 px-2 text-center text-xs font-semibold text-gray-500 dark:text-slate-400 tracking-wider">
              Actions
            </th>
          </tr>
        </thead>
        {/* Added dark mode divider */}
        <tbody className="divide-y divide-gray-200 dark:divide-slate-600">
          {sortedInstances.map((instance) => (
            <InstancesTableRow
              key={instance.id}
              instance={instance}
              handleRestartRequest={handleRestartRequest}
              handleDeleteRequest={handleDeleteRequest}
              handleToggleLanRate={handleToggleLanRate}
              onOpenEditConfigModal={onOpenEditConfigModal} // Pass down
              onViewInstanceDetails={onViewInstanceDetails} // Pass down the new prop
              onOpenHostDrawer={onOpenHostDrawer} // Pass down handler for host drawer
              onViewLogs={onViewLogs} // Pass down handler for view logs modal
              onViewChatLogs={onViewChatLogs} // Pass down handler for chat logs modal
              onOpenRconConsole={onOpenRconConsole}
              POLLABLE_INSTANCE_STATUSES={POLLABLE_INSTANCE_STATUSES}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default InstancesTable;
