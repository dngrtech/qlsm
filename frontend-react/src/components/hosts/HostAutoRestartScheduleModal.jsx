import React, { useState, Fragment, useEffect } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { PowerIcon, X } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { WheelPicker, WheelPickerWrapper } from '@ncdai/react-wheel-picker';
import '../../ncdai-wheel-picker.css';

const DAYS_OF_WEEK = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const HOUR_OPTIONS = Array.from({ length: 12 }, (_, i) => {
    const v = (i + 1).toString().padStart(2, '0');
    return { value: v, label: v };
});

const MINUTE_OPTIONS = Array.from({ length: 60 }, (_, i) => {
    const v = i.toString().padStart(2, '0');
    return { value: v, label: v };
});

const PERIOD_OPTIONS = [
    { value: 'AM', label: 'AM' },
    { value: 'PM', label: 'PM' },
];

const PICKER_CLASSES = {
    optionItem: 'rwp-option',
    highlightWrapper: 'rwp-highlight',
    highlightItem: 'rwp-highlight-item',
};

/* Convert 24h string → 12h + period */
function to12h(h24) {
    const n = parseInt(h24, 10);
    return {
        hour: (n % 12 || 12).toString().padStart(2, '0'),
        period: n >= 12 ? 'PM' : 'AM',
    };
}

/* Convert 12h + period → 24h string */
function to24h(h12, period) {
    let n = parseInt(h12, 10);
    if (period === 'AM') n = n === 12 ? 0 : n;
    else n = n === 12 ? 12 : n + 12;
    return n.toString().padStart(2, '0');
}

