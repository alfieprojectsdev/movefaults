import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      // workbox precaches all built assets for full offline capability
      workbox: {
        globPatterns: ["**/*.{js,css,html,ico,png,svg}"],
        // Cache the stations API response for offline station picker
        runtimeCaching: [
          {
            urlPattern: /\/api\/v1\/stations/,
            handler: "StaleWhileRevalidate",
            options: {
              cacheName: "stations-cache",
              expiration: { maxAgeSeconds: 60 * 60 * 24 }, // 24 h
            },
          },
        ],
      },
      manifest: {
        name: "MOVE Faults Field Ops",
        short_name: "Field Ops",
        description: "PHIVOLCS CORS station field operations",
        theme_color: "#1a56a4",
        background_color: "#ffffff",
        display: "standalone",
        orientation: "portrait",
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
        ],
      },
    }),
  ],
  server: {
    proxy: {
      // Proxy API calls to the FastAPI backend during development
      // 127.0.0.1, NOT localhost. Node 17+ stopped reordering DNS results, so
      // `localhost` resolves to ::1 (IPv6) first — while the API binds 0.0.0.0,
      // which is IPv4 only. The proxy then hangs on a refused IPv6 connection
      // and every request through it stalls until the client gives up, which
      // looks exactly like a broken app rather than a broken address.
      "/api": { target: "http://127.0.0.1:8001", changeOrigin: true },
    },
  },
});
