import React from 'react';
// Link import removed as it's replaced by a button for instance details
import { Copy, Check } from 'lucide-react';
import { formatVultrPlan, formatVultrRegion } from '../../utils/formatters';
import HostActionsMenu from '../HostActionsMenu'; // Path relative to HostsTableRow.jsx
import StatusIndicator from '../StatusIndicator'; // Import the new component
import QLFilterIndicator from './QLFilterIndicator';

function HostsTableRow({
  host,
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
  return (
    // Adjusted dark hover background to slate-600
    <tr key={host.id} className="hover:bg-gray-100 dark:hover:bg-slate-600">
      {/* Adjusted dark text color to slate-100 */}
      <td className="py-2 px-2 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-slate-100 truncate max-w-[150px]" title={host.name}>
        {/* Replace Link with clickable button/span */}
        <button
          type="button"
          onClick={() => onOpenDrawer(host.id)} // Changed from onHostNameClick
          className="text-indigo-600 dark:text-indigo-400 hover:text-indigo-900 dark:hover:text-indigo-200 hover:underline focus:outline-none text-left w-full"
        >
          {host.name}
        </button>
      </td>
      {/* Adjusted dark text color to slate-300 */}
      <td className="py-2 px-2 whitespace-nowrap text-sm text-gray-700 dark:text-slate-300">{host.provider}</td>
      {/* Adjusted dark text color to slate-300 */}
      <td className="py-2 px-2 text-sm text-gray-700 dark:text-slate-300" title={formatVultrRegion(host.region)}>
        <div className="truncate max-w-[150px] lg:max-w-none">
          {formatVultrRegion(host.region)}
        </div>
      </td>
      {/* Adjusted dark text color to slate-300 */}
      <td className="py-2 px-2 text-sm text-gray-700 dark:text-slate-300" title={formatVultrPlan(host.machine_size)}>
        <div className="truncate max-w-[200px] lg:max-w-none">
          {formatVultrPlan(host.machine_size)}
        </div>
      </td>
      {/* Adjusted dark text color to slate-300 */}
      <td className="py-2 px-2 text-sm text-gray-700 dark:text-slate-300">
        <div className="flex items-center space-x-1">
          {/* Ensure span inherits dark text color */}
          <span className="truncate max-w-[120px] lg:max-w-none" title={host.ip_address}>{host.ip_address || 'N/A'}</span>
          {host.ip_address && (
            <button
              onClick={() => copyToClipboard(host.ip_address, host.id)}
              className="flex-shrink-0 p-1 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 focus:outline-none"
              title="Copy IP Address"
            >
              {copiedIp === host.id ? <Check size={16} className="text-green-500" /> : <Copy size={16} />}
            </button>
          )}
        </div>
      </td>
      {/* Adjusted dark text color to slate-300 */}
      <td className="py-2 px-2 text-sm text-gray-700 dark:text-slate-300">
        <div
          className="flex flex-col space-y-1"
          title={host.instances && host.instances.length > 0 ? host.instances.map(inst => inst.name).join(', ') : 'None'}
        >
          {host.instances && host.instances.length > 0 ? (
            host.instances.map((instance) => (
              <button
                key={instance.id}
                type="button"
                onClick={() => {
                  if (onInstanceNameClick) {
                    onInstanceNameClick(instance.id);
                  }
                }}
                className="text-indigo-600 dark:text-indigo-400 hover:underline focus:outline-none text-left truncate"
              >
                {instance.name}
              </button>
            ))
          ) : (
            <span className="text-gray-500 dark:text-gray-400">None</span>
          )}
        </div>
      </td>
      <td className="py-2 px-2 text-sm">
        {/* Use the StatusIndicator component */}
        <StatusIndicator status={host.status} pollableStatuses={POLLABLE_STATUSES} />
      </td>
      <td className="py-2 px-2 text-sm text-center">
        <QLFilterIndicator qlfilterStatus={host.qlfilter_status} />
      </td>
      {/* Adjusted dark text color to slate-400 */}
      <td className="py-2 px-2 text-sm text-gray-500 dark:text-slate-400 text-right">
        <HostActionsMenu
          host={host}
          handleDelete={handleDeleteRequest}
          onOpenDrawer={onOpenDrawer} // Pass the renamed prop for drawer
          POLLABLE_STATUSES={POLLABLE_STATUSES}
          onInstallQlfilter={onInstallQlfilter} // Pass down specific QLFilter prop
          onUninstallQlfilter={onUninstallQlfilter} // Pass down specific QLFilter prop
          onRequestRestart={onRequestRestart} // Pass onRequestRestart to HostActionsMenu
        />
      </td>
    </tr>
  );
}

export default HostsTableRow;
