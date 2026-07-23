import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Proxying /api, /auth, and /callback to the backend is what eliminates
// CORS/Trusted-Origin complexity entirely: the browser only ever sees one
// origin (http://localhost:5173) for static assets, API calls, and the OAuth
// redirect landing page.
//
// Target is 127.0.0.1, not localhost: Node resolves "localhost" to ::1 first
// on some machines, and anything else already publishing :8000 on IPv6
// (e.g. a Docker container) will silently swallow the proxied requests
// instead of the backend, which only binds IPv4 127.0.0.1.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/auth": "http://127.0.0.1:8000",
      "/callback": "http://127.0.0.1:8000",
    },
  },
});
