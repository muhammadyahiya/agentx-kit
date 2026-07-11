import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { viteSingleFile } from 'vite-plugin-singlefile'

// https://vite.dev/config/
// Single-file output (JS+CSS inlined into one index.html) so this can be
// vendored the same way as the existing viewer's dagre.min.js etc. — one
// self-contained artifact, no separate asset files to serve.
export default defineConfig({
  plugins: [react(), viteSingleFile()],
  build: { cssCodeSplit: false, assetsInlineLimit: 100000000 },
})
