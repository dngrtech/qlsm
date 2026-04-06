import React, { useState } from 'react'; // Added useState
import { LoaderCircle, AlertTriangle, Zap, Copy, Check } from 'lucide-react'; // Added Zap, Copy, Check
import { formatStatus } from '../../utils/formatters';
import InstanceActionsMenu from '../InstanceActionsMenu'; // Path relative to InstancesTableRow.jsx
import { useNotification } from '../NotificationProvider'; // Added for copy notification
import InfoTooltip from '../common/InfoTooltip';

function InstancesTableRow({
  instance,
  handleRestartRequest,
  handleDeleteRequest,
  handleToggleLanRate, // Added for LAN rate toggle
  onOpenEditConfigModal, // Added new prop
  onViewInstanceDetails, // Added for the details drawer
  onOpenHostDrawer, // This prop IS used to open the drawer on InstancesPage
  onViewLogs, // Added for view logs modal
  onViewChatLogs, // Added for chat logs modal
  onOpenRconConsole, // RCON console callback
  POLLABLE_INSTANCE_STATUSES,
}) {
  const [ipCopied, setIpCopied] = useState(false);
  const { addNotification } = useNotification();

  const handleCopyIp = (ipAddress) => {
    if (!ipAddress) return;
    navigator.clipboard.writeText(ipAddress).then(() => {
      setIpCopied(true);
      addNotification('IP Address copied to clipboard!', 'success');
      setTimeout(() => setIpCopied(false), 2000);
    }).catch(err => {
      console.error('Failed to copy IP Address: ', err);
      addNotification('Failed to copy IP Address.', 'error');
    });
  };

  return (
    // Added dark mode hover and text colors
    <tr key={instance.id} className="hover:bg-gray-100 dark:hover:bg-slate-600">
      <td className="py-2 px-2 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-slate-100 truncate max-w-[150px]" title={instance.name}>
        <button
          onClick={() => onViewInstanceDetails(instance.id)}
          className="text-indigo-600 dark:text-indigo-400 hover:underline focus:outline-none text-left w-full"
        >
          {instance.name}
        </button>
      </td>
      {/* Added dark mode text and link colors */}
      <td className="py-2 px-2 text-sm text-gray-700 dark:text-slate-300">
        {instance.host_id && instance.host_name ? (
          <button
            onClick={() => onOpenHostDrawer(instance.host_id)} // ENSURED THIS IS CORRECT
            className="text-indigo-600 dark:text-indigo-400 hover:underline focus:outline-none text-left"
          >
            {instance.host_name}
          </button>
        ) : (
          <span className="dark:text-slate-400">N/A</span>
        )}
      </td>
      {/* IP Address Cell */}
      <td className="py-2 px-2 text-sm text-gray-700 dark:text-slate-300">
        {instance.host_ip_address ? (
          <div className="flex items-center space-x-1">
            <span className="truncate max-w-[120px] lg:max-w-none" title={instance.host_ip_address}>{instance.host_ip_address}</span>
            <button
              onClick={() => handleCopyIp(instance.host_ip_address)}
              className="p-0.5 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-300 focus:outline-none"
              title="Copy IP Address"
            >
              {ipCopied ? <Check size={14} className="text-green-500" /> : <Copy size={14} />}
            </button>
          </div>
        ) : (
          <span className="dark:text-slate-400">N/A</span>
        )}
      </td>
      {/* Added dark mode text color */}
      <td className="py-2 px-2 text-sm text-gray-700 dark:text-slate-300">{instance.port}</td>
      {/* Added dark mode text color */}
      <td className="py-2 px-2 text-sm text-gray-700 dark:text-slate-300" title={instance.hostname}>
        <div className="truncate max-w-[150px] lg:max-w-none">
          {instance.hostname}
        </div>
      </td>
      {/* Added dark mode text color for status badges */}
      <td className="py-2 px-2 text-sm">
        <span
          className={`px-2 inline-flex items-center text-xs leading-5 font-semibold rounded-full ${instance.status === 'running'
            ? 'bg-green-100 text-green-800 dark:bg-green-700 dark:text-green-100'
            : instance.status === 'updated'
              ? 'bg-cyan-100 text-cyan-800 dark:bg-cyan-900/40 dark:text-cyan-300'
              : instance.status === 'stopped' || instance.status === 'idle'
                ? 'bg-gray-100 text-gray-800 dark:bg-slate-600 dark:text-slate-100'
                : POLLABLE_INSTANCE_STATUSES.includes(instance.status)
                  ? 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-100'
                  : instance.status === 'error'
                    ? 'bg-red-100 text-red-800 dark:bg-red-700 dark:text-red-100'
                    : 'bg-blue-100 text-blue-800 dark:bg-blue-700 dark:text-blue-100'
            }`}
        >
          {instance.status === 'running' && !POLLABLE_INSTANCE_STATUSES.includes(instance.status) && (
            <span className="w-2 h-2 mr-1.5 bg-green-500 dark:bg-green-400 rounded-full"></span>
          )}
          {instance.status === 'updated' && (
            <InfoTooltip text="Configuration has been synced to the host but the instance has not been restarted. Restart to apply changes." variant="cyan" size={12} className="mr-1" />
          )}
          {instance.status === 'error' && (
            <AlertTriangle size={14} className="mr-1.5 text-red-700 dark:text-red-300" />
          )}
          {POLLABLE_INSTANCE_STATUSES.includes(instance.status) && !(instance.status === 'error') && (
            <LoaderCircle size={14} className="animate-spin mr-1.5" />
          )}
          <span>{formatStatus(instance.status)}</span>
        </span>
      </td>
      {/* Added dark mode text and button colors, changed to justify-center */}
      <td className="py-2 px-2 text-sm text-gray-500 dark:text-slate-400 align-middle">
        <div className="flex items-center justify-center space-x-2"> {/* Changed to justify-center */}
          {/* Connect Button/Span */}
          {instance.host_ip_address && instance.port ? (
            <a
              href={`steam://connect/${instance.host_ip_address}:${instance.port}`}
              title="Connect via Steam"
              className="inline-flex items-center justify-center p-1 rounded text-gray-500 dark:text-slate-400 hover:text-indigo-600 dark:hover:text-indigo-300 hover:bg-gray-200 dark:hover:bg-slate-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 dark:focus:ring-offset-slate-900"
              target="_blank"
              rel="noopener noreferrer"
            >
              <Zap size={16} className="mr-1" />
              Connect
            </a>
          ) : (
            <span title="Connect info unavailable" className="inline-flex items-center p-1 text-gray-300 cursor-not-allowed opacity-50">
              <Zap size={16} className="mr-1" />
              Connect
            </span>
          )}
          {/* Actions Menu */}
          <InstanceActionsMenu
            instance={instance}
            handleRestart={handleRestartRequest}
            handleDelete={handleDeleteRequest}
            handleToggleLanRate={handleToggleLanRate}
            onOpenEditConfigModal={onOpenEditConfigModal} // Pass down
            onViewInstanceDetails={() => onViewInstanceDetails(instance.id)} // Pass to actions menu
            onViewLogs={onViewLogs} // Pass to actions menu for View Logs
            onViewChatLogs={onViewChatLogs} // Pass to actions menu for Chat Logs
            onOpenRconConsole={onOpenRconConsole}
            POLLABLE_INSTANCE_STATUSES={POLLABLE_INSTANCE_STATUSES}
          />
        </div> {/* Closing the flex container div */}
      </td>
    </tr>
  );
}

export default InstancesTableRow;
