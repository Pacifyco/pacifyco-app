/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // One .env file for the whole repo, at the root.
  envDir: "..",
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
