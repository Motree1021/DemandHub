import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

// 同域部署在 /h5/ 路径下（对接标准入口 https://{域名}/h5/report?from=chuangjinls&ticket=...）
// base 经 VITE_BASE 注入：本地/同域 nginx 为 '/h5/'，H5 Publish TEST(Kong 路径前缀)为 '/demandhub-frontend/h5/'
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '')
  return {
    base: env.VITE_BASE || '/h5/',
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    server: {
      port: 5174,
      proxy: {
        '/api': {
          target: 'http://localhost:8080',
          changeOrigin: true
        }
      }
    }
  }
})
