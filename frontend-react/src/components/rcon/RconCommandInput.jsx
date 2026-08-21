import { useCallback, useEffect, useRef, useState } from 'react';
import { Send } from 'lucide-react';

function RconCommandInput({
  disabled = false,
  recipientCount,
  prompt = 'RCON>',
  onSend,
  buttonLabel = 'Send',
  className = 'border-t border-theme bg-theme-elevated',
}) {
  const [value, setValue] = useState('');
  const [history, setHistory] = useState([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const inputRef = useRef(null);
  // mousedown/keydown only fire for real interaction — the programmatic
  // focus() calls both Headless UI's Dialog FocusTrap and its Menu's
  // close-then-restore-focus make while the modal caller is opening never
  // dispatch either, so this can't mistake that internal shuffling for the
  // user moving on.
  const userInteractedRef = useRef(false);

  useEffect(() => {
    const markInteracted = () => { userInteractedRef.current = true; };
    document.addEventListener('mousedown', markInteracted, true);
    document.addEventListener('keydown', markInteracted, true);
    return () => {
      document.removeEventListener('mousedown', markInteracted, true);
      document.removeEventListener('keydown', markInteracted, true);
    };
  }, []);

  useEffect(() => {
    // Both callers pass `disabled` until the field is actually usable (RCON
    // socket connected / a ready target selected) — a disabled input can't
    // take focus, so wait for that instead of only trying once on mount.
    if (disabled) return undefined;
    const focusIfUntouched = () => {
      // The retry covers the modal's open animation; the fleet page mounts
      // this permanently, so this also avoids yanking focus back once the
      // user has moved on. Checking document.activeElement here isn't
      // enough — inside the RCON console modal, closing the Actions menu
      // that launched it leaves focus on that menu's own trigger button
      // (Headless UI restores focus there on close), so activeElement is
      // never idle by the time the socket connects even though the user
      // never touched anything after the modal opened.
      if (!userInteractedRef.current) inputRef.current?.focus();
    };
    focusIfUntouched();
    const timer = setTimeout(focusIfUntouched, 350);
    return () => clearTimeout(timer);
  }, [disabled]);

  const submit = useCallback((event) => {
    event.preventDefault();
    const command = value.trim();
    if (disabled || !command) return;
    if (onSend(command) === false) return;
    setHistory((previous) => [command, ...previous].slice(0, 50));
    setHistoryIndex(-1);
    setValue('');
    requestAnimationFrame(() => inputRef.current?.focus());
  }, [disabled, onSend, value]);

  const navigateHistory = useCallback((event) => {
    if (event.key === 'ArrowUp' && historyIndex < history.length - 1) {
      event.preventDefault();
      const next = historyIndex + 1;
      setHistoryIndex(next);
      setValue(history[next]);
    } else if (event.key === 'ArrowDown' && historyIndex >= 0) {
      event.preventDefault();
      const next = historyIndex - 1;
      setHistoryIndex(next);
      setValue(next < 0 ? '' : history[next]);
    }
  }, [history, historyIndex]);

  return (
    <form onSubmit={submit} className={`flex flex-wrap items-center gap-3 px-4 py-4 sm:px-6 flex-shrink-0 ${className}`}>
      <span className="font-mono text-sm font-semibold" style={{ color: 'var(--accent-primary)' }}>{prompt}</span>
      {recipientCount != null && <span className="text-xs text-theme-muted">{recipientCount} recipients</span>}
      <input
        ref={inputRef}
        type="text"
        value={value}
        disabled={disabled}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={navigateHistory}
        placeholder={disabled ? 'Connecting...' : 'Enter command...'}
        className="min-w-0 flex-1 basis-40 bg-transparent border-none outline-none font-mono text-sm text-theme-primary placeholder-theme-muted"
        autoComplete="off"
        spellCheck="false"
      />
      <button type="submit" disabled={disabled || !value.trim()} className="btn btn-primary shrink-0 gap-2">
        <Send size={14} />
        {buttonLabel}
      </button>
    </form>
  );
}

export default RconCommandInput;
