import { defineConfig } from 'vite'

// Builds the zero-framework ES-module frontend into ../static/dist with
// content-hashed filenames (cache-busting). The backend serves that dir.
//
// sparrow-chat.js is NOT bundled: it's synced at runtime by the backend from
// the sparrow package into static/dist/, and referenced via an absolute
// /ui/sparrow-chat.js <script> tag in index.html (so it's not a module import).
export default defineConfig({
  base: '/ui/',
  root: '.',
  build: {
    outDir: '../static/dist',
    emptyOutDir: true,
    rollupOptions: {
      // Keep the runtime-synced sparrow chat out of the bundle.
      external: [/\/ui\/sparrow-chat\.js$/],
    },
  },
})
