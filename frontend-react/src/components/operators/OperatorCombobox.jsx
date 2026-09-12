import React, { Fragment, useState } from 'react';
import { Combobox, Portal, Transition } from '@headlessui/react';
import { useFloating, offset, flip, shift, autoUpdate } from '@floating-ui/react-dom';
import { ChevronDown } from 'lucide-react';
import { classNames } from '../../utils/uiUtils';

// Searchable operator picker (by name or SteamID64). `value` is a SteamID64
// string or ''; `onChange` receives the SteamID64 of the picked operator.
function OperatorCombobox({ value, onChange, operators = [], placeholder = 'Search operators…', disabled = false, allowClear = true }) {
  const [query, setQuery] = useState('');
  const { x, y, strategy, refs } = useFloating({
    placement: 'bottom-start',
    middleware: [offset(4), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  });

  // A SteamID that is not in the directory is still a real config value: fall
  // back to a synthetic entry so it renders as itself rather than as blank.
  const known = operators.find((op) => op.steam_id64 === value) || null;
  const selected = known || (value ? { id: `raw-${value}`, name: '', steam_id64: value } : null);
  const q = query.trim().toLowerCase();
  const filtered = q
    ? operators.filter((op) => op.name.toLowerCase().includes(q) || op.steam_id64.includes(q))
    : operators;

  return (
    <Combobox
      value={selected}
      onChange={(op) => onChange(op ? op.steam_id64 : '')}
      disabled={disabled}
    >
      {({ open }) => (
        <div className="relative">
          <Combobox.Input
            ref={refs.setReference}
            autoComplete="off"
            displayValue={(op) => (op ? (op.name ? `${op.name} (${op.steam_id64})` : op.steam_id64) : '')}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={placeholder}
            className="input-base pr-10"
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
            afterLeave={() => setQuery('')}
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
                {allowClear && (
                  <Combobox.Option
                    value={null}
                    className={({ active }) =>
                      classNames(
                        active ? 'bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]' : 'text-[var(--text-muted)]',
                        'cursor-pointer select-none px-3 py-2 italic'
                      )
                    }
                  >
                    None
                  </Combobox.Option>
                )}
                {filtered.length === 0 ? (
                  <div className="px-3 py-2 text-xs text-[var(--text-muted)]">
                    No matching operators.
                  </div>
                ) : (
                  filtered.map((op) => (
                    <Combobox.Option
                      key={op.id}
                      value={op}
                      className={({ active }) =>
                        classNames(
                          active ? 'bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]' : 'text-[var(--text-primary)]',
                          'flex cursor-pointer select-none items-center justify-between gap-2 px-3 py-2'
                        )
                      }
                    >
                      <span className="truncate">{op.name}</span>
                      <span className="font-mono text-[10px] text-[var(--text-muted)]">{op.steam_id64}</span>
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

export default OperatorCombobox;
