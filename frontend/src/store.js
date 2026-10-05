// 共享状态（内存版 store）
// 为什么需要它：规划页生成行程后要跳转到结果页展示。
// 行程数据很大（几 KB JSON），不适合塞进 URL 参数，
// 所以放在一个全局响应式对象里，任何页面都能读。
import { reactive } from 'vue'

export const planStore = reactive({
  // 后端 PlanResponse：{ trip_id, destination, itinerary, budget_split, weather, sources }
  result: null,
  // 用户上传的图片（dataURL），结果页要展示"识别到的图片"
  userImage: null,
  loading: false,
  error: '',
})
