import React from 'react';
import { RadioGroup } from '@headlessui/react';
import { FILTER_MODES, LINE_OPTIONS, TIME_OPTIONS } from './logFilterOptions';

/**
 * Shared filter control bar for the instance-log and chat-log modals.
 * Renders the Filter By toggle plus the mode-specific line/time selectors and
 * an Apply button. Filters are applied on demand (via Apply), never reactively.
 */
function LogFilterControls({
    filterMode,
    setFilterMode,
    lineCount,
    setLineCount,
    timeRange,
    setTimeRange,
    onApply,
    isLoading,
    allowedModes = ['lines', 'time', 'all'],
}) {
    const visibleFilterModes = FILTER_MODES.filter((mode) => allowedModes.includes(mode.value));

    return (
        <div className="px-6 py-3 border-b border-theme bg-theme-elevated flex-shrink-0">
            <div className="flex flex-wrap items-center gap-4">
                {/* Filter Mode Toggle */}
                <div className="flex items-center gap-2">
                    <span className="label-tech">Filter by:</span>
                    <RadioGroup value={filterMode} onChange={setFilterMode} className="flex gap-1">
                        {visibleFilterModes.map((mode) => (
                            <RadioGroup.Option
                                key={mode.value}
                                value={mode.value}
                                className={({ checked }) =>
                                    `logs-modal-filter-option ${checked ? 'logs-modal-filter-option-active' : ''}`
                                }
                            >
                                <mode.icon className="h-3.5 w-3.5" strokeWidth={2} />
                                {mode.label}
                            </RadioGroup.Option>
                        ))}
                    </RadioGroup>
                </div>

                {/* Line Count Options */}
                {filterMode === 'lines' && (
                    <div className="flex items-center gap-2">
                        <span className="label-tech">Lines:</span>
                        <div className="flex gap-1">
                            {LINE_OPTIONS.map((count) => (
                                <button
                                    key={count}
                                    onClick={() => setLineCount(count)}
                                    className={`logs-modal-value-btn ${lineCount === count ? 'logs-modal-value-btn-active' : ''}`}
                                >
                                    {count}
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {/* Time Range Options */}
                {filterMode === 'time' && (
                    <div className="flex items-center gap-2">
                        <span className="label-tech">Time:</span>
                        <div className="flex gap-1">
                            {TIME_OPTIONS.map((option) => (
                                <button
                                    key={option.value}
                                    onClick={() => setTimeRange(option.value)}
                                    className={`logs-modal-value-btn ${timeRange === option.value ? 'logs-modal-value-btn-active' : ''}`}
                                >
                                    {option.label}
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {filterMode === 'all' && (
                    <span className="font-mono text-xs" style={{ color: 'var(--accent-warning, #f59e0b)' }}>
                        ⚠ May fetch a very large log — slow on long-running servers
                    </span>
                )}

                {/* Apply Button */}
                <button
                    onClick={onApply}
                    disabled={isLoading}
                    className="logs-modal-apply-btn"
                >
                    Apply
                </button>
            </div>
        </div>
    );
}

export default LogFilterControls;
