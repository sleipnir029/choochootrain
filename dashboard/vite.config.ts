import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base: './' so the built bundle works when FastAPI serves it from / (P6.T10).
// Dev proxy forwards /api to the FastAPI server so `npm run dev` hits real data.
// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
