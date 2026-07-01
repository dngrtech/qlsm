import React, { Fragment } from 'react';
import { Combobox, Portal, Transition } from '@headlessui/react';
import { useFloating, offset, flip, shift, autoUpdate } from '@floating-ui/react-dom';
import { ChevronDown } from 'lucide-react';
import { classNames } from '../../utils/uiUtils';

function PresetNameCombobox({ value, onChange, presets = [], disabled = false, hasCaution = false }) {
  const { x, y, strategy, refs } = useFloating({
    placement: 'bottom-start',
    middleware: [offset(4), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  });

  const query = (value || '').trim().toLowerCase();
  const filtered = query
    ? presets.filter((p) => p.name.toLowerCase().includes(query))
    : presets;

  return (
    <Combobox value={value} onChange={onChange} disabled={disabled}>
      {({ open }) => (
        <div className="relative">
          <Combobox.Input
            ref={refs.setReference}
            aria-label="Preset Name"
            autoComplete="off"
            displayValue={(v) => v || ''}
            onChange={(e) => onChange(e.target.value)}
            placeholder="Type a new name, or pick one to overwrite…"
            className={classNames('input-base pr-10', hasCaution && 'input-caution')}
          />
          <Combobox.Button className="absolute inset-y-0 right-0 flex items-center pr-2">
            <ChevronDown className="h-4 w-4 text-[var(--text-muted)]" aria-hidden="true" />
          </Combobox.Button>
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
            <Portal>
              <Combobox.Options
                ref={refs.setFloating}
                style={{
                  position: strategy,
                  top: y ?? 0,
                  left: x ?? 0,
                  width: refs.reference.current?.offsetWidth,
                  zIndex: 9999,
                }}
                className="max-h-52 overflow-auto rounded-md bg-[var(--surface-overlay)] border border-[var(--surface-border)] py-1 text-sm shadow-xl focus:outline-none scrollbar-thin"
              >
                <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-[var(--text-muted)]">
                  Existing presets — select to overwrite
                </div>
                {filtered.length === 0 ? (
                  <div className="px-3 py-2 text-xs text-[var(--text-muted)]">
                    No matching presets — this will be saved as new.
                  </div>
                ) : (
                  filtered.map((preset) => (
                    <Combobox.Option
                      key={preset.id}
                      value={preset.name}
                      className={({ active }) =>
                        classNames(
                          active ? 'bg-[var(--accent-warning)]/10 text-[var(--accent-warning)]' : 'text-[var(--text-primary)]',
                          'flex cursor-pointer select-none items-center justify-between px-3 py-2'
                        )
                      }
                    >
                      {({ active }) => (
                        <>
                          <span className="truncate">{preset.name}</span>
                          <span className={classNames('text-[10px] uppercase tracking-wider text-[var(--accent-warning)]', active ? 'opacity-100' : 'opacity-0')}>
                            Overwrite →
                          </span>
                        </>
                      )}
                    </Combobox.Option>
                  ))
                )}
              </Combobox.Options>
            </Portal>
          </Transition>
        </div>
      )}
    </Combobox>
  );
}

export default PresetNameCombobox;
