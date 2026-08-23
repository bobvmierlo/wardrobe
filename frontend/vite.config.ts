import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// During development the frontend runs on :5173 and proxies API + photo
// requests to the FastAPI backend on :8000. In production everything is served
// from the same origin by FastAPI, so these proxies are dev-only.
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      // The app promises `display: standalone`, so it has to survive being
      // opened without a connection — without a service worker that is a blank
      // page. The manifest stays hand-written in public/.
      registerType: "autoUpdate",
      manifest: false,
      includeAssets: ["icon.svg", "apple-touch-icon.png", "icon-192.png", "icon-512.png"],
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,webmanifest}"],
        // The API is the source of truth and must never be served stale, and a
        // missing photo must 404 rather than fall back to the app shell.
        navigateFallbackDenylist: [/^\/api\//, /^\/uploads\//],
        runtimeCaching: [
          {
            // Photos are immutable: the filename carries a UUID, so an edited
            // photo is a different URL. Cache-first is what makes a revisit
            // feel instant, and what makes the grids work offline at all.
            urlPattern: ({ url }) => url.pathname.startsWith("/uploads/"),
            handler: "CacheFirst",
            options: {
              cacheName: "wardrobe-photos",
              expiration: { maxEntries: 600, maxAgeSeconds: 60 * 60 * 24 * 60 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
      devOptions: { enabled: false },
    }),
  ],
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
