import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Proxying /api, /auth, and /callback to the backend is what eliminates
// CORS/Trusted-Origin complexity entirely: the browser only ever sees one
// origin (http://localhost:5173) for static assets, API calls, and the OAuth
// redirect landing page.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/auth": "http://localhost:8000",
      "/callback": "http://localhost:8000",
    },
  },
});
