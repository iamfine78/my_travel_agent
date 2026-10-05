// 路由：URL 路径 → 页面组件
// /        → Home.vue     规划页（填表单，生成行程）
// /result  → Result.vue   结果页（展示行程 + 地图 + 导出）
// /history → History.vue  历史页（查看/删除已保存行程）
import { createRouter, createWebHistory } from 'vue-router'
import Home from './views/Home.vue'
import Result from './views/Result.vue'
import History from './views/History.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Home },
    { path: '/result', component: Result },
    { path: '/history', component: History },
  ],
})

export default router