/* ── Main modal ── */
function HostAutoRestartScheduleModal({ isOpen, onClose, onSubmit, host }) {
    const [scheduleMode, setScheduleMode] = useState('daily');
    const [selectedDays, setSelectedDays] = useState([]);
    const [selectedDates, setSelectedDates] = useState([]);
    const [hour, setHour] = useState('04');
    const [minute, setMinute] = useState('00');
    const [period, setPeriod] = useState('AM');

    useEffect(() => {
        if (isOpen && host) {
            const schedule = host.auto_restart_schedule;
            if (schedule) {
                const parts = schedule.split(' ');
                let dayOfWeekPart = '*';
                let datePart = '*-*-*';
                let timePart = '00:00:00';

                if (parts.length === 3) {
                    dayOfWeekPart = parts[0];
                    datePart = parts[1];
                    timePart = parts[2];
                } else if (parts.length === 2) {
                    datePart = parts[0];
                    timePart = parts[1];
                }

                const [hr, min] = timePart.split(':');
                const { hour: h12, period: p } = to12h(hr);
                setHour(h12);
                setMinute(min.padStart(2, '0'));
                setPeriod(p);

                if (dayOfWeekPart !== '*' && dayOfWeekPart !== '') {
                    setScheduleMode('weekly');
                    setSelectedDays(dayOfWeekPart.split(','));
                } else if (datePart !== '*-*-*') {
                    setScheduleMode('monthly');
                    const dates = datePart.split('-')[2];
                    if (dates && dates !== '*') setSelectedDates(dates.split(','));
                } else {
                    setScheduleMode('daily');
                    setSelectedDays([]);
                    setSelectedDates([]);
                }
            } else {
                setScheduleMode('none');
                setSelectedDays([]);
                setSelectedDates([]);
                setHour('04');
                setMinute('00');
                setPeriod('AM');
            }
        }
    }, [isOpen, host]);

    if (!host) return null;

    const handleClose = () => onClose();

    const toggleDay = (day) =>
        setSelectedDays((p) => (p.includes(day) ? p.filter((d) => d !== day) : [...p, day]));

    const toggleDate = (date) => {
        const dStr = date.toString().padStart(2, '0');
        setSelectedDates((p) => (p.includes(dStr) ? p.filter((d) => d !== dStr) : [...p, dStr]));
    };

    const handleSubmit = (e) => {
        e.preventDefault();
        let onCalendarStr = null;
        if (scheduleMode !== 'none') {
            const h24 = to24h(hour, period);
            const timeStr = `${h24}:${minute}:00`;
            if (scheduleMode === 'daily') {
                onCalendarStr = `*-*-* ${timeStr}`;
            } else if (scheduleMode === 'weekly') {
                if (selectedDays.length === 0) return;
                onCalendarStr = `${selectedDays.join(',')} *-*-* ${timeStr}`;
            } else if (scheduleMode === 'monthly') {
                if (selectedDates.length === 0) return;
                onCalendarStr = `*-*-${selectedDates.join(',')} ${timeStr}`;
            }
        }
        onSubmit(host.id, onCalendarStr);
        handleClose();
    };

    const allDates = Array.from({ length: 31 }, (_, i) => i + 1);

    const contentVariants = {
        initial: { opacity: 0, y: 6 },
        animate: { opacity: 1, y: 0, transition: { duration: 0.2, ease: 'easeOut' } },
        exit: { opacity: 0, y: -6, transition: { duration: 0.15 } },
    };

    return (
        <Transition appear show={isOpen} as={Fragment}>
            <Dialog as="div" className="relative z-50" onClose={handleClose}>
                <Transition.Child
                    as={Fragment}
                    enter="ease-out duration-300"
                    enterFrom="opacity-0"
                    enterTo="opacity-100"
                    leave="ease-in duration-200"
                    leaveFrom="opacity-100"
                    leaveTo="opacity-0"
                >
                    <div className="modal-backdrop fixed inset-0" aria-hidden="true" />
                </Transition.Child>

                <div className="fixed inset-0 overflow-y-auto scrollbar-thick">
                    <div className="flex min-h-full items-center justify-center p-4">
                        <Transition.Child
                            as={Fragment}
                            enter="ease-out duration-300"
                            enterFrom="opacity-0 translate-y-4 scale-95"
                            enterTo="opacity-100 translate-y-0 scale-100"
                            leave="ease-in duration-200"
                            leaveFrom="opacity-100 scale-100"
                            leaveTo="opacity-0 scale-95"
                        >
                            <Dialog.Panel className="modal-panel w-full max-w-[480px] transform p-6 text-left align-middle transition-all">
                                <div className="accent-line-top" />

                                {/* Header */}
                                <Dialog.Title as="h3" className="relative z-10 flex items-center gap-3 mb-6">
                                    <span className="status-pulse status-pulse-active" />
                                    <PowerIcon size={18} className="text-[var(--accent-primary)]" />
                                    <span className="font-display text-base font-semibold tracking-wider uppercase text-[var(--text-primary)]">
                                        Configure Auto-Restart
                                    </span>
                                    <button type="button" onClick={handleClose} className="ml-auto logs-modal-close-btn">
                                        <X size={18} />
                                    </button>
                                </Dialog.Title>

                                <form onSubmit={handleSubmit}>
                                    <div className="space-y-6">
                                        <p className="text-sm text-[var(--text-muted)]">
                                            Schedule automated reboots for <strong>{host.name}</strong>. Reboots will
                                            automatically update workshop items on all QL instances.
                                        </p>

                                        {/* Schedule type selector */}
                                        <div>
                                            <label className="label-tech mb-3 block">Schedule Type</label>
                                            <div className="flex border-b border-[var(--surface-border)] mb-5">
                                                {['none', 'daily', 'weekly', 'monthly'].map((mode) => (
                                                    <label
                                                        key={mode}
                                                        className={`flex-1 text-center py-2.5 px-4 cursor-pointer transition-all border-b-2 -mb-[1px] ${scheduleMode === mode
                                                            ? 'border-[var(--accent-primary)] text-[var(--accent-primary)] font-semibold bg-[var(--surface-raised)]'
                                                            : 'border-transparent text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:border-[var(--surface-border-strong)]'
                                                            }`}
                                                    >
                                                        <input
                                                            type="radio"
                                                            name="scheduleMode"
                                                            value={mode}
                                                            checked={scheduleMode === mode}
                                                            onChange={(e) => setScheduleMode(e.target.value)}
                                                            className="sr-only"
                                                        />
                                                        <span className="text-sm capitalize tracking-wide">
                                                            {mode === 'none' ? 'Disabled' : mode}
                                                        </span>
                                                    </label>
                                                ))}
                                            </div>
                                        </div>

                                        {/* ── Dynamic-height options area ── */}
                                        <div className="overflow-hidden">
                                            <AnimatePresence mode="popLayout" initial={false}>
                                                {scheduleMode !== 'none' && (
                                                    <motion.div
                                                        key={`mode-${scheduleMode}`}
                                                        variants={contentVariants}
                                                        initial="initial"
                                                        animate="animate"
                                                        exit="exit"
                                                        className="space-y-5 border-t border-[var(--surface-border)] pt-5"
                                                    >
                                                        {/* Weekly */}
                                                        {scheduleMode === 'weekly' && (
                                                            <div>
                                                                <label className="label-tech mb-2 block">Days of Week</label>
                                                                <div className="grid grid-cols-4 gap-3">
                                                                    {DAYS_OF_WEEK.map((day) => (
                                                                        <label key={day} className="flex items-center gap-2 cursor-pointer group">
                                                                            <input
                                                                                type="checkbox"
                                                                                checked={selectedDays.includes(day)}
                                                                                onChange={() => toggleDay(day)}
                                                                                className="w-4 h-4 accent-[var(--accent-primary)] cursor-pointer"
                                                                            />
                                                                            <span className="text-sm font-medium text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] transition-colors">
                                                                                {day}
                                                                            </span>
                                                                        </label>
                                                                    ))}
                                                                </div>
                                                                <p className={`text-xs text-[var(--accent-danger)] mt-2 ${selectedDays.length === 0 ? '' : 'invisible'}`}>
                                                                    Required: Select at least one day.
                                                                </p>
                                                            </div>
                                                        )}

                                                        {scheduleMode === 'monthly' && (
                                                            <div>
                                                                <label className="label-tech mb-2 block">Days of Month</label>
                                                                <div className="grid grid-cols-7 gap-y-3 gap-x-1 max-h-[150px] overflow-y-auto scrollbar-thin pr-1 pb-1">
                                                                    {allDates.map((date) => {
                                                                        const dStr = date.toString().padStart(2, '0');
                                                                        const sel = selectedDates.includes(dStr);
                                                                        return (
                                                                            <label key={date} className="flex flex-row items-center gap-2 cursor-pointer group">
                                                                                <input
                                                                                    type="checkbox"
                                                                                    checked={sel}
                                                                                    onChange={() => toggleDate(date)}
                                                                                    className="w-4 h-4 accent-[var(--accent-primary)] cursor-pointer"
                                                                                />
                                                                                <span className="text-xs font-medium text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] transition-colors">
                                                                                    {date}
                                                                                </span>
                                                                            </label>
                                                                        );
                                                                    })}
                                                                </div>
                                                                <p className={`text-xs text-[var(--accent-danger)] mt-2 ${selectedDates.length === 0 ? '' : 'invisible'}`}>
                                                                    Required: Select at least one date.
                                                                </p>
                                                            </div>
                                                        )}

                                                        {/* ── Time Picker ── */}
                                                        <div>
                                                            <label className="label-tech mb-3 block text-center">Local Server Time</label>
                                                            <div className="flex justify-center">
                                                                <WheelPickerWrapper className="w-56">
                                                                    <WheelPicker
                                                                        options={HOUR_OPTIONS}
                                                                        value={hour}
                                                                        onValueChange={setHour}
                                                                        classNames={PICKER_CLASSES}
                                                                        infinite
                                                                    />
                                                                    <WheelPicker
                                                                        options={MINUTE_OPTIONS}
                                                                        value={minute}
                                                                        onValueChange={setMinute}
                                                                        classNames={PICKER_CLASSES}
                                                                        infinite
                                                                    />
                                                                    <WheelPicker
                                                                        options={PERIOD_OPTIONS}
                                                                        value={period}
                                                                        onValueChange={setPeriod}
                                                                        classNames={PICKER_CLASSES}
                                                                    />
                                                                </WheelPickerWrapper>
                                                            </div>
                                                            <p className="text-xs text-[var(--text-muted)] mt-2 text-center">
                                                                Scroll or drag to change. Uses the host's local timezone.
                                                            </p>
                                                        </div>
                                                    </motion.div>
                                                )}

                                                {scheduleMode === 'none' && (
                                                    <motion.div
                                                        key="none"
                                                        variants={contentVariants}
                                                        initial="initial"
                                                        animate="animate"
                                                        exit="exit"
                                                        className="flex items-center justify-center p-6 border-t border-[var(--surface-border)] mt-4"
                                                    >
                                                        <p className="text-sm text-[var(--text-muted)] text-center">
                                                            Auto-restart is disabled. Select a schedule type above to configure.
                                                        </p>
                                                    </motion.div>
                                                )}
                                            </AnimatePresence>
                                        </div>
                                    </div>

                                    {/* Footer */}
                                    <div className="flex justify-end items-center gap-3 mt-8 pt-4 border-t border-[var(--surface-border)]">
                                        <button type="button" onClick={handleClose} className="btn btn-secondary">
                                            Cancel
                                        </button>
                                        <button
                                            type="submit"
                                            disabled={
                                                (scheduleMode === 'weekly' && selectedDays.length === 0) ||
                                                (scheduleMode === 'monthly' && selectedDates.length === 0)
                                            }
                                            className="btn btn-primary"
                                        >
                                            Save Schedule
                                        </button>
                                    </div>
                                </form>
                            </Dialog.Panel>
                        </Transition.Child>
                    </div>
                </div>
            </Dialog>
        </Transition>
    );
}

export default HostAutoRestartScheduleModal;
