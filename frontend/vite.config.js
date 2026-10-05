// Vite 开发服务器配置
// 作用：1) 起前端开发服务（端口 5173）
//       2) 把 /api 开头的请求"代理"到后端 FastAPI（8000），
//          前端写 /api/xxx 即可，不用关心后端地址，也没有跨域问题
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // 请求 /api/trip/plan → http://localhost:8000/api/trip/plan
      '/api': 'http://localhost:8000',
    },
  },
})
