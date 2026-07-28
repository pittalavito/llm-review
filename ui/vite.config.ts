import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Served by FastAPI at the root in "deployed" mode; in dev the API/docs
// requests are proxied to the backend on 8081 (APP_PORT).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/chat': 'http://localhost:8081',
      '/agent': 'http://localhost:8081',
      '/docs': 'http://localhost:8081',
      '/openapi.json': 'http://localhost:8081',
    },
  },
})
