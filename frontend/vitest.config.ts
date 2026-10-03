import { defineConfig } from "vitest/config";

// The React plugin is not needed here: Vitest transpiles TSX through esbuild
// using the app's `jsx: react-jsx` setting, and Fast Refresh is a dev-server
// concern. Leaving it out also keeps Vite's types from clashing with the copy
// Vitest bundles.
export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/shared/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
