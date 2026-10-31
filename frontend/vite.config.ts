import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const here = dirname(fileURLToPath(import.meta.url));

// Django serves the build from static/dist/ and reads .vite/manifest.json
// through the {% vite_entry %} tag (common/templatetags/vite.py).
export default defineConfig({
  base: "/static/dist/",
  server: { port: 5173, strictPort: true, cors: true, origin: "http://localhost:5173" },
  esbuild: { jsx: "automatic", jsxImportSource: "preact" },
  build: {
    outDir: resolve(here, "../static/dist"),
    emptyOutDir: true,
    manifest: true,
    rollupOptions: {
      input: {
        game: resolve(here, "src/entries/game.ts"),
        lobby: resolve(here, "src/entries/lobby.ts"),
      },
    },
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
