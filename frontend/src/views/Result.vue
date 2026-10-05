<template>
  <div class="page">
    <!-- 未生成行程 -->
    <div v-if="!store.result" class="card" style="text-align: center; padding: 60px">
      <p style="margin-bottom: 16px">还没有行程，请先到「规划页」生成。</p>
      <router-link to="/" class="btn">去规划</router-link>
    </div>

    <template v-else>
      <div class="result-layout">
        <!-- ===== 左栏：行程导航 + 操作按钮 ===== -->
        <aside class="result-left">
          <div class="nav-menu">
            <div class="menu-title">行程导航</div>
            <a v-for="item in menu" :key="item.id" class="menu-item" @click="scrollTo(item.id)">
              {{ item.label }}
            </a>

            <div class="menu-title">操作</div>
            <button class="menu-btn primary" @click="doSave">{{ saving ? '保存中…' : '💾 保存行程' }}</button>
            <button class="menu-btn primary" @click="doExport('pdf')">📄 导出 PDF</button>
            <button class="menu-btn primary" @click="doExport('md')">📝 导出 Markdown</button>
            <button class="menu-btn" @click="$router.push('/history')">🗂 历史列表</button>
            <button class="menu-btn" @click="$router.push('/')">← 返回规划页</button>
            <button class="menu-btn" @click="scrollToTop">↑ 回到顶部</button>
          </div>
        </aside>

        <!-- ===== 中栏：行程概览 + 地图 + 每日行程 ===== -->
        <main class="result-main">
          <!-- 行程概览 -->
          <div id="overview" class="card">
            <div style="display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap">
              <h2 style="margin-bottom: 0; font-size: 22px">{{ itinerary.destination }}旅行计划</h2>
              <div style="font-size: 12px; color: var(--ink-faint)">{{ dateRange }}</div>
            </div>
            <div class="overview-hero">
              <div>
                <div class="ov-num">{{ itinerary.days?.length || 0 }}<small>天</small></div>
                <div class="ov-lbl">行程长度</div>
              </div>
              <div>
                <div class="ov-num">¥{{ budgetTotal }}<small>元</small></div>
                <div class="ov-lbl">预估总预算</div>
              </div>
              <div>
                <div class="ov-num">{{ allSpots.length }}<small>站</small></div>
                <div class="ov-lbl">规划点位</div>
              </div>
            </div>
            <div style="font-size: 14px; color: var(--ink-soft)">{{ itinerary.summary }}</div>
            <div v-if="store.result.sources?.length" class="tip" style="margin-top: 8px">
              信息来源：{{ store.result.sources.join('、') }}
            </div>

            <!-- 旧版本统一提示：游玩建议/住宿/坐标都是新版本才有 -->
            <div v-if="missingGuides > 0" class="tip" style="margin-top: 10px">
              该行程为旧版本生成：建议在规划页重新生成一次，即可获得完整的游玩建议、住宿安排与地图坐标。
            </div>

            <!-- 用户上传图片（多模态） -->
            <div v-if="store.userImage" style="margin-top: 10px">
              <p style="font-size: 13px; color: var(--ink-soft)">你上传的参考图片（AI 已识别并融入行程）：</p>
              <img :src="store.userImage" style="width: 180px; border-radius: 8px" alt="用户图片" />
            </div>
          </div>

          <!-- 旅行提示 -->
          <div id="tips" class="card" v-if="itinerary.tips?.length">
            <h2>旅行提示</h2>
            <div v-for="(t, i) in itinerary.tips" :key="i" class="tip">{{ t }}</div>
          </div>

          <!-- 景点地图 -->
          <div id="map" class="card">
            <h2>景点地图</h2>
            <AmapTripMap :spots="allSpots" />
          </div>

          <!-- 点位明细（卡片式：序号 + 名称 + 费用 + 地址 + 游玩建议全文） -->
          <div id="points" class="card" v-if="allSpots.length">
            <h2>点位明细</h2>
            <div v-for="(s, i) in allSpots" :key="i" class="point-item">
              <div class="point-no">{{ i + 1 }}</div>
              <div style="flex: 1; min-width: 0">
                <div class="point-head">
                  <b style="font-size: 15px">{{ s.place }}</b>
                  <span v-if="isFree(s.cost)" class="free-tag">免费</span>
                  <span v-else-if="s.cost" class="cost-tag">¥ {{ displayCost(s.cost) }}</span>
                </div>
                <div class="point-addr" v-if="s.address">📍 {{ s.address }}</div>
                <div class="point-addr" v-if="s.open_time">🕐 营业时间：{{ s.open_time }}</div>
                <div class="point-guide" v-if="s.play_guide">🔍 游玩建议：{{ s.play_guide }}</div>
                <div class="point-guide old" v-else>旧版本数据，重新生成可获取游玩建议</div>
              </div>
            </div>
          </div>

          <!-- 按天花费 -->
          <div id="daily-cost" class="card" v-if="dailyCosts.length">
            <h2>按天花费</h2>
            <table>
              <tr><th>天数</th><th>花费（元）</th></tr>
              <tr v-for="d in dailyCosts" :key="d.day">
                <td>第 {{ d.day }} 天</td>
                <td>{{ d.total }}</td>
              </tr>
            </table>
            <div class="tip" style="margin-top: 8px">
              注：为景点门票的估算值（从"120元""免费"等描述中提取数字），不含交通住宿餐饮——总预算见右侧预算明细。
            </div>          </div>

          <!-- 每日行程 -->
          <div id="daily" class="card" v-for="day in itinerary.days" :key="day.day">
            <h2>第 {{ day.day }} 天</h2>
            <div v-for="(slotName, slotKey) in slotLabels" :key="slotKey">
              <div v-if="day[slotKey]?.length" class="slot">
                <h4>{{ slotName }}</h4>
                <div v-for="(act, i) in day[slotKey]" :key="i" class="activity">
                  <img v-if="act.image_url" :src="act.image_url" :alt="act.place" />
                  <div style="flex: 1">
                    <b>{{ act.place }}</b>
                    <div style="font-size: 13px; color: #555">{{ act.description }}</div>
                    <!-- 到达后怎么玩 -->
                    <div v-if="act.play_guide" style="font-size: 13px; color: #6d5ef0; margin-top: 4px">
                      🔍 怎么玩：{{ act.play_guide }}
                    </div>
                    <div class="meta">
                      <span v-if="isFree(act.cost)">🎫 免费</span>
                      <span v-else-if="act.cost">🎫 {{ displayCost(act.cost) }}</span>
                      <span v-if="act.address">📍 {{ act.address }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-if="day.meals?.length" style="margin-top: 8px; font-size: 14px">
              🍜 餐饮：{{ day.meals.join('、') }}
            </div>
            <!-- 当天住宿安排 -->
            <div v-if="day.lodging" class="tip" style="margin-top: 6px">
              🏨 住宿：{{ day.lodging }}
            </div>
            <div v-if="day.note" class="tip">💡 {{ day.note }}</div>
          </div>

          <!-- 智能调整 -->
          <div id="edit" class="card">
            <h2>智能调整</h2>
            <p style="font-size: 13px; color: #666; margin-bottom: 8px">
              用一句话告诉 AI 你想怎么改，例如："第二天太累了，换成轻松的市区半日游"
            </p>
            <textarea v-model="editInstruction" rows="2" placeholder="输入修改指令…"></textarea>
            <button class="btn" :disabled="editing || !editInstruction" @click="doEdit">
              {{ editing ? '调整中…' : '应用修改' }}
            </button>
          </div>
        </main>

        <!-- ===== 右栏：预算明细 + 天气信息 ===== -->
        <aside class="result-right">
          <div id="budget" class="card">
            <h2>预算明细</h2>
            <div v-for="(label, key) in budgetLabels" :key="key" class="budget-row">
              <span class="lbl">{{ label }}</span>
              <span class="bar-track"><span class="bar-fill" :class="'bar-fill-' + key" :style="{ width: barWidth(key) }"></span></span>
              <span class="pct" :class="'pct-' + key">{{ barPercent(key) }}%</span>
              <span class="val">{{ splitValue(key) }} 元</span>
            </div>
            <div class="budget-total">
              <span>预估总费用</span>
              <span class="amt">¥{{ budgetTotal }}</span>
            </div>
            <div style="font-size: 12px; color: var(--ink-faint); margin-top: 6px">
              预算为模型估算，实际以出行消费为准
            </div>
          </div>

          <div id="weather" class="card" v-if="store.result.weather">
            <h2>天气信息</h2>
            <div v-for="f in store.result.weather.forecasts.slice(0, 4)" :key="f.date" class="weather-item">
              <div class="w-date">{{ formatDate(f.date) }}</div>
              <div style="font-size: 13px">
                {{ f.daytemp }}/{{ f.nighttemp }}°
              </div>
              <div style="font-size: 12px; color: #888">
                白天: {{ f.dayweather }} ｜ 夜间: {{ f.nightweather }}
              </div>
            </div>
          </div>
        </aside>
      </div>
    </template>
  </div>
</template>

<script setup>
// 结果页（参考图布局）：左导航 + 中行程 + 右预算/天气
import { computed, ref } from 'vue'
import AmapTripMap from '../components/AmapTripMap.vue'
import { planStore } from '../store'
import { editTrip, saveTrip, exportMarkdown, exportPdf } from '../services/api'

const store = planStore

const itinerary = computed(() => store.result?.itinerary || {})

// 左栏导航菜单（锚点 id 对应页面区块）
const menu = [
  { id: 'overview', label: '行程概览' },
  { id: 'budget', label: '预算明细' },
  { id: 'daily-cost', label: '按天花费' },
  { id: 'edit', label: '智能调整' },
  { id: 'map', label: '景点地图' },
  { id: 'weather', label: '天气信息' },
  { id: 'points', label: '点位明细' },
  { id: 'daily', label: '每日行程' },
]

function scrollTo(id) {
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

const slotLabels = { morning: '上午', afternoon: '下午', evening: '晚上' }
const budgetLabels = { tickets: '景点门票', lodging: '酒店住宿', food: '餐饮费用', transport: '交通费用', other: '其他' }

// 预算
function splitValue(key) {
  const v = store.result?.budget_split?.[key]
  return v ? Number(v).toFixed(0) : '0'
}
const budgetTotal = computed(() => {
  const s = store.result?.budget_split || {}
  return Object.values(s).reduce((sum, v) => sum + (Number(v) || 0), 0).toFixed(0)
})

// 预算条形宽度（相对总额的百分比，至少 2% 可显示）
function barWidth(key) {
  const v = Number(store.result?.budget_split?.[key]) || 0
  const total = Number(budgetTotal.value) || 1
  return Math.max(2, Math.round((v / total) * 100)) + '%'
}

// 预算占比百分比（进度条旁的数字）
function barPercent(key) {
  const v = Number(store.result?.budget_split?.[key]) || 0
  const total = Number(budgetTotal.value) || 1
  return Math.round((v / total) * 100)
}

// 按天花费：每天所有活动花费之和
// LLM 输出的 cost 可能是数字也可能是字符串（"成人120元"、"免费"），
// 所以先用 parseCost 提取数字再累加
function parseCost(cost) {
  if (typeof cost === 'number') return cost
  if (typeof cost === 'string') {
    const m = cost.match(/\d+(\.\d+)?/) // 提取第一个数字
    return m ? parseFloat(m[0]) : 0
  }
  return 0
}

const dailyCosts = computed(() => {
  const rows = []
  for (const day of itinerary.value.days || []) {
    let total = 0
    for (const key of ['morning', 'afternoon', 'evening']) {
      for (const a of day[key] || []) {
        total += parseCost(a.cost)
      }
    }
    rows.push({ day: day.day, total: total.toFixed(0) })
  }
  return rows
})

// 所有景点（地图 + 点位明细）
const allSpots = computed(() => {
  const spots = []
  for (const day of itinerary.value.days || []) {
    for (const key of ['morning', 'afternoon', 'evening']) {
      for (const act of day[key] || []) spots.push(act)
    }
  }
  return spots
})

// 检测旧版本：缺游玩建议的景点数量（play_guide/lodging 是新版本字段，旧数据没有）
const missingGuides = computed(() => {
  let n = 0
  for (const day of itinerary.value.days || []) {
    for (const key of ['morning', 'afternoon', 'evening']) {
      for (const a of day[key] || []) if (!a.play_guide) n++
    }
  }
  return n
})

// 一键补全已移除：游玩建议/住宿由 LLM 生成，补全只能补坐标、价值低，
// 旧行程统一提示"重新生成"。（后端 POST /api/trip/{trip_id}/refresh 接口保留备用）

// 展示辅助
// 费用为 0 或含"免费" → 显示"免费"徽标
function isFree(cost) {
  if (cost === 0 || cost === '0' || cost === '免费') return true
  if (typeof cost === 'string' && cost.includes('免费') && !cost.match(/\d+/)) return true
  return false
}
function displayCost(cost) {
  return cost
}
function formatDate(dateStr) {
  return (dateStr || '').slice(5).replace('-', '-') // "2026-04-29" → "04-29"
}
const displayTripId = computed(() => {
  const id = store.result?.trip_id
  return id ? `trip_${itinerary.value.destination}_${(store.result.weather?.forecasts?.[0]?.date || '').slice(0, 10) || id.slice(0, 8)}` : ''
})
const dateRange = computed(() => {
  const fs = store.result?.weather?.forecasts || []
  if (fs.length >= 2) return `${fs[0].date.slice(5)} 至 ${fs[fs.length - 1].date.slice(5)}`
  return `${itinerary.value.days?.length || ''} 天行程`
})

// ---------- 智能编辑 ----------
const editInstruction = ref('')
const editing = ref(false)
async function doEdit() {
  editing.value = true
  try {
    const result = await editTrip(store.result.trip_id, editInstruction.value)
    store.result = result
    editInstruction.value = ''
  } catch (err) {
    alert('编辑失败：' + (err.response?.data?.detail || err.message))
  } finally {
    editing.value = false
  }
}

// ---------- 保存 ----------
const saving = ref(false)
async function doSave() {
  saving.value = true
  try {
    // 保存时把天气一并归档，历史导出的 PDF 封面也能显示天气预览
    const payloadItinerary = { ...itinerary.value, weather_data: store.result.weather || null }
    await saveTrip(itinerary.value.destination, itinerary.value.summary, payloadItinerary, store.result.token_usage)
    alert('✅ 已保存到历史行程')
  } catch (err) {
    alert('保存失败：' + (err.response?.data?.detail || err.message))
  } finally {
    saving.value = false
  }
}

// ---------- 导出 ----------
async function doExport(format) {
  try {
    const payload = {
      destination: itinerary.value.destination,
      itinerary: itinerary.value,
      weather: store.result.weather || null,
    }
    if (format === 'md') {
      await exportMarkdown(payload)
      alert('✅ Markdown 已下载')
    } else {
      await exportPdf(payload)
      alert('✅ PDF 已下载')
    }
  } catch (err) {
    alert('导出失败：' + (err.response?.data?.detail || err.message))
  }
}
</script>

<style scoped>
.weather-item {
  background: #f8f6ff;
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 8px;
}
</style>
