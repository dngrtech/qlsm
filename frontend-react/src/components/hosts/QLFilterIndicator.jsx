import { useState, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { useFloating, offset, flip, shift, arrow, autoUpdate } from '@floating-ui/react-dom';
import { QLFILTER_STATUS } from '../../utils/statusEnums';

function QLFilterIndicator({ qlfilterStatus }) {
  const [open, setOpen] = useState(false);
  const arrowRef = useRef(null);
  const hoverTimeout = useRef(null);

  const isEnabled = qlfilterStatus === QLFILTER_STATUS.ACTIVE;
  const iconSrc = isEnabled ? '/images/qlfilter-on.png' : '/images/qlfilter-off.png';
  const tooltipText = isEnabled ? 'QLFilter enabled' : 'QLFilter not installed';

  const { x, y, refs, strategy, middlewareData, placement: finalPlacement } = useFloating({
    placement: 'top',
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

  const side = finalPlacement.split('-')[0];
  const arrowSide = { top: 'bottom', bottom: 'top', left: 'right', right: 'left' }[side];
  const arrowX = middlewareData.arrow?.x;
  const arrowY = middlewareData.arrow?.y;

  return (
    <span className="inline-flex items-center justify-center">
      <span
        ref={refs.setReference}
        onMouseEnter={handleEnter}
        onMouseLeave={handleLeave}
        className="inline-flex cursor-default transition-opacity duration-150 hover:opacity-75"
      >
        <img
          src={iconSrc}
          alt={tooltipText}
          width={20}
          height={20}
          style={{ display: 'block' }}
        />
      </span>

      {open && createPortal(
        <div
          ref={refs.setFloating}
          role="tooltip"
          onMouseEnter={handleEnter}
          onMouseLeave={handleLeave}
          style={{
            position: strategy,
            top: y ?? 0,
            left: x ?? 0,
            zIndex: 9999,
          }}
        >
          <div
            className="tooltip-bubble"
            style={{
              background: 'var(--surface-overlay)',
              borderColor: 'var(--surface-border-strong)',
              color: 'var(--text-secondary)',
            }}
          >
            {tooltipText}
            <span
              ref={arrowRef}
              className="tooltip-arrow"
              style={{
                left: arrowX != null ? `${arrowX}px` : '',
                top: arrowY != null ? `${arrowY}px` : '',
                [arrowSide]: '-4px',
                borderColor: 'var(--surface-border-strong)',
                background: 'var(--surface-overlay)',
              }}
            />
          </div>
        </div>,
        document.body
      )}
    </span>
  );
}

export default QLFilterIndicator;
