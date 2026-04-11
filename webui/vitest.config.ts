import path from "node:path";

import vue from "@vitejs/plugin-vue";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src")
    }
  },
  test: {
    environment: "jsdom",
    globals: true,
    css: true,
    setupFiles: "./tests/setup.ts",
    exclude: ["tests/e2e/**", "node_modules/**"],
    coverage: {
      enabled: true,
      provider: "v8",
      all: true,
      reportsDirectory: "./coverage",
      reporter: ["text", "lcov", "json-summary"],
      include: ["src/**/*.{ts,vue}"],
      exclude: ["src/main.ts"]
    }
  }
});
