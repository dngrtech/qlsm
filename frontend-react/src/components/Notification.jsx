import React, { useState, useEffect } from 'react';
import { X, CheckCircle, AlertTriangle, Info } from 'lucide-react';

const VARIANTS = {
  success: {
    icon: CheckCircle,
    accentColor: '#00FF9D',
    bgGradient: 'from-emerald-500/10 to-transparent',
    borderColor: 'border-emerald-500/50',
    glowColor: 'shadow-emerald-500/20',
    textColor: 'text-emerald-400',
    iconBg: 'bg-emerald-500/20',
    progressColor: 'bg-emerald-500',
  },
  error: {
    icon: AlertTriangle,
    accentColor: '#FF3366',
    bgGradient: 'from-red-500/10 to-transparent',
    borderColor: 'border-red-500/50',
    glowColor: 'shadow-red-500/20',
    textColor: 'text-red-400',
    iconBg: 'bg-red-500/20',
    progressColor: 'bg-red-500',
  },
  info: {
    icon: Info,
    accentColor: '#00D4FF',
    bgGradient: 'from-cyan-500/10 to-transparent',
    borderColor: 'border-cyan-500/50',
    glowColor: 'shadow-cyan-500/20',
    textColor: 'text-cyan-400',
    iconBg: 'bg-cyan-500/20',
    progressColor: 'bg-cyan-500',
  },
};

function Notification({ message, variant = 'info', onClose, autoClose = true, autoCloseDelay = 6000 }) {
  const [isVisible, setIsVisible] = useState(false);
  const [isExiting, setIsExiting] = useState(false);

  const variantConfig = VARIANTS[variant] || VARIANTS.info;
  const IconComponent = variantConfig.icon;

  // Entrance animation on mount
  useEffect(() => {
    requestAnimationFrame(() => setIsVisible(true));
  }, []);

  useEffect(() => {
    let autoCloseTimer;
    let exitTimer;

    if (autoClose) {
      autoCloseTimer = setTimeout(() => {
        setIsExiting(true);
        exitTimer = setTimeout(() => {
          if (onClose) onClose();
        }, 300);
      }, autoCloseDelay);
    }

    return () => {
      clearTimeout(autoCloseTimer);
      clearTimeout(exitTimer);
    };
  }, [autoClose, autoCloseDelay, onClose]);

  const handleClose = () => {
    setIsExiting(true);
    setTimeout(() => {
      if (onClose) onClose();
    }, 300);
  };

  return (
    <div
      className={`
        relative overflow-hidden
        min-w-[320px] max-w-md
        bg-slate-900/95 backdrop-blur-md
        border ${variantConfig.borderColor}
        rounded-lg
        shadow-lg ${variantConfig.glowColor}
        transform transition-all duration-300 ease-out
        ${isVisible && !isExiting
          ? 'opacity-100 translate-y-0 scale-100'
          : 'opacity-0 -translate-y-2 scale-95'
        }
      `}
      role="alert"
      style={{
        boxShadow: `0 0 20px ${variantConfig.accentColor}15, 0 4px 12px rgba(0,0,0,0.3)`,
      }}
    >
      {/* Top accent line */}
      <div
        className="absolute top-0 left-0 right-0 h-[2px]"
        style={{
          background: `linear-gradient(90deg, transparent, ${variantConfig.accentColor}, transparent)`,
        }}
      />

      {/* Background gradient */}
      <div className={`absolute inset-0 bg-gradient-to-r ${variantConfig.bgGradient} pointer-events-none`} />

      {/* Content */}
      <div className="relative flex items-center gap-3 p-3 pr-10">
        {/* Icon container */}
        <div className={`flex-shrink-0 p-2 rounded-md ${variantConfig.iconBg}`}>
          <IconComponent
            className={`h-4 w-4 ${variantConfig.textColor}`}
            strokeWidth={2.5}
          />
        </div>

        {/* Message */}
        <p className="text-sm font-medium text-slate-200 leading-tight">
          {message}
        </p>

        {/* Close button */}
        <button
          onClick={handleClose}
          className="absolute top-1/2 right-2 -translate-y-1/2 p-1.5 rounded-md text-slate-500 hover:text-slate-300 hover:bg-slate-800/50 transition-colors focus:outline-none focus:ring-1 focus:ring-slate-600"
          aria-label="Dismiss notification"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Auto-close progress bar */}
      {autoClose && (
        <div className="absolute bottom-0 left-0 right-0 h-[2px] bg-slate-800">
          <div
            className={`h-full ${variantConfig.progressColor} origin-left`}
            style={{
              animation: `shrink ${autoCloseDelay}ms linear forwards`,
            }}
          />
        </div>
      )}

      {/* Inline keyframes for progress bar */}
      <style>{`
        @keyframes shrink {
          from { transform: scaleX(1); }
          to { transform: scaleX(0); }
        }
      `}</style>
    </div>
  );
}

export default Notification;
