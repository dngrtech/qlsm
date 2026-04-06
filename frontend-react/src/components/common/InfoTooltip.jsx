import { useState, useRef, useEffect } from 'react';
import { useFloating, offset, flip, shift, arrow, autoUpdate } from '@floating-ui/react-dom';
import { Info } from 'lucide-react';

/**
 * Reusable info tooltip with instant hover response and themed design.
 *
 * @param {string}  text       - Tooltip message text
 * @param {number}  [size=14]  - Icon size in px
 * @param {'top'|'bottom'|'left'|'right'} [placement='top'] - Preferred placement
 * @param {string}  [iconClassName] - Extra classes for the icon wrapper
 * @param {string}  [className]     - Extra classes for the outer container
 * @param {'info'|'cyan'|'warning'|'danger'} [variant='info'] - Color scheme
 */
function InfoTooltip({ text, size = 14, placement = 'top', iconClassName = '', className = '', variant = 'info' }) {
  const [open, setOpen] = useState(false);
  const arrowRef = useRef(null);
  const hoverTimeout = useRef(null);

  const { x, y, refs, strategy, middlewareData, placement: finalPlacement } = useFloating({
    placement,
    middleware: [
      offset(8),
      flip({ fallbackPlacements: ['bottom', 'left', 'right'] }),
      shift({ padding: 8 }),
      arrow({ element: arrowRef }),
    ],
    whileElementsMounted: autoUpdate,
  });

  useEffect(() => {
    return () => { if (hoverTimeout.current) clearTimeout(hoverTimeout.current); };
  }, []);

  const handleEnter = () => {
    if (hoverTimeout.current) clearTimeout(hoverTimeout.current);
    setOpen(true);
  };

  const handleLeave = () => {
    hoverTimeout.current = setTimeout(() => setOpen(false), 100);
  };

  // Variant-based colors using CSS variables + explicit values
  const variantStyles = {
    info: {
      icon: 'var(--text-muted)',
      iconHover: 'var(--accent-info)',
      bg: 'var(--surface-overlay)',
      border: 'var(--surface-border-strong)',
      text: 'var(--text-secondary)',
    },
    cyan: {
      icon: 'var(--accent-info)',
      iconHover: 'var(--accent-info)',
      bg: 'var(--surface-overlay)',
      border: 'var(--accent-info)',
      text: 'var(--text-secondary)',
    },
    warning: {
      icon: 'var(--accent-warning)',
      iconHover: 'var(--accent-warning)',
      bg: 'var(--surface-overlay)',
      border: 'var(--accent-warning)',
      text: 'var(--text-secondary)',
    },
    danger: {
      icon: 'var(--accent-danger)',
      iconHover: 'var(--accent-danger)',
      bg: 'var(--surface-overlay)',
      border: 'var(--accent-danger)',
      text: 'var(--text-secondary)',
    },
  };

  const colors = variantStyles[variant] || variantStyles.info;

  // Arrow positioning based on final placement side
  const side = finalPlacement.split('-')[0];
  const arrowSide = { top: 'bottom', bottom: 'top', left: 'right', right: 'left' }[side];
  const arrowX = middlewareData.arrow?.x;
  const arrowY = middlewareData.arrow?.y;

  return (
    <span className={`inline-flex items-center ${className}`}>
      <span
        ref={refs.setReference}
        onMouseEnter={handleEnter}
        onMouseLeave={handleLeave}
        className={`inline-flex cursor-help transition-colors duration-150 ${iconClassName}`}
        style={{ color: open ? colors.iconHover : colors.icon }}
      >
        <Info size={size} />
      </span>

      {open && (
        <div
          ref={refs.setFloating}
          role="tooltip"
          onMouseEnter={handleEnter}
          onMouseLeave={handleLeave}
          style={{
            position: strategy,
            top: y ?? 0,
            left: x ?? 0,
            zIndex: 50,
          }}
        >
          <div
            className="tooltip-bubble"
            style={{
              background: colors.bg,
              borderColor: colors.border,
              color: colors.text,
            }}
          >
            {text}

            {/* Arrow */}
            <span
              ref={arrowRef}
              className="tooltip-arrow"
              style={{
                left: arrowX != null ? `${arrowX}px` : '',
                top: arrowY != null ? `${arrowY}px` : '',
                [arrowSide]: '-4px',
                borderColor: colors.border,
                background: colors.bg,
              }}
            />
          </div>
        </div>
      )}
    </span>
  );
}

export default InfoTooltip;
