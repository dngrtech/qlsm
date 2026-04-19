import React, { useState, useEffect, Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { X, Server, AlertTriangle } from 'lucide-react';
import { createHost, getHosts, getSelfHostDefaults, testHostConnection } from '../../services/api';
import { useNotification } from '../NotificationProvider';
import { providerOptions } from '../../utils/providerData';
import AddHostFormFields from './AddHostFormFields';
import { validateHostName } from '../../utils/resourceValidation';
import { getTimezoneForRegion } from '../../utils/formatters';

const PROVIDER_LIST_OPTIONS = [
  { id: 'self', name: 'QLSM Host (self-deployment)' },
  { id: 'standalone', name: 'Standalone' },
  { id: 'vultr', name: 'VULTR' },
];

const DEFAULT_SELF_HOST_DEFAULTS = {
  ssh_user: 'root',
  host_ip: null,
  provider_capabilities: {
    vultr: {
      configured: true,
    },
  },
};

const VULTR_UNAVAILABLE_MESSAGE = 'Vultr deployment is unavailable until VULTR_API_KEY is added to the environment.';

function AddHostModal({ isOpen, onClose, onHostAdded }) {
  const [name, setName] = useState('');
  const [nameError, setNameError] = useState(null);
  const [provider, setProvider] = useState('self');
  const [selfHostExists, setSelfHostExists] = useState(false);
  const [providerOptionsReady, setProviderOptionsReady] = useState(false);
  const [selectedContinent, setSelectedContinent] = useState('');
  const [vultrContinentOptions, setVultrContinentOptions] = useState([]);
  const [region, setRegion] = useState('');
  const [machineSize, setMachineSize] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const { showSuccess, showError } = useNotification();
  const [selfHostDefaults, setSelfHostDefaults] = useState(DEFAULT_SELF_HOST_DEFAULTS);
  const [vultrConfigured, setVultrConfigured] = useState(true);

  // Standalone-specific state
  const [ipAddress, setIpAddress] = useState('');
  const [sshPort, setSshPort] = useState(22);
  const [sshUser, setSshUser] = useState('root');
  const [sshKey, setSshKey] = useState('');
  const [sshPassword, setSshPassword] = useState('');
  const [standaloneAuthMethod, setStandaloneAuthMethod] = useState('key');
  const [timezone, setTimezone] = useState('');

  // Connection test state
  const [connectionTestStatus, setConnectionTestStatus] = useState('idle');
  const [connectionTestMessage, setConnectionTestMessage] = useState('');

  const availableProviderOptions = PROVIDER_LIST_OPTIONS.filter(
    (option) => option.id !== 'self' || !selfHostExists
  );
  const isVultrUnavailable = provider === 'vultr' && !vultrConfigured;

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    setProviderOptionsReady(false);

    Promise.allSettled([getHosts(), getSelfHostDefaults()])
      .then(([hostsResult, defaultsResult]) => {
        if (cancelled) return;

        if (hostsResult.status === 'fulfilled') {
          const hasSelfHost = hostsResult.value.some((host) => host.provider === 'self');
          setSelfHostExists(hasSelfHost);
          setProvider(hasSelfHost ? 'standalone' : 'self');
        } else {
          const message = hostsResult.reason?.error?.message || hostsResult.reason?.message || 'Failed to load host options.';
          showError(message);
          setSelfHostExists(false);
          setProvider('self');
        }

        if (defaultsResult.status === 'fulfilled') {
          const defaults = defaultsResult.value || DEFAULT_SELF_HOST_DEFAULTS;
          setSelfHostDefaults(defaults);
          setVultrConfigured(defaults.provider_capabilities?.vultr?.configured ?? true);
        } else {
          const message = defaultsResult.reason?.error?.message || defaultsResult.reason?.message || 'Failed to load self-host defaults.';
          showError(message);
          setSelfHostDefaults(DEFAULT_SELF_HOST_DEFAULTS);
          setVultrConfigured(true);
        }

        setProviderOptionsReady(true);
      });

    return () => {
      cancelled = true;
    };
  }, [isOpen, showError]);

  useEffect(() => {
    if (provider === 'vultr') {
      const uniqueContinents = [...new Set(providerOptions.vultr.regions.map(r => r.continent))].sort();
      setVultrContinentOptions(uniqueContinents.map(c => ({ id: c.toLowerCase().replace(/\s+/g, '-'), name: c })));
    } else {
      setSelectedContinent('');
      setVultrContinentOptions([]);
    }
    setRegion('');
    setMachineSize('');
  }, [provider]);

  useEffect(() => {
    if (!isOpen || !providerOptionsReady || provider !== 'self') return;
    setSshUser(selfHostDefaults?.ssh_user || 'root');
    setIpAddress(selfHostDefaults?.host_ip || '');
  }, [isOpen, provider, providerOptionsReady, selfHostDefaults]);

  const resetForm = () => {
    setName('');
    setNameError(null);
    setProvider(selfHostExists ? 'standalone' : 'self');
    setSelectedContinent('');
    setRegion('');
    setMachineSize('');
    setError(null);
    setLoading(false);
    setIpAddress('');
    setSshPort(22);
    setSshUser('root');
    setSshKey('');
    setSshPassword('');
    setStandaloneAuthMethod('key');
    setTimezone('');
    setConnectionTestStatus('idle');
    setConnectionTestMessage('');
    setSelfHostDefaults(DEFAULT_SELF_HOST_DEFAULTS);
    setVultrConfigured(true);
    setProviderOptionsReady(false);
  };

  const resetConnectionTest = () => {
    setConnectionTestStatus('idle');
    setConnectionTestMessage('');
  };

  const buildStandaloneConnectionData = () => ({
    ip_address: ipAddress.trim(),
    ssh_port: parseInt(sshPort, 10) || 22,
    ssh_user: sshUser.trim(),
    ssh_auth_method: standaloneAuthMethod,
    ...(standaloneAuthMethod === 'password'
      ? { ssh_password: sshPassword }
      : { ssh_key: sshKey }),
  });

  const handleStandaloneAuthMethodChange = (value) => {
    setStandaloneAuthMethod(value);
    if (value === 'password') {
      setSshKey('');
    } else {
      setSshPassword('');
    }
    resetConnectionTest();
  };

  const handleTestConnection = async () => {
    setConnectionTestStatus('testing');
    setConnectionTestMessage('');
    try {
      const result = await testHostConnection(buildStandaloneConnectionData());
      if (result.success) {
        setConnectionTestStatus('success');
        setConnectionTestMessage(result.message || 'Connection successful');
      } else {
        setConnectionTestStatus('failed');
        setConnectionTestMessage(result.message || 'Connection failed');
      }
    } catch (err) {
      setConnectionTestStatus('failed');
      setConnectionTestMessage(err.error?.message || err.message || 'Connection test failed');
    }
  };

  const handleNameBlur = () => {
    if (name.trim()) {
      const error = validateHostName(name);
      setNameError(error);
    }
  };

  const handleClose = () => {
    resetForm();
    onClose();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);

    if (isVultrUnavailable) {
      return;
    }

    const validationError = validateHostName(name);
    if (validationError) {
      setNameError(validationError);
      return;
    }
    setNameError(null);

    if (provider === 'standalone') {
      if (!ipAddress || !ipAddress.trim()) {
        setError('IP address is required for standalone hosts.');
        return;
      }
      if (standaloneAuthMethod === 'password' && (!sshPassword || !sshPassword.trim())) {
        setError('SSH password is required for password bootstrap.');
        return;
      }
      if (standaloneAuthMethod !== 'password' && (!sshKey || !sshKey.trim())) {
        setError('SSH private key is required for standalone hosts.');
        return;
      }
      if (!sshUser || !sshUser.trim()) {
        setError('SSH username is required for standalone hosts.');
        return;
      }
      if (!timezone) {
        setError('Timezone is required for standalone hosts.');
        return;
      }
    }
    if (provider === 'self') {
      if (!ipAddress || !ipAddress.trim()) {
        setError('Server address is required for self hosts.');
        return;
      }
      if (!timezone) {
        setError('Timezone is required for self hosts.');
        return;
      }
      if (!sshUser || !sshUser.trim()) {
        setError('SSH user is required for self hosts.');
        return;
      }
    }

    setLoading(true);
    try {
      let hostData;
      if (provider === 'standalone') {
        hostData = {
          name: name.trim().toLowerCase(),
          provider: 'standalone',
          ip_address: ipAddress.trim(),
          ssh_port: parseInt(sshPort, 10) || 22,
          ssh_user: sshUser.trim(),
          ssh_auth_method: standaloneAuthMethod,
          ...(standaloneAuthMethod === 'password'
            ? { ssh_password: sshPassword }
            : { ssh_key: sshKey }),
          timezone,
        };
      } else if (provider === 'self') {
        hostData = {
          name: name.trim().toLowerCase(),
          provider: 'self',
          ip_address: ipAddress.trim(),
          timezone,
          ssh_user: sshUser.trim(),
        };
      } else {
        hostData = {
          name: name.trim().toLowerCase(),
          provider,
          region,
          machine_size: machineSize,
          timezone: getTimezoneForRegion(region),
        };
      }

      const response = await createHost(hostData);
      const successMessage = provider === 'self'
        ? response.message || 'Self host added and setup task queued.'
        : provider === 'standalone'
          ? response.message || 'Standalone host added and setup task queued.'
          : response.message || 'Host added and provisioning task queued.';
      showSuccess(successMessage);
      if (onHostAdded) onHostAdded();
      handleClose();
    } catch (err) {
      const errorMessage = err.error?.message || err.message || 'Failed to add host. Please check details and try again.';
      setError(errorMessage);
      showError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const vultrAllRegions = providerOptions.vultr.regions || [];
  const vultrFilteredRegions = selectedContinent && provider === 'vultr'
    ? vultrAllRegions.filter(r => r.continent === selectedContinent)
    : [];
  const currentSizes = providerOptions[provider]?.sizes || [];

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={handleClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" aria-hidden="true" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto scrollbar-thick">
          <div className="flex min-h-full items-center justify-center p-4">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel
                className="w-full max-w-2xl transform overflow-hidden rounded-xl text-left align-middle shadow-2xl transition-all"
                style={{
                  background: 'var(--surface-overlay)',
                  border: '1px solid var(--surface-border)',
                }}
              >
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-4" style={{ borderBottom: '1px solid var(--surface-border)' }}>
                  <div className="flex items-center gap-3">
                    <div className="flex items-center justify-center w-8 h-8 rounded-lg" style={{ background: 'rgba(0, 255, 157, 0.1)' }}>
                      <Server size={16} style={{ color: 'var(--accent-primary)' }} />
                    </div>
                    <Dialog.Title as="h3" className="text-base font-semibold text-theme-primary" style={{ fontFamily: 'var(--font-display)' }}>
                      Add New Host
                    </Dialog.Title>
                  </div>
                  <button
                    type="button"
                    onClick={handleClose}
                    className="logs-modal-close-btn"
                  >
                    <X size={18} />
                  </button>
                </div>

                {/* Body */}
                <form onSubmit={handleSubmit}>
                  <div className="px-6 py-5 space-y-5">
                    {providerOptionsReady ? (
                      <AddHostFormFields
                        name={name}
                        onNameChange={(e) => {
                          setName(e.target.value);
                          if (nameError) setNameError(null);
                        }}
                        nameError={nameError}
                        onNameBlur={handleNameBlur}
                        provider={provider}
                        providerListOptions={availableProviderOptions}
                        onProviderChange={(value) => {
                          setProvider(value);
                          setError(null);
                          resetConnectionTest();
                        }}
                        vultrConfigured={vultrConfigured}
                        vultrUnavailableMessage={VULTR_UNAVAILABLE_MESSAGE}
                        selectedContinent={selectedContinent}
                        onContinentChange={setSelectedContinent}
                        vultrContinentOptions={vultrContinentOptions}
                        region={region}
                        onRegionChange={setRegion}
                        vultrFilteredRegions={vultrFilteredRegions}
                        machineSize={machineSize}
                        onMachineSizeChange={setMachineSize}
                        currentSizes={currentSizes}
                        ipAddress={ipAddress}
                        onIpAddressChange={(e) => { setIpAddress(e.target.value); resetConnectionTest(); }}
                        sshPort={sshPort}
                        onSshPortChange={(e) => { setSshPort(e.target.value); resetConnectionTest(); }}
                        sshUser={sshUser}
                        onSshUserChange={(e) => { setSshUser(e.target.value); resetConnectionTest(); }}
                        standaloneAuthMethod={standaloneAuthMethod}
                        onStandaloneAuthMethodChange={handleStandaloneAuthMethodChange}
                        sshKey={sshKey}
                        onSshKeyChange={(e) => { setSshKey(e.target.value); resetConnectionTest(); }}
                        sshPassword={sshPassword}
                        onSshPasswordChange={(e) => { setSshPassword(e.target.value); resetConnectionTest(); }}
                        timezone={timezone}
                        onTimezoneChange={setTimezone}
                        connectionTestStatus={connectionTestStatus}
                        connectionTestMessage={connectionTestMessage}
                        onTestConnection={handleTestConnection}
                      />
                    ) : (
                      <div className="text-sm text-theme-muted">Loading host options...</div>
                    )}

                    {error && (
                      <div
                        className="flex items-start gap-2.5 px-3.5 py-3 rounded-lg text-sm"
                        style={{
                          background: 'rgba(255, 51, 102, 0.08)',
                          border: '1px solid rgba(255, 51, 102, 0.2)',
                          color: 'var(--accent-danger)',
                        }}
                      >
                        <AlertTriangle size={16} className="flex-shrink-0 mt-0.5" />
                        <span>{error}</span>
                      </div>
                    )}
                  </div>

                  {/* Footer */}
                  <div
                    className="flex justify-end gap-3 px-6 py-4"
                    style={{ borderTop: '1px solid var(--surface-border)' }}
                  >
                    <button
                      type="button"
                      onClick={handleClose}
                      className="px-4 py-2 rounded-lg text-sm font-medium text-theme-secondary hover:text-theme-primary hover:bg-black/[0.04] dark:hover:bg-white/[0.06] transition-colors"
                      style={{ border: '1px solid var(--surface-border)' }}
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={loading || !providerOptionsReady || isVultrUnavailable || (provider === 'standalone' && connectionTestStatus !== 'success')}
                      className="px-5 py-2 rounded-lg text-sm font-semibold transition-all disabled:opacity-40 disabled:cursor-not-allowed text-white dark:text-[#0A0E14]"
                      style={{
                        background: 'var(--accent-primary)',
                      }}
                    >
                      {loading ? (
                        <span className="flex items-center gap-2">
                          <span className="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin" />
                          Adding Host...
                        </span>
                      ) : (
                        'Add Host'
                      )}
                    </button>
                  </div>
                </form>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  );
}

export default AddHostModal;
