import React from 'react';
import HostsTableRow from './HostsTableRow'; // Import the new row component

function HostsTable({
  sortedHosts,
  handleSort,
  getSortIcon,
  handleDeleteRequest,
  POLLABLE_STATUSES,
  copyToClipboard,
  copiedIp,
  onOpenDrawer, // Renamed from onHostNameClick
  onInstallQlfilter, // New prop
  onUninstallQlfilter, // New prop
  onRequestRestart,
  onInstanceNameClick, // ADDED: New prop for instance name click
}) {
  if (!sortedHosts || sortedHosts.length === 0) {
    return <p>No hosts to display in table.</p>;
  }

  return (
    <div className="overflow-x-auto shadow-md rounded-lg">
      {/* Adjusted dark mode table background to slate-800 */}
      <table className="w-full bg-white dark:bg-slate-800">
        {/* Adjusted dark mode thead background to slate-700 */}
        <thead className="bg-gray-200 dark:bg-slate-700">
          <tr>
            {/* Increased font weight */}
            <th className="py-2 px-2 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider w-[15%]">
              <button onClick={() => handleSort('name')} className="flex items-center hover:text-gray-700 dark:hover:text-gray-200">
                Name {getSortIcon('name')}
              </button>
            </th>
            {/* Increased font weight */}
            <th className="py-2 px-2 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider w-[10%]">
              <button onClick={() => handleSort('provider')} className="flex items-center hover:text-gray-700 dark:hover:text-gray-200">
                Provider {getSortIcon('provider')}
              </button>
            </th>
            {/* Increased font weight */}
            <th className="py-2 px-2 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider w-[15%]">
              <button onClick={() => handleSort('region')} className="flex items-center hover:text-gray-700 dark:hover:text-gray-200">
                Region {getSortIcon('region')}
              </button>
            </th>
            {/* Increased font weight */}
            <th className="py-2 px-2 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider w-[25%]">
              <button onClick={() => handleSort('machine_size')} className="flex items-center hover:text-gray-700 dark:hover:text-gray-200">
                Size {getSortIcon('machine_size')}
              </button>
            </th>
            {/* Increased font weight */}
            <th className="py-2 px-2 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider w-[15%]">
              <button onClick={() => handleSort('ip_address')} className="flex items-center hover:text-gray-700 dark:hover:text-gray-200">
                IP Address {getSortIcon('ip_address')}
              </button>
            </th>
            {/* Increased font weight */}
            <th className="py-2 px-2 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider w-[10%]">
              <button onClick={() => handleSort('instances')} className="flex items-center hover:text-gray-700 dark:hover:text-gray-200">
                Instances {getSortIcon('instances')}
              </button>
            </th>
            {/* Increased font weight */}
            <th className="py-2 px-2 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider w-[10%]">
              <button onClick={() => handleSort('status')} className="flex items-center hover:text-gray-700 dark:hover:text-gray-200">
                Status {getSortIcon('status')}
              </button>
            </th>
            <th className="py-2 px-2 text-center text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider w-[8%]">
              QL-Filter
            </th>
            {/* Increased font weight */}
            <th className="py-2 px-2 text-left text-xs font-semibold text-gray-500 dark:text-slate-400 uppercase tracking-wider w-[5%]">
              {/* Actions */}
            </th>
          </tr>
        </thead>
        {/* Adjusted dark mode divider to slate-600 */}
        <tbody className="divide-y divide-gray-200 dark:divide-slate-600">
          {sortedHosts.map((host) => (
            <HostsTableRow
              key={host.id}
              host={host}
              handleDeleteRequest={handleDeleteRequest}
              POLLABLE_STATUSES={POLLABLE_STATUSES}
              copyToClipboard={copyToClipboard}
              copiedIp={copiedIp}
              onOpenDrawer={onOpenDrawer} // Pass it down
              onInstallQlfilter={onInstallQlfilter} // Pass it down
              onUninstallQlfilter={onUninstallQlfilter} // Pass it down
              onRequestRestart={onRequestRestart} // Pass onRequestRestart down to the row
              onInstanceNameClick={onInstanceNameClick} // ADDED: Pass it down
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default HostsTable;
