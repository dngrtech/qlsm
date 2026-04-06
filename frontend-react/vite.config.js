import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: '/',
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
  },
  server: {
    proxy: {
      // Proxy /api requests to the Flask backend
      '/api': {
        target: process.env.VITE_API_URL || 'http://127.0.0.1:5001', // Your Flask backend URL (Updated Port)
        changeOrigin: true, // Recommended for virtual hosted sites
        // secure: false, // Uncomment if your backend uses HTTPS with a self-signed certificate
        // rewrite: (path) => path.replace(/^\/api/, ''), // Uncomment if Flask doesn't expect /api prefix
      },
      // Proxy socket.io connections to Flask-SocketIO backend
      '/socket.io': {
        target: process.env.VITE_API_URL || 'http://127.0.0.1:5001',
        changeOrigin: true,
        ws: true,  // Enable WebSocket proxying
      },
    },
  },
})
