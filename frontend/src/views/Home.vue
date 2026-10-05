<template>
  <div class="page">
    <!-- ===== Hero：下一站去哪 ===== -->
    <div class="hero">
      <div class="hero-eyebrow">TRIP PLANNER</div>
      <h1>下一站，去哪？</h1>
      <div class="hero-sub">告诉我目的地、时间和偏好，AI 基于本地攻略与实时天气为你编排一份可执行的旅行计划。</div>

      <div class="hero-stats">
        <div class="hero-stat">
          <div class="num">{{ form.days }}<em>天</em></div>
          <div class="lbl">行程长度</div>
        </div>
        <div class="hero-stat">
          <div class="num">¥{{ form.budget }}<em>元</em></div>
          <div class="lbl">旅行预算</div>
        </div>
        <div class="hero-stat">
          <div class="num">{{ form.people }}<em>人</em></div>
          <div class="lbl">同行人数</div>
        </div>
      </div>

      <div class="route-strip">
        <span class="node"></span>
        <span class="seg"></span>
        <span>{{ form.destination || '目的地' }}</span>
        <span class="seg"></span>
        <span class="node end"></span>
      </div>
    </div>

    <div class="card">
      <!-- ===== 目的地与日期 ===== -->
      <div class="section-title">目的地与日期</div>
      <div style="display: flex; gap: 16px; flex-wrap: wrap">
        <div style="flex: 2; min-width: 160px">
          <label>目的城市</label>
          <input v-model="form.destination" placeholder="如：大理、西安、成都" />
          <!-- 热门城市快捷选择（14 城有本地攻略走 RAG，大理演示动态生成） -->
          <div style="margin-top: 6px">
            <span
              v-for="c in hotCities"
              :key="c"
              class="chip"
              :class="{ active: form.destination === c }"
              @click="form.destination = c"
            >{{ c }}</span>
          </div>
        </div>
        <div style="flex: 1; min-width: 130px">
          <label>开始日期</label>
          <input v-model="form.startDate" type="date" @change="calcDays" />
        </div>
        <div style="flex: 1; min-width: 130px">
          <label>结束日期</label>
          <input v-model="form.endDate" type="date" @change="calcDays" />
        </div>
        <div style="flex: 1; min-width: 90px">
          <label>人数</label>
          <select v-model="form.people">
            <option v-for="n in [1, 2, 3, 4, 5, 6]" :key="n" :value="n">{{ n }} 人</option>
          </select>
        </div>
        <div style="flex: 1; min-width: 90px">
          <label>旅行天数</label>
          <input :value="form.days + ' 天'" disabled style="background: #f2f3ff; color: #5b5bd6; font-weight: 600" />
        </div>
      </div>

      <!-- ===== 偏好设置 ===== -->
      <div class="section-title" style="margin-top: 22px">偏好设置</div>
      <div style="display: flex; gap: 16px; flex-wrap: wrap">
        <div style="flex: 1; min-width: 130px">
          <label>节奏偏好</label>
          <select v-model="form.pace">
            <option>轻松</option>
            <option>适中</option>
            <option>紧凑</option>
          </select>
        </div>
        <div style="flex: 1; min-width: 130px">
          <label>住宿偏好</label>
          <select v-model="form.stay">
            <option>经济型</option>
            <option>舒适型</option>
            <option>豪华型</option>
          </select>
        </div>
        <div style="flex: 1; min-width: 130px">
          <label>预算（元）</label>
          <input v-model.number="form.budget" type="number" min="100" step="100" />
        </div>
      </div>

      <div style="margin-top: 14px">
        <label>旅行偏好（可多选）</label>
        <div>
          <span
            v-for="tag in travelTags"
            :key="tag"
            class="chip"
            :class="{ active: form.travelPrefs.includes(tag) }"
            @click="toggleTag(form.travelPrefs, tag)"
          >{{ tag }}</span>
        </div>
      </div>

      <div style="margin-top: 10px">
        <label>饮食偏好（可多选）</label>
        <div>
          <span
            v-for="tag in foodTags"
            :key="tag"
            class="chip"
            :class="{ active: form.foodPrefs.includes(tag) }"
            @click="toggleTag(form.foodPrefs, tag)"
          >{{ tag }}</span>
        </div>
      </div>

      <!-- ===== 额外要求 ===== -->
      <div class="section-title" style="margin-top: 22px">额外要求</div>
      <textarea
        v-model="form.extra"
        rows="3"
        placeholder="如：不想太早起床，希望安排一个适合看日落的地点。"
      ></textarea>

      <!-- 多模态：保留图片上传（第一版需求） -->
      <div style="margin-top: 12px">
        <label>上传参考图片（选填，AI 识别图片辅助规划）</label>
        <div style="display: flex; align-items: center; gap: 12px; margin-top: 6px">
          <label class="file-btn">
            <input type="file" accept="image/*" @change="onFileChange" class="file-input-hidden" />
            {{ previewUrl ? '重新选择' : '选择图片' }}
          </label>
          <span v-if="previewUrl" style="font-size: 13px; color: var(--ink-soft)">已选择 1 张参考图片</span>
        </div>
        <img v-if="previewUrl" :src="previewUrl" class="preview" alt="预览" />
      </div>

      <div style="margin-top: 20px; text-align: center">
        <button class="btn" :disabled="store.loading || !form.destination" @click="generate" style="padding: 12px 44px; font-size: 15px">
          {{ store.loading ? '规划中…' : '开始规划' }}
        </button>
      </div>

      <div v-if="store.error" class="error">{{ store.error }}</div>
    </div>

    <div class="tip" style="text-align: center">
      已接通后端规划接口，生成成功后会直接展示真实行程（含 RAG 攻略、天气、地图）。
    </div>
  </div>
