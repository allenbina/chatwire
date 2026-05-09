import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  base: '/app/',
  plugins: [react(), tailwindcss()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  server: {
    // In dev mode, proxy API and SSE calls to the running FastAPI server.
    proxy: {
      '/api': 'http://localhost:8723',
      '/events': 'http://localhost:8723',
      '/healthz': 'http://localhost:8723',
      '/login': 'http://localhost:8723',
      '/logout': 'http://localhost:8723',
    },
  },
})
