import { useCallback, useEffect, useRef, useState } from 'react';
import { Send } from 'lucide-react';

function RconCommandInput({
  disabled = false,
  recipientCount,
  prompt = 'RCON>',
  onSend,
  buttonLabel = 'Send',
}) {
  const [value, setValue] = useState('');
  const [history, setHistory] = useState([]);
  const [historyIndex, setHistoryIndex] = useState(-1);
  const inputRef = useRef(null);

  useEffect(() => {
    inputRef.current?.focus();
    const timer = setTimeout(() => inputRef.current?.focus(), 350);
    return () => clearTimeout(timer);
  }, []);

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
    <form onSubmit={submit} className="flex items-center gap-3 px-6 py-4 border-t border-theme bg-theme-elevated flex-shrink-0">
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
        className="flex-1 bg-transparent border-none outline-none font-mono text-sm text-theme-primary placeholder-theme-muted"
        autoComplete="off"
        spellCheck="false"
      />
      <button type="submit" disabled={disabled || !value.trim()} className="btn btn-primary gap-2">
        <Send size={14} />
        {buttonLabel}
      </button>
    </form>
  );
}

export default RconCommandInput;
