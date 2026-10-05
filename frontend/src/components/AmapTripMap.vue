<template>
  <!-- 高德地图组件：紫色序号标记 + 点击弹窗（用户起点不确定，不画驾车路线） -->
  <div :id="mapId" class="amap-container"></div>
</template>

<script setup>
// 高德地图组件
// 原理：
//   1) 用官方加载器 @amap/amap-jsapi-loader 异步加载高德 JS API
//   2) key 是"应用凭证"，securityJsCode 是 2021 后新 key 必配的"安全密钥"
//   3) 标记用"自定义 HTML 内容"（序号圆点），避免 setLabel 长文本互相重叠
//   4) 点击标记弹 InfoWindow（景点名/图片/地址/游玩建议）
//   5) setFitView(标记数组) 自动缩放视野框住所有景点
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import AMapLoader from '@amap/amap-jsapi-loader'

const props = defineProps({
  // 景点列表：[{ place, location: "lng,lat", ... }]
  spots: { type: Array, default: () => [] },
})

const mapId = `amap-${Math.random().toString(36).slice(2, 8)}`
const mapRef = ref(null)
let markers = [] // 已添加的标记（卸载时清理）
let infoWindow = null

// 高德 JS Key 与安全密钥（前端配置，与后端 .env 同步）
const AMAP_KEY = '***REMOVED-AMAP-JS-KEY***'
const AMAP_SECURITY_CODE = '***REMOVED-AMAP-SECURITY-CODE***'

// 标记的紫色序号圆点样式（CSS 直接写进 content，随标记渲染）
function markerHtml(index) {
  return `<div style="
    width:26px;height:26px;border-radius:50%;
    background:linear-gradient(135deg,#6366f1,#a855f7);
    color:#fff;font-size:13px;font-weight:bold;
    display:flex;align-items:center;justify-content:center;
    border:2px solid #fff;box-shadow:0 2px 6px rgba(139,92,246,.5);
    cursor:pointer;">${index + 1}</div>`
}

async function initMap() {
  // 加载高德 JS API 2.0
  const AMap = await AMapLoader.load({
    key: AMAP_KEY,
    securityJsCode: AMAP_SECURITY_CODE,
    version: '2.0',
  })

  // 建地图（先全国视野，fitView 会再调整）
  mapRef.value = new AMap.Map(mapId, { zoom: 5, center: [104, 35] })
  infoWindow = new AMap.InfoWindow({ offset: new AMap.Pixel(0, -28) })

  const valid = props.spots.filter((s) => s.location)
  if (valid.length === 0) return

  // 1) 序号圆点标记（不显示长文本，避免重叠）
  const markerList = []
  valid.forEach((s, i) => {
    const [lng, lat] = s.location.split(',').map(Number)
    const marker = new AMap.Marker({
      position: [lng, lat],
      content: markerHtml(i), // 自定义 HTML 内容
      anchor: 'center',
      offset: new AMap.Pixel(0, -14),
    })
    marker.on('click', () => {
      infoWindow.setContent(
        `<div style="max-width:240px;padding:6px">
          ${s.image_url ? `<img src="${s.image_url}" style="width:100%;border-radius:8px;margin-bottom:6px"/>` : ''}
          <div style="font-weight:bold;font-size:14px">${i + 1}. ${s.place}</div>
          ${s.address ? `<div style="color:#666;font-size:12px;margin-top:4px">${s.address}</div>` : ''}
          ${s.play_guide ? `<div style="color:#6d5ef0;font-size:12px;margin-top:4px">🔍 ${s.play_guide}</div>` : ''}
          ${s.cost !== undefined && s.cost !== '' && s.cost !== 0 ? `<div style="color:#666;font-size:12px;margin-top:4px">费用：${s.cost}</div>` : ''}
        </div>`,
      )
      infoWindow.open(mapRef.value, [lng, lat])
    })
    mapRef.value.add(marker)
    markerList.push(marker)
  })
  markers = markerList

  // 2) 视野自动框住所有景点（正确的 fitView 用法：传标记数组）
  mapRef.value.setFitView(markerList, false, [60, 40, 60, 40], 16)
}

// 景点变化时重建（智能编辑后刷新）
watch(
  () => props.spots,
  () => {
    if (mapRef.value) {
      mapRef.value.clearMap()
      markers = []
      initMap()
    }
  },
  { deep: true },
)

onMounted(initMap)

onBeforeUnmount(() => {
  if (mapRef.value) mapRef.value.destroy()
})
</script>

<style scoped>
.amap-container {
  width: 100%;
  height: 420px;
  border-radius: 10px;
}
</style>
