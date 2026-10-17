/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  // In dev/preview the app calls /api on its own origin and Vite forwards it to the backend.
  const proxy = {
    "/api": { target: env.VITE_PROXY_TARGET || "http://localhost:8000", changeOrigin: true },
  };
  return {
    plugins: [react()],
    server: { port: 5173, proxy },
    preview: { port: 4173, proxy },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.ts",
    },
  };
});
