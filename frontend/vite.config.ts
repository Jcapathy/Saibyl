import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

// Dev-server proxy target. Overridable so a local session can point the /api
// proxy at the deployed backend (browser CORS forbids calling it directly
// from a localhost origin; the server-side proxy is origin-less).
const proxyTarget = process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000'
const wsTarget = proxyTarget.replace(/^http/, 'ws')

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
      '/ws': {
        target: wsTarget,
        ws: true,
        changeOrigin: true,
      },
    },
  },
})
