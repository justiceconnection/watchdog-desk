import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Static site: the desk reads cards (placeholder data now; marts/<agency>/cards/*.parquet later) in the browser.
export default defineConfig({
  base: './', // path-independent: works at a pages subpath, a custom domain, or inside an iframe
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5190, strictPort: true },
});
