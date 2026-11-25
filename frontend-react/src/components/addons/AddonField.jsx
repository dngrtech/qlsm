import React from 'react';
import { Eye, EyeOff } from 'lucide-react';
import FloatingListbox from '../common/FloatingListbox';

/**
 * One manifest-declared field.
 *
 * Styling mirrors the rest of QLSM's forms (CSS custom properties, not hard
 * colours) so an addon's panel is visually indistinguishable from a built-in
 * one -- which is the whole point of the declarative tier.
 */
function AddonField({ field, value, error, disabled, onChange }) {
  const [revealed, setRevealed] = React.useState(false);
  // Unique per rendered field: hidden tabs stay mounted, and two panels (or
  // two addons) can declare the same key.
  const inputId = `addon-field-${React.useId()}-${field.key}`;

  const baseInputClass =
    'w-full rounded-md border px-3 py-2 text-sm transition-colors focus:outline-none disabled:opacity-50 disabled:cursor-not-allowed';
  const inputStyle = {
    background: 'var(--surface-base)',
    borderColor: error ? 'var(--accent-danger)' : 'var(--surface-border)',
    color: 'var(--text-primary)',
  };

  if (field.type === 'bool') {
    return (
      <div className="flex items-start gap-3 py-2">
        <input
          id={inputId}
          type="checkbox"
          checked={Boolean(value)}
          disabled={disabled}
          onChange={(e) => onChange(field.key, e.target.checked)}
          className="mt-0.5 h-4 w-4 flex-shrink-0 cursor-pointer disabled:cursor-not-allowed"
        />
        <div className="min-w-0">
          <label htmlFor={inputId} className="text-sm text-theme-primary cursor-pointer">
            {field.label}
          </label>
          {field.description && (
            <p className="mt-0.5 text-xs text-theme-muted">{field.description}</p>
          )}
        </div>
      </div>
    );
  }

  if (field.type === 'select') {
    const options = (Array.isArray(field.options) ? field.options : []).map((option) => {
      const optionValue = option && typeof option === 'object' ? option.value : option;
      const optionLabel = option && typeof option === 'object' ? (option.label ?? option.value) : option;
      return { value: optionValue, label: String(optionLabel) };
    });
    const placeholder = field.placeholder || `Select ${String(field.label ?? '').toLowerCase()}`;
    return (
      <div className="py-2">
        <FloatingListbox
          label={field.label}
          value={value ?? ''}
          onChange={(next) => onChange(field.key, next)}
          options={options}
          disabled={disabled}
          getOptionKey={(option) => option.value}
          getOptionDisplay={(option) => option.label}
          getSelectedDisplay={(selected, opts) => opts.find((o) => o.value === selected)?.label ?? placeholder}
          placeholder={placeholder}
        />
        {field.description && !error && (
          <p className="mt-1 text-xs text-theme-muted">{field.description}</p>
        )}
        {error && (
          <p className="mt-1 text-xs" style={{ color: 'var(--accent-danger)' }}>{error}</p>
        )}
      </div>
    );
  }

  return (
    <div className="py-2">
      <label htmlFor={inputId} className="mb-1 block text-sm text-theme-primary">
        {field.label}
      </label>
      <div className="relative">
        <input
          id={inputId}
          type={field.type === 'number' ? 'number' : (field.type === 'secret' && !revealed ? 'password' : 'text')}
          value={value ?? ''}
          min={field.min}
          max={field.max}
          placeholder={field.placeholder}
          disabled={disabled}
          onChange={(e) => onChange(field.key, e.target.value)}
          className={`${baseInputClass} ${field.type === 'secret' ? 'pr-10' : ''}`}
          style={inputStyle}
        />
        {field.type === 'secret' && (
          <button
            type="button"
            onClick={() => setRevealed(r => !r)}
            aria-label={revealed ? 'Hide value' : 'Show value'}
            className="absolute inset-y-0 right-0 flex items-center px-3 text-theme-muted hover:text-theme-primary"
          >
            {revealed ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
        )}
      </div>
      {field.description && !error && (
        <p className="mt-1 text-xs text-theme-muted">{field.description}</p>
      )}
      {error && (
        <p className="mt-1 text-xs" style={{ color: 'var(--accent-danger)' }}>{error}</p>
      )}
    </div>
  );
}

export default AddonField;
