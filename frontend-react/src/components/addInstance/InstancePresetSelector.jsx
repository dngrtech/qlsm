import React, { Fragment } from 'react';
import { Listbox, Transition } from '@headlessui/react';
import { Check, ChevronsUpDown } from 'lucide-react';
import { classNames } from '../../utils/uiUtils'; // Adjusted path

function InstancePresetSelector({
  selectedPresetId,
  onPresetChange,
  presets,
  loadingPresets,
  noPresetText = '-- No Preset (Use Defaults/Manual Input) --', // Added prop with default
  label = 'Configuration Preset (Optional)', // Added label prop
}) {
  return (
    <div>
      <label htmlFor="selectedPresetId" className="block text-sm font-medium text-gray-700 dark:text-gray-300">
        {label}
      </label>
      <Listbox value={selectedPresetId} onChange={onPresetChange} disabled={loadingPresets}>
        {({ open }) => (
          <div>
            <div className="relative mt-1">
              <Listbox.Button className="relative w-full cursor-default rounded-md bg-white dark:bg-slate-700 py-2 pl-3 pr-10 text-left text-gray-900 dark:text-gray-200 shadow-sm border border-gray-300 dark:border-slate-600 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm disabled:cursor-not-allowed disabled:bg-gray-200 dark:disabled:bg-slate-600/50 disabled:text-gray-500 dark:disabled:text-gray-400">
                <span className="block truncate">
                  {selectedPresetId ? presets.find(p => p.id.toString() === selectedPresetId)?.name : (loadingPresets ? 'Loading presets...' : noPresetText)}
                </span>
                <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
                  <ChevronsUpDown className="h-5 w-5 text-gray-400" aria-hidden="true" />
                </span>
              </Listbox.Button>
              <Transition
                show={open}
                as="div" // Changed from Fragment to div to ensure it's a valid child for Transition if needed, though Fragment is usually fine.
                leave="transition ease-in duration-100"
                leaveFrom="opacity-100"
                leaveTo="opacity-0"
              >
                <Listbox.Options className="absolute z-10 mt-1 max-h-60 w-full overflow-auto rounded-md bg-white dark:bg-slate-700 py-1 text-base shadow-lg ring-1 ring-black dark:ring-black/20 ring-opacity-5 focus:outline-none sm:text-sm">
                  <Listbox.Option
                    key="no-preset" // Ensure key is unique if this component is used multiple times with different noPresetTexts
                    className={({ active }) =>
                      classNames(
                        active ? 'bg-indigo-600 text-white dark:bg-indigo-500' : 'text-gray-900 dark:text-gray-200',
                        'relative cursor-default select-none py-2 pl-3 pr-9'
                      )
                    }
                    value=""
                  >
                    {({ selected, active }) => (
                      <>
                        <span className={classNames(selected ? 'font-semibold' : 'font-normal', 'block truncate')}>
                          {noPresetText}
                        </span>
                        {selected ? (
                          <span
                            className={classNames(
                              active ? 'text-white' : 'text-indigo-600 dark:text-indigo-400',
                              'absolute inset-y-0 right-0 flex items-center pr-4'
                            )}
                          >
                            <Check className="h-5 w-5" aria-hidden="true" />
                          </span>
                        ) : null}
                      </>
                    )}
                  </Listbox.Option>
                  {presets.map((preset) => (
                    <Listbox.Option
                      key={preset.id}
                      className={({ active }) =>
                        classNames(
                          active ? 'bg-indigo-600 text-white dark:bg-indigo-500' : 'text-gray-900 dark:text-gray-200',
                          'relative cursor-default select-none py-2 pl-3 pr-9'
                        )
                      }
                      value={preset.id.toString()}
                    >
                      {({ selected, active }) => (
                        <>
                          <span className={classNames(selected ? 'font-semibold' : 'font-normal', 'block truncate')}>
                            {preset.name}
                          </span>
                          {selected ? (
                            <span
                              className={classNames(
                                active ? 'text-white' : 'text-indigo-600 dark:text-indigo-400',
                                'absolute inset-y-0 right-0 flex items-center pr-4'
                              )}
                            >
                              <Check className="h-5 w-5" aria-hidden="true" />
                            </span>
                          ) : null}
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
  );
}

export default InstancePresetSelector;
