import { Listbox, Transition } from '@headlessui/react';
import { Check, ChevronsUpDown, Zap } from 'lucide-react';

function InstanceBasicInfoForm({
  name, onNameChange,
  selectedHostId, onHostChange, hosts,
  port, onPortChange, availablePorts, loadingPorts,
  hostname, onHostnameChange,
  lanRateEnabled, onLanRateChange,
  lanRateDisabled = false,
  lanRateUnavailableReason = null,
}) {
  const listboxBtnClass = 'relative w-full cursor-default rounded py-2 pl-3 pr-10 text-left text-sm border bg-[var(--surface-raised)] border-[var(--surface-border)] text-[var(--text-primary)] focus:outline-none focus:border-[var(--accent-primary)] transition-colors';
  const listboxOptionsClass = 'absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded bg-[var(--surface-overlay)] border border-[var(--surface-border)] py-1 text-sm shadow-xl focus:outline-none scrollbar-thin';

  return (
    <>
      <div className="grid grid-cols-[1.2fr_1fr_0.5fr_1.8fr] gap-4 mb-4">
        {/* Instance Name */}
        <div>
          <label htmlFor="name" className="label-tech mb-1.5 block">
            Instance Name <span className="text-[var(--accent-danger)]">*</span>
          </label>
          <input
            id="name"
            type="text"
            value={name}
            onChange={onNameChange}
            required
            className="input-base"
            placeholder="e.g. My FFA Server"
          />
        </div>

        {/* Host Server */}
        <div>
          <Listbox value={selectedHostId} onChange={onHostChange}>
            {({ open }) => (
              <div>
                <Listbox.Label className="label-tech mb-1.5 block">
                  Host Server <span className="text-[var(--accent-danger)]">*</span>
                </Listbox.Label>
                <div className="relative">
                  <Listbox.Button className={listboxBtnClass}>
                    <span className="block truncate">
                      {selectedHostId ? hosts.find(h => h.id.toString() === selectedHostId)?.name : 'Select Host'}
                    </span>
                    <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
                      <ChevronsUpDown className="h-4 w-4 text-[var(--text-muted)]" aria-hidden="true" />
                    </span>
                  </Listbox.Button>
                  <Transition show={open} as="div" leave="transition ease-in duration-100" leaveFrom="opacity-100" leaveTo="opacity-0">
                    <Listbox.Options className={listboxOptionsClass}>
                      {hosts.map((host) => (
                        <Listbox.Option
                          key={host.id}
                          className={({ active }) => `relative cursor-default select-none py-2 pl-3 pr-9 transition-colors ${active ? 'bg-[var(--accent-primary)] text-black' : 'text-[var(--text-primary)]'}`}
                          value={host.id.toString()}
                        >
                          {({ selected, active }) => (
                            <>
                              <span className={`block truncate ${selected ? 'font-semibold' : 'font-normal'}`}>
                                {host.name}
                                <span className={`text-xs ml-2 ${active ? 'text-black/60' : 'text-[var(--text-muted)]'}`}>
                                  ({host.provider} - {host.ip_address || 'No IP'})
                                </span>
                              </span>
                              {selected && (
                                <span className={`absolute inset-y-0 right-0 flex items-center pr-4 ${active ? 'text-black' : 'text-[var(--accent-primary)]'}`}>
                                  <Check className="h-4 w-4" aria-hidden="true" />
                                </span>
                              )}
                            </>
                          )}
                        </Listbox.Option>
                      ))}
                    </Listbox.Options>
                  </Transition>
                </div>
              </div>
            )}
          </Listbox>
        </div>

        {/* Port */}
        <div>
          <Listbox value={port} onChange={onPortChange} disabled={!selectedHostId || loadingPorts}>
            {({ open }) => (
              <div>
                <Listbox.Label className="label-tech mb-1.5 block">
                  Port <span className="text-[var(--accent-danger)]">*</span>
                </Listbox.Label>
                <div className="relative">
                  <Listbox.Button className={`${listboxBtnClass} disabled:cursor-not-allowed disabled:opacity-50`}>
                    <span className="block truncate font-mono">
                      {port || (loadingPorts ? 'Loading...' : 'Select Port')}
                    </span>
                    <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
                      <ChevronsUpDown className="h-4 w-4 text-[var(--text-muted)]" aria-hidden="true" />
                    </span>
                  </Listbox.Button>
                  <Transition show={open} as="div" leave="transition ease-in duration-100" leaveFrom="opacity-100" leaveTo="opacity-0">
                    <Listbox.Options className={listboxOptionsClass}>
                      {availablePorts.length === 0 && !loadingPorts && selectedHostId && (
                        <div className="relative cursor-default select-none py-2 px-4 text-[var(--text-muted)]">No available ports.</div>
                      )}
                      {availablePorts.map((p) => (
                        <Listbox.Option
                          key={p}
                          className={({ active }) => `relative cursor-default select-none py-2 pl-3 pr-9 transition-colors ${active ? 'bg-[var(--accent-primary)] text-black' : 'text-[var(--text-primary)]'}`}
                          value={p.toString()}
                        >
                          {({ selected, active }) => (
                            <>
                              <span className={`block truncate font-mono ${selected ? 'font-semibold' : 'font-normal'}`}>{p}</span>
                              {selected && (
                                <span className={`absolute inset-y-0 right-0 flex items-center pr-4 ${active ? 'text-black' : 'text-[var(--accent-primary)]'}`}>
                                  <Check className="h-4 w-4" aria-hidden="true" />
                                </span>
                              )}
                            </>
                          )}
                        </Listbox.Option>
                      ))}
                    </Listbox.Options>
                  </Transition>
                </div>
              </div>
            )}
          </Listbox>
        </div>

        {/* Server Hostname */}
        <div>
          <label htmlFor="hostname" className="label-tech mb-1.5 block">Server Hostname</label>
          <div className="relative">
            <input
              id="hostname"
              type="text"
              value={hostname}
              onChange={onHostnameChange}
              required
              className="input-base pr-16"
              placeholder="A New Quake Live Dedicated Server"
            />
            <span className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none">
              <span className="font-mono text-[10px] font-bold tracking-wider uppercase px-1.5 py-0.5 rounded bg-[var(--surface-elevated)] border border-[var(--surface-border)] text-[var(--text-muted)]">
                AUTO
              </span>
            </span>
          </div>
        </div>
      </div>

      {/* LAN Rate Toggle */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => onLanRateChange(!lanRateEnabled)}
          className="neu-toggle"
          aria-pressed={lanRateEnabled}
          disabled={lanRateDisabled}
        >
          <span className="sr-only">Toggle 99k LAN Rate</span>
          <span className={`neu-toggle__track ${lanRateEnabled ? 'neu-toggle__track--on' : 'neu-toggle__track--off'}`}>
            <span className={`neu-toggle__knob ${lanRateEnabled ? 'neu-toggle__knob--on' : 'neu-toggle__knob--off'}`} />
          </span>
        </button>
        <span className="flex items-center text-sm font-medium text-[var(--text-primary)]">
          <Zap size={16} className={`mr-1 ${lanRateEnabled ? 'text-[var(--accent-warning)]' : 'text-[var(--text-muted)]'}`} />
          99k LAN Rate
        </span>
      </div>
      {lanRateUnavailableReason && (
        <p className="mt-2 text-sm text-theme-danger">
          {lanRateUnavailableReason}
        </p>
      )}
    </>
  );
}

export default InstanceBasicInfoForm;
