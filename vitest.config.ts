import { defineConfig } from "vitest/config";

// Tests are pure logic (no DOM yet), so the node environment is right.
// Kept separate from vite.config.ts so the Tauri-tuned dev server settings
// stay untouched. Add jsdom here later if component tests need a DOM.
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
