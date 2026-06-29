import { defineConfig } from 'vite'

// Builds the zero-framework ES-module frontend into ../static/dist with
// content-hashed filenames (cache-busting). The backend serves that dir.
//
// sparrow-chat.js is NOT bundled: it ships in frontend/public/ and is served
// verbatim at /sparrow-chat.js via a plain <script> tag in index.html (so it's
// not a module import).
export default defineConfig({
  base: '/',
  root: '.',
  build: {
    outDir: '../static/dist',
    emptyOutDir: true,
    rollupOptions: {
      // Keep the runtime chat component out of the bundle.
      external: [/\/sparrow-chat\.js$/],
    },
  },
})
