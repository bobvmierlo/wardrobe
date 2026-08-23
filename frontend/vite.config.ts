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
        // A missing photo must 404 rather than fall back to the app shell, and
        // an API call must never be answered with HTML.
        navigateFallbackDenylist: [/^\/api\//, /^\/uploads\//],
        runtimeCaching: [
          {
            // Reading the wardrobe works without a connection. Network-first,
            // so an answer from the server always wins and nothing is served
            // stale while there is a network; the cache is the fallback for
            // when there is none. Only the GETs that render a screen — the
            // ones that carry someone else's decisions are worth having.
            urlPattern: ({ url, request }) =>
              request.method === "GET" &&
              /^\/api\/(wardrobes|items|brands|categories|sizes|matches\/)/.test(url.pathname),
            handler: "NetworkFirst",
            options: {
              cacheName: "wardrobe-api",
              // Long enough to outlast a tunnel, short enough that a phone
              // that has been in a drawer for a month starts fresh.
              expiration: { maxEntries: 200, maxAgeSeconds: 60 * 60 * 24 * 14 },
              cacheableResponse: { statuses: [200] },
              // A dead connection fails fast; a captive portal that swallows
              // requests should not hang the screen for a minute.
              networkTimeoutSeconds: 6,
            },
          },
          {
            // Verdicts survive a lost connection: the request is queued and
            // replayed later, even if the app is closed in the meantime.
            // Only these two, and only because the API upserts on
            // (pair, person) — replaying one twice changes nothing.
            urlPattern: ({ url, request }) =>
              request.method === "POST" &&
              (url.pathname === "/api/matches" || url.pathname === "/api/matches/skip"),
            handler: "NetworkOnly",
            method: "POST",
            options: {
              backgroundSync: {
                name: "wardrobe-verdicts",
                options: { maxRetentionTime: 60 * 24 * 7 },
              },
            },
          },
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