</template>

<script setup>
// 规划页（参考图布局）：目的地与日期 + 偏好设置 + 额外要求 + 图片上传
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { planTrip } from '../services/api'
import { planStore } from '../store'

const router = useRouter()
const store = planStore
const previewUrl = ref(null)

// 可选项
const travelTags = ['自然风景', '拍照', '美食', '古镇', '休闲', '人文历史', '购物']
const foodTags = ['少辣', '不吃香菜', '不吃葱', '素食', '清真', '海鲜']
// 热门城市（14 城有本地攻略走 RAG，大理演示动态城市生成）
const hotCities = [
  '大理', '西安', '成都', '北京', '上海', '杭州', '重庆',
  '南京', '苏州', '广州', '武汉', '长沙', '厦门', '青岛', '昆明',
]

const form = reactive({
  destination: '',
  startDate: '',
  endDate: '',
  people: 2,
  days: 3,
  pace: '轻松',
  stay: '舒适型',
  budget: 3200,
  travelPrefs: [],
  foodPrefs: [],
  extra: '',
})

// 结束日期 - 开始日期 + 1 = 旅行天数
function calcDays() {
  if (form.startDate && form.endDate) {
    const d1 = new Date(form.startDate)
    const d2 = new Date(form.endDate)
    const days = Math.round((d2 - d1) / 86400000) + 1
    form.days = days > 0 && days <= 30 ? days : 3
    if (days <= 0) alert('结束日期需晚于开始日期')
  }
}

// 本地日期格式化 YYYY-MM-DD（不用 toISOString，避免 UTC 时区差一天）
function formatDate(d) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

// 页面加载时给日期填默认值：开始=今天，结束=今天+2（默认 3 天行程）
onMounted(() => {
  if (!form.startDate) form.startDate = formatDate(new Date())
  if (!form.endDate) {
    const d = new Date()
    d.setDate(d.getDate() + 2)
    form.endDate = formatDate(d)
  }
  calcDays()
})

function toggleTag(list, tag) {
  const i = list.indexOf(tag)
  i >= 0 ? list.splice(i, 1) : list.push(tag)
}

// 图片 → base64
function onFileChange(e) {
  const file = e.target.files[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    previewUrl.value = reader.result
    store.userImage = reader.result
  }
  reader.readAsDataURL(file)
}

// 组装 preferences（把各偏好拼成自然语言，传给后端 LLM）
function buildPreferences() {
  const parts = []
  parts.push(`节奏：${form.pace}`)
  parts.push(`住宿：${form.stay}`)
  if (form.travelPrefs.length) parts.push(`旅行偏好：${form.travelPrefs.join('、')}`)
  if (form.foodPrefs.length) parts.push(`饮食偏好：${form.foodPrefs.join('、')}`)
  if (form.extra.trim()) parts.push(`额外要求：${form.extra.trim()}`)
  return parts.join('；')
}

async function generate() {
  store.error = ''
  store.loading = true
  try {
    const payload = {
      destination: form.destination,
      days: form.days,
      budget: form.budget,
      companions: `${form.people}人`,
      preferences: buildPreferences(),
    }
    if (store.userImage) {
      payload.image_base64 = store.userImage.split(',')[1]
    }
    const result = await planTrip(payload)
    store.result = result
    router.push('/result')
  } catch (err) {
    store.error = err.response?.data?.detail || err.message || '生成失败，请检查后端服务'
  } finally {
    store.loading = false
  }
}
</script>

<style scoped>
.preview {
  width: 140px;
  height: 100px;
  object-fit: cover;
  border-radius: 8px;
  margin-top: 10px;
  display: block;
  border: 1px solid var(--border);
}
/* 自定义文件选择按钮（隐藏原生 input，label 触发） */
.file-input-hidden {
  display: none;
}
.file-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border-radius: var(--radius-pill);
  border: 1px dashed var(--border-strong);
  background: #fff;
  color: var(--indigo);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  user-select: none;
  transition: all 0.15s;
}
.file-btn:hover {
  border-color: var(--indigo);
  background: #eef0ff;
}
</style>
