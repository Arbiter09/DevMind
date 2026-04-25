import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/webhooks": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  define: {
    // Inject the API base URL at build time.
    // In production Vercel serves the API from the same domain,
    // so the default empty string (same-origin) is correct.
    // Override with VITE_API_BASE_URL if you deploy API separately.
    __API_BASE__: JSON.stringify(process.env.VITE_API_BASE_URL ?? ""),
  },
});
