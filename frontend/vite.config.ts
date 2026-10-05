import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Фронт ходит в API по /api/v1; dev-прокси на backend.
// VITE_PROXY_TARGET позволяет работать и на хосте (localhost:8000),
// и внутри docker-сети (http://api:8000).
const proxyTarget = process.env.VITE_PROXY_TARGET || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
});