import path from "node:path";

import legacy from "@vitejs/plugin-legacy";
import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [
    vue(),
    legacy({
      targets: [
        "chrome >= 64",
        "firefox >= 67",
        "safari >= 11",
        "edge >= 18"
      ],
      modernPolyfills: true,
      renderLegacyChunks: true
    })
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src")
    }
  },
  build: {
    target: "es2015",
    outDir: "dist",
    cssTarget: "chrome61",
    sourcemap: true
  },
  server: {
    host: "127.0.0.1",
    port: 5173
  },
  preview: {
    host: "127.0.0.1",
    port: 4173
  }
});
