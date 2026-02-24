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
        name: "POGF Field Ops",
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
      "/api": { target: "http://localhost:8001", changeOrigin: true },
    },
  },
});
