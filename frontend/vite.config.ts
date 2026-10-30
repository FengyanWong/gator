import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The UI is served same-origin by the FastAPI backend in production (frontend/dist).
// In development the API is proxied to the local backend; nothing listens beyond localhost.
export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5173, proxy: { '/api': 'http://127.0.0.1:8765' } },
  // `vite preview --outDir <a folder outside the repository> --port 5174` serves a build WITHOUT touching the dist the
  // user's backend serves: how the browser checks try a change before it goes live (review of 2026-09-23).
  preview: { host: '127.0.0.1', port: 5174, proxy: { '/api': 'http://127.0.0.1:8765' } },
  build: { outDir: 'dist', sourcemap: false },
});
