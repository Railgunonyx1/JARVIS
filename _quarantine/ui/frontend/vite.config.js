import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    host: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8765',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8765',
        ws: true,
      },
    },
    watch: {
      ignored: ['**/src-tauri/target/**'],
    },
  },
  build: {
    outDir: 'dist',
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: 'vendor-react', test: /node_modules\/(react|react-dom|zustand|scheduler)\// },
            { name: 'vendor-anim', test: /node_modules\/(framer-motion|motion-dom|motion-utils)\// },
            { name: 'vendor-three', test: /node_modules\/three\// },
            { name: 'vendor-echarts', test: /node_modules\/(echarts|zrender)\// },
          ],
        },
      },
    },
  },
  clearScreen: false,
  envPrefix: ['VITE_', 'TAURI_'],
})
