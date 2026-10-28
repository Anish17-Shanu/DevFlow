import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const backend = process.env.VITE_PROXY_TARGET || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/health": { target: backend, changeOrigin: true },
      "/metrics": { target: backend, changeOrigin: true },
      "/ws": { target: backend, ws: true }
    }
  },
  preview: {
    port: 4173,
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/health": { target: backend, changeOrigin: true },
      "/metrics": { target: backend, changeOrigin: true },
      "/ws": { target: backend, ws: true }
    }
  },
  build: {
    sourcemap: true
  }
});
