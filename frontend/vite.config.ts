import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  optimizeDeps: { exclude: ['pdfjs-dist'] },
  server: {
    proxy: {
      '/api': {
        target: process.env.RAYFLOW_API_PROXY_TARGET || loadEnv(mode, process.cwd(), '').RAYFLOW_API_PROXY_TARGET || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
}))
