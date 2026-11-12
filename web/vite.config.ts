/// <reference types="vitest/config" />
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // The installable app (DESIGN §18.11): our own service worker, given the list of built files to keep.
    VitePWA({
      strategies: "injectManifest",
      srcDir: "src",
      filename: "sw.ts",
      registerType: "autoUpdate",
      // Fonts are cached for offline use as woff2; Phosphor also ships 3 MB SVG fonts no current browser loads.
      injectManifest: { globPatterns: ["**/*.{js,css,html,png,svg,woff2}"], globIgnores: ["**/Phosphor*.svg"] },
      manifest: {
        name: "Friday",
        short_name: "Friday",
        description: "Decides when things get done",
        display: "standalone",
        start_url: "/",
        background_color: "#0c141c",
        theme_color: "#0c141c",
        icons: [
          { src: "icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "icon-512.png", sizes: "512x512", type: "image/png", purpose: "any maskable" },
        ],
      },
    }),
  ],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  // Two kinds of test: the quick ones, in Node, and the screens (*.screen.test.tsx), the whole app on a page in
  // happy-dom over a real Friday serving a lived-in sample (src/test/), each file its own copy.
  test: {
    projects: [
      { extends: true, test: { name: "unit", include: ["src/**/*.test.{ts,tsx}"], exclude: ["src/**/*.screen.test.tsx", "node_modules/**"] } },
      {
        extends: true,
        test: {
          name: "screens",
          include: ["src/**/*.screen.test.tsx"],
          environment: "happy-dom",
          globalSetup: ["src/test/globalSetup.ts"],
          setupFiles: ["src/test/setup.ts"],
          testTimeout: 30_000,
          hookTimeout: 120_000,
          maxWorkers: 4,
        },
      },
    ],
  },
  // In development the API is fridayd's; FRIDAY_SERVER points elsewhere, as for the CLI.
  server: {
    proxy: Object.fromEntries(
      ["/api", "/events", "/openapi.json"].map((p) => [p, process.env.FRIDAY_SERVER ?? "http://localhost:8765"]),
    ),
  },
});
