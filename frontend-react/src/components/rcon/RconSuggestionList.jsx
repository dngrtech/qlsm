function RconSuggestionList({ id, items, activeIndex, onPick }) {
  if (!items.length) return null;
  return (
    <ul
      id={id}
      role="listbox"
      className="absolute bottom-full left-0 right-0 z-20 mx-4 mb-1 max-h-72 overflow-y-auto rounded-md border border-theme bg-theme-elevated py-1 shadow-lg sm:mx-6"
    >
      {items.map((item, index) => (
        <li
          key={item.label}
          id={`${id}-${index}`}
          role="option"
          aria-selected={index === activeIndex}
          // mousedown, not click: keeps focus in the input.
          onMouseDown={(event) => { event.preventDefault(); onPick(index); }}
          className={`flex cursor-pointer items-baseline gap-3 border-l-2 px-3 py-1.5 font-mono text-sm ${index === activeIndex ? 'bg-theme-overlay' : 'border-transparent'}`}
          style={index === activeIndex ? { borderLeftColor: 'var(--accent-primary)' } : undefined}
        >
          <span className="shrink-0" style={{ color: index === activeIndex ? 'var(--accent-primary)' : 'var(--text-primary)' }}>{item.label}</span>
          <span className="shrink-0 text-xs text-theme-muted">{item.detail}</span>
          {item.description && (
            <span className="min-w-0 truncate font-sans text-xs text-theme-secondary">{item.description}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

export default RconSuggestionList;
