import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Local dev proxies to http://localhost:8000 by default; in docker-compose set
// VITE_PROXY_TARGET=http://backend:8000 to reach the backend service.
const proxyTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: true,
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
})
