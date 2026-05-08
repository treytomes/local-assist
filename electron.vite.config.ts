import { defineConfig, externalizeDepsPlugin } from 'electron-vite'
import { resolve } from 'path'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// Evaluated per-path before inotify handles are opened — much more effective
// than glob patterns which are checked after the handle is already allocated.
function ignored(p: string): boolean {
  return (
    p.includes('/.venv/') ||
    p.includes('/node_modules/') ||
    p.includes('/out/') ||
    p.includes('/dist/') ||
    p.includes('/__pycache__/') ||
    p.includes('/.git/') ||
    p.endsWith('.pyc')
  )
}

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: { index: resolve(__dirname, 'src/main/index.ts') },
        external: ['electron']
      }
    }
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: { index: resolve(__dirname, 'src/preload/index.ts') },
        external: ['electron']
      }
    }
  },
  renderer: {
    root: resolve(__dirname, 'src/renderer'),
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        '@shared': resolve(__dirname, 'src/shared'),
        '@renderer': resolve(__dirname, 'src/renderer')
      }
    },
    server: {
      watch: {
        ignored,
        // Only watch src/ — keeps instance count low
        paths: [resolve(__dirname, 'src')]
      }
    },
    build: {
      rollupOptions: {
        input: { index: resolve(__dirname, 'src/renderer/index.html') }
      }
    }
  }
})
