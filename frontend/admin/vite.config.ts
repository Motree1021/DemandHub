import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  // 产物由 FastAPI 挂在 /admin/ 路径下，资源用相对路径
  base: './',
  plugins: [vue()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: { port: 5175, proxy: { '/demandhub-api': { target: 'http://127.0.0.1:8000', changeOrigin: true } } }
})
