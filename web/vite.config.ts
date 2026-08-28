import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    // The panel calls the API on the same origin in development, so the browser
    // never deals with CORS and the token never crosses an origin boundary.
    proxy: { "/api": "http://localhost:8000" },
  },
});
