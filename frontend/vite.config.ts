import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  // Shell / Make wins so `DEVMIND_BACKEND_PORT=8010 npm run dev` and `make frontend` work.
  const backendPort =
    process.env.DEVMIND_BACKEND_PORT ||
    process.env.BACKEND_PORT ||
    env.DEVMIND_BACKEND_PORT ||
    env.BACKEND_PORT ||
    "8000";
  const backendTarget = `http://127.0.0.1:${backendPort}`;

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": backendTarget,
        "/webhooks": backendTarget,
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
  };
});
