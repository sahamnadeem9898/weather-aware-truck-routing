import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development the Django API runs on :8000; in production Django serves
// the built files itself, so the app always calls same-origin /api.
export default defineConfig({
  plugins: [react()],
  worker: { format: 'es' },
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
