// API 封装：所有和后端的通信都走这里
// 原理：axios 是一个 HTTP 客户端，帮我们发请求、收响应。
// baseURL '/api' 会被 Vite 代理到后端 8000 端口（见 vite.config.js）
import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 120000, // 生成行程要调 LLM + 高德，给足 2 分钟
})

// ---------- 行程 ----------

// 生成规划：POST /api/trip/plan
// payload: { destination, days, budget, companions, preferences, image_base64? }
export function planTrip(payload) {
  return http.post('/trip/plan', payload).then((r) => r.data)
}

// 自然语言编辑：POST /api/trip/{tripId}/edit
export function editTrip(tripId, instruction) {
  return http.post(`/trip/${tripId}/edit`, { instruction }).then((r) => r.data)
}

// 补全旧行程地理信息（车程/坐标）：POST /api/trip/{tripId}/refresh
export function refreshTrip(tripId) {
  return http.post(`/trip/${tripId}/refresh`).then((r) => r.data)
}

// 保存到历史：POST /api/trip（tokenUsage 一并存档，供 /trip/stats 汇总）
export function saveTrip(destination, summary, itinerary, tokenUsage) {
  return http
    .post('/trip', { destination, summary, itinerary_json: itinerary, token_usage: tokenUsage })
    .then((r) => r.data)
}

// 历史列表：GET /api/trip/history
export function listHistory() {
  return http.get('/trip/history').then((r) => r.data)
}

// 历史详情：GET /api/trip/{tripId}
export function getTrip(tripId) {
  return http.get(`/trip/${tripId}`).then((r) => r.data)
}

// 删除：DELETE /api/trip/{tripId}
export function deleteTrip(tripId) {
  return http.delete(`/trip/${tripId}`)
}

// ---------- 天气 ----------

// GET /api/weather/{city} → { city, adcode, live, forecasts }
export function getWeather(city) {
  return http.get(`/weather/${encodeURIComponent(city)}`).then((r) => r.data)
}

// ---------- 导出 ----------

// 导出 Markdown：把"当前页面数据"发给后端，返回 md 文本，前端下载
export async function exportMarkdown(payload) {
  const r = await http.post('/export/from-data?format=md', payload, {
    responseType: 'text',
  })
  downloadBlob(r.data, `${payload.destination || 'trip'}_行程单.md`, 'text/markdown')
}

// 导出 PDF：后端返回二进制文件流，前端触发浏览器下载
export async function exportPdf(payload) {
  const r = await http.post('/export/from-data?format=pdf', payload, {
    responseType: 'blob',
  })
  downloadBlob(r.data, 'travel_itinerary.pdf', 'application/pdf')
}

// 工具：把二进制/文本变成"下载文件"
function downloadBlob(content, filename, mime) {
  const blob = content instanceof Blob ? content : new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
