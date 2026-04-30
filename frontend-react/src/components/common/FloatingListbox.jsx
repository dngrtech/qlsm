import React, { Fragment } from 'react';
import { Listbox, Transition, Portal } from '@headlessui/react';
import { useFloating, offset, flip, shift, autoUpdate } from '@floating-ui/react-dom';
import { Check, ChevronsUpDown } from 'lucide-react';

function OptionBadge({ children }) {
  if (!children) return null;

  return (
    <span className="shrink-0 whitespace-nowrap rounded border border-[var(--accent-primary)] bg-[var(--surface-elevated)] px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase text-[var(--accent-primary)]">
      {children}
    </span>
  );
}

function FloatingListbox({
  value,
  onChange,
  options,
  label,
  disabled = false,
  getOptionKey = (option) => option.id,
  getOptionValue = null,
  getOptionDisplay = (option) => option.name,
  getOptionBadge = null,
  getSelectedDisplay = (selectedValue, opts) => {
    if (!selectedValue) return `Select ${label.toLowerCase()}`;
    const actualOptionValueFn = getOptionValue || getOptionKey;
    const selectedOption = opts.find(opt => actualOptionValueFn(opt) === selectedValue);
    return selectedOption ? getOptionDisplay(selectedOption) : `Select ${label.toLowerCase()}`;
  },
  placeholder = `Select ${label.toLowerCase()}`,
  noOptionsMessage = "No options available."
}) {
  const optionValueFn = getOptionValue || getOptionKey;
  const selectedOption = options.find(opt => optionValueFn(opt) === value);
  const selectedBadge = selectedOption && getOptionBadge?.(selectedOption);
  const selectedDisplay = getSelectedDisplay(value, options) || placeholder;

  const { x, y, strategy, refs } = useFloating({
    placement: 'bottom-start',
    middleware: [offset(4), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  });

  return (
    <Listbox value={value} onChange={onChange} disabled={disabled}>
      {({ open }) => (
        <div>
          {label && <Listbox.Label className="block text-sm font-medium text-theme-secondary">{label}</Listbox.Label>}
          <div className="relative mt-1">
            <Listbox.Button
              ref={refs.setReference}
              className="relative w-full cursor-default rounded-lg py-2 pl-3 pr-10 text-left text-sm text-theme-primary focus:outline-none focus:ring-1 transition-colors disabled:cursor-not-allowed disabled:opacity-40"
              style={{
                background: 'var(--surface-elevated)',
                border: '1px solid var(--surface-border)',
              }}
            >
              <span className="flex min-w-0 items-center gap-2">
                <span className="block min-w-0 flex-1 truncate">{selectedDisplay}</span>
                {selectedBadge && (
                  <span className="shrink-0 mr-[74px]">
                    <OptionBadge>{selectedBadge}</OptionBadge>
                  </span>
                )}
              </span>
              <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
                <ChevronsUpDown className="h-4 w-4 text-theme-muted" aria-hidden="true" />
              </span>
            </Listbox.Button>
            {open && (
              <Portal>
                <Transition
                  as={Fragment}
                  show={open}
                  enter="transition ease-out duration-100"
                  enterFrom="transform opacity-0 scale-95"
                  enterTo="transform opacity-100 scale-100"
                  leave="transition ease-in duration-100"
                  leaveFrom="transform opacity-100 scale-100"
                  leaveTo="transform opacity-0 scale-95"
                >
                  <Listbox.Options
                    ref={refs.setFloating}
                    style={{
                      position: strategy,
                      top: y ?? 0,
                      left: x ?? 0,
                      width: refs.reference.current?.offsetWidth,
                      zIndex: 9999,
                      background: 'var(--surface-raised)',
                      border: '1px solid var(--surface-border)',
                    }}
                    className="max-h-60 overflow-auto rounded-lg py-1 text-sm shadow-lg focus:outline-none scrollbar-thick"
                  >
                    {options.length === 0 ? (
                      <div className="relative cursor-default select-none py-2 px-4 text-theme-muted">
                        {noOptionsMessage}
                      </div>
                    ) : (
                      options.map((option) => {
                        const optionKeyValue = getOptionKey(option);
                        const displayValue = getOptionDisplay(option);
                        const valueForOption = optionValueFn(option);
                        const badge = getOptionBadge?.(option);

                        return (
                          <Listbox.Option
                            key={optionKeyValue}
                            value={valueForOption}
                            className={({ active }) =>
                              `relative cursor-default select-none py-2 px-3 transition-colors ${active ? 'bg-black/[0.04] dark:bg-white/[0.06] text-theme-primary' : 'text-theme-secondary'
                              }`
                            }
                          >
                            {({ selected }) => (
                              <div className="flex w-full min-w-0 items-center gap-2">
                                <span className={`block min-w-0 flex-1 truncate ${selected ? 'font-semibold' : 'font-normal'}`}>
                                  {displayValue}
                                </span>
                                {(badge || selected) && (
                                  <span className="grid w-40 shrink-0 grid-cols-[1fr_auto] items-center gap-2">
                                    <span className="justify-self-start">
                                      <OptionBadge>{badge}</OptionBadge>
                                    </span>
                                    {selected && (
                                      <Check className="h-4 w-4" style={{ color: 'var(--accent-primary)' }} aria-hidden="true" />
                                    )}
                                    {!selected && <span className="h-4 w-4" aria-hidden="true" />}
                                  </span>
                                )}
                              </div>
                            )}
                          </Listbox.Option>
                        );
                      })
                    )}
                  </Listbox.Options>
                </Transition>
              </Portal>
            )}
          </div>
        </div>
      )}
    </Listbox>
  );
}

export default FloatingListbox;
