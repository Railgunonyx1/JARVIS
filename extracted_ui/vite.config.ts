import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"
import tailwindcss from "@tailwindcss/vite"
import path from "node:path"

// Tauri-ready Vite config.
// When wrapped by Tauri, the desktop shell loads this dev server (or the built
// dist/) and exposes native APIs on window.__TAURI__. In the browser preview the
// same build runs standalone and talks to the JARVIS daemon over WebSocket.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  clearScreen: false,
  server: {
    host: true,
    port: 5173,
    strictPort: false,
    allowedHosts: true,
    // Tauri expects a fixed dev origin; harmless in the browser preview.
    hmr: { overlay: true },
  },
  // Keep chunks reasonable for the desktop bundle.
  build: {
    target: "es2022",
    sourcemap: false,
  },
})
