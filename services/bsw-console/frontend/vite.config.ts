import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The API is the FastAPI app (uv run bsw-console, port 8002). In production
// it serves this build itself, so the proxy is for `npm run dev` only.
export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://127.0.0.1:8002' } },
  test: { environment: 'jsdom', globals: true },
})
