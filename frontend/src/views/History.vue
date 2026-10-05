<template>
  <div class="page">
    <div class="card">
      <div style="display: flex; align-items: baseline; justify-content: space-between; gap: 16px; flex-wrap: wrap">
        <div>
          <h2 style="margin-bottom: 2px">历史行程</h2>
          <p style="font-size: 13px; color: var(--ink-faint); margin-bottom: 6px">
            保存过的行程都在这里，随时打开续用或导出。
          </p>
        </div>
        <button class="btn secondary" @click="load">刷新列表</button>
      </div>

      <div v-if="loading" class="loading">加载中…</div>

      <!-- 空状态：邀请去规划 -->
      <div v-else-if="records.length === 0" class="empty-state">
        <div class="empty-icon">◌</div>
        <div class="empty-title">还没有保存过行程</div>
        <div class="empty-desc">去规划页生成一份旅行计划，保存后就会出现在这里。</div>
        <router-link to="/" class="btn" style="margin-top: 16px">去规划</router-link>
      </div>

      <!-- 卡片式列表（路线感：圆点 + 目的地大标题） -->
      <div v-for="rec in records" :key="rec.trip_id" class="history-card">
        <div class="history-route">
          <span class="node"></span>
          <span class="line"></span>
          <span class="node end"></span>
        </div>
        <div style="flex: 1; min-width: 0">
          <div class="dest">{{ rec.destination }}</div>
          <div style="font-size: 12px; color: var(--ink-faint); margin: 2px 0">
            {{ displayId(rec) }}
          </div>
          <div style="font-size: 13px; color: var(--ink-soft); margin: 6px 0; line-height: 1.6">
            {{ rec.summary || '（无摘要）' }}
          </div>
          <div style="font-size: 12px; color: var(--ink-faint)">
            更新时间：{{ formatTime(rec.updated_at || rec.created_at) }}
          </div>
        </div>
        <div style="display: flex; flex-direction: column; gap: 8px; justify-content: center">
          <button class="btn" @click="openTrip(rec.trip_id)">查看详情</button>
          <button class="btn danger" @click="removeTrip(rec.trip_id)">删除行程</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
// 历史页（参考图布局）：卡片列表 + 查看详情/删除 + 刷新
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listHistory, getTrip, deleteTrip } from '../services/api'
import { planStore } from '../store'

const router = useRouter()
const store = planStore
const records = ref([])
const loading = ref(true)

onMounted(load)

async function load() {
  loading.value = true
  try {
    const data = await listHistory()
    records.value = data.records || []
  } catch (err) {
    alert('加载失败：' + (err.response?.data?.detail || err.message))
  } finally {
    loading.value = false
  }
}

// 行程 ID 显示名（参考图风格：trip_大理_2026-04-29）
function displayId(rec) {
  const date = (rec.itinerary?.days?.[0]?.date_hint || '').match(/\d{4}-\d{2}-\d{2}/)?.[0] || ''
  return `trip_${rec.destination}_${date}`
}

async function openTrip(tripId) {
  try {
    const rec = await getTrip(tripId)
    store.result = {
      trip_id: rec.trip_id,
      destination: rec.destination,
      itinerary: rec.itinerary,
      budget_split: rec.itinerary.budget_split || {},
      weather: null,
      sources: [],
    }
    store.userImage = null
    router.push('/result')
  } catch (err) {
    alert('打开失败：' + (err.response?.data?.detail || err.message))
  }
}

async function removeTrip(tripId) {
  if (!confirm('确定删除这条行程？')) return
  try {
    await deleteTrip(tripId)
    await load()
  } catch (err) {
    alert('删除失败：' + (err.response?.data?.detail || err.message))
  }
}

function formatTime(iso) {
  return new Date(iso).toLocaleString('zh-CN')
}
</script>

<style scoped>
/* 空状态（邀请去规划） */
.empty-state {
  text-align: center;
  padding: 48px 0 40px;
}
.empty-icon {
  font-size: 44px;
  color: var(--border-strong);
  line-height: 1;
}
.empty-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--navy);
  margin-top: 12px;
}
.empty-desc {
  font-size: 13px;
  color: var(--ink-faint);
  margin-top: 6px;
}

/* 历史卡片左侧路线感：起点 → 终点 */
.history-route {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 2px 0;
  align-self: stretch;
}
.history-route .node {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--amber);
  box-shadow: 0 0 0 3px rgba(245, 158, 11, 0.18);
  flex-shrink: 0;
  margin-top: 4px;
}
.history-route .line {
  flex: 1;
  width: 2px;
  background: repeating-linear-gradient(to bottom, rgba(59, 130, 246, 0.35) 0 4px, transparent 4px 8px);
  min-height: 24px;
}
.history-route .node.end {
  background: var(--sky);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.18);
  margin-bottom: 4px;
}
</style>
