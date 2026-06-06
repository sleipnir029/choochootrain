import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// base: '/' (absolute asset URLs) so client-side routes like /match/:id resolve
// /assets/* correctly under the SPA fallback. Dev proxy forwards /api to FastAPI.
// https://vite.dev/config/
export default defineConfig({
  base: '/',
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
