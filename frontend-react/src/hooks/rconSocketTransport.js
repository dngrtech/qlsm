import { io } from 'socket.io-client';

const SOCKET_URL = import.meta.env.VITE_API_BASE_URL || '';
const DISCONNECT_DELAY_MS = 1000;

// NOTE: these are module-level on purpose — one shared socket per tab. They are
// not HMR-safe: a hot reload re-executes this module and resets them while the
// previous socket stays connected, so you can see two live connections after
// saving a file in dev. Reload the page (or restart run-dev.sh) to clear it.
let socket = null;
let users = 0;
let disconnectTimer = null;

function disconnectSharedSocket() {
  if (!socket || users > 0) return;
  socket.disconnect();
  socket = null;
  disconnectTimer = null;
}

export function acquireRconSocket() {
  if (disconnectTimer) {
    clearTimeout(disconnectTimer);
    disconnectTimer = null;
  }

  if (!socket) {
    socket = io(SOCKET_URL, {
      withCredentials: true,
      transports: import.meta.env.DEV ? ['polling'] : ['websocket', 'polling'],
      upgrade: !import.meta.env.DEV,
      reconnection: true,
      reconnectionAttempts: 3,
      reconnectionDelay: 1000,
    });
  }

  users += 1;
  return socket;
}

export function releaseRconSocket({ immediate = false } = {}) {
  if (users === 0) return;
  users -= 1;
  if (users > 0 || !socket) return;

  if (immediate) {
    if (disconnectTimer) clearTimeout(disconnectTimer);
    disconnectTimer = null;
    disconnectSharedSocket();
    return;
  }

  disconnectTimer = setTimeout(disconnectSharedSocket, DISCONNECT_DELAY_MS);
}

export function resetRconSocketForTests() {
  if (disconnectTimer) clearTimeout(disconnectTimer);
  disconnectTimer = null;
  users = 0;
  if (socket) {
    socket.removeAllListeners?.();
    socket.disconnect();
    socket = null;
  }
}
