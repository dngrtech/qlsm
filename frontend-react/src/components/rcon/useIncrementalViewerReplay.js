import { useEffect, useRef } from 'react';

function preservesEventPrefix(previous, next) {
  if (previous.length > next.length) return false;
  return previous.every((event, index) => event === next[index]);
}

function resetCursor(renderedRef) {
  renderedRef.current = { events: [], resetKey: Symbol('initial') };
}

export default function useIncrementalViewerReplay(viewerRef, events, resetKey) {
  const renderedRef = useRef({ events: [], resetKey: Symbol('initial') });

  useEffect(() => () => resetCursor(renderedRef), []);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer) return;

    const previous = renderedRef.current;
    const canAppend = previous.resetKey === resetKey
      && preservesEventPrefix(previous.events, events);
    const start = canAppend ? previous.events.length : 0;

    if (!canAppend) viewer.clear();
    for (let index = start; index < events.length; index += 1) {
      viewer.append(events[index]);
    }
    renderedRef.current = { events, resetKey };
  }, [events, resetKey, viewerRef]);
}
