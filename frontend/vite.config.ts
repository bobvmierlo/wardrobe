import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development the frontend runs on :5173 and proxies API + photo
// requests to the FastAPI backend on :8000. In production everything is served
// from the same origin by FastAPI, so these proxies are dev-only.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/uploads": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
  },
});
