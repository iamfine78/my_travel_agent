<template>
  <!-- 顶部导航：深航蓝实色 -->
  <div class="navbar">
    <span class="brand-en">TRIP PLANNER DEMO</span>
    <span class="brand">智能旅行助手</span>
    <router-link to="/">规划页</router-link>
    <router-link to="/result">结果页</router-link>
    <router-link to="/history">历史列表</router-link>
  </div>
  <router-view />
</template>
