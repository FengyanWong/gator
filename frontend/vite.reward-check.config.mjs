import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  cacheDir: '../artifacts/local/reward-v2-real/20260926-qualification-05/ui/vite-cache',
  server: {
    host: '127.0.0.1', port: 5187, strictPort: true,
    proxy: { '/api': 'http://127.0.0.1:8837' },
  },
});
