import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': new URL('./src', import.meta.url).pathname
    }
  },
  server: {
    port: 17317,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:18317',
        changeOrigin: true
      }
    }
  }
})
