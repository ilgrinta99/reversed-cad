import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In sviluppo il dev server inoltra /api al backend: niente CORS da gestire nel
// browser, e gli stream SSE passano senza buffering.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
})
