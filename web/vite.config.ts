/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // One .env file for the whole repo, at the root.
  envDir: "..",
  test: {
    environment: "jsdom",
  },
});
