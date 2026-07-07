<template>
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-mark" aria-hidden="true">
        <span></span>
        <span></span>
        <span></span>
        <span></span>
      </div>
      <div>
        <strong>科学文献研究智能体</strong>
        <p>从综述到实验设计到商业项目</p>
      </div>
    </div>

    <nav class="sidebar-nav" aria-label="主导航">
      <a
        v-for="item in primaryNav"
        :key="item.label"
        :class="{ active: currentView === item.view }"
        href="#"
        @click.prevent="$emit('navigate', item.view)"
      >
        <el-icon><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
      </a>
    </nav>

    <div class="nav-group-title">核心功能</div>
    <nav class="sidebar-nav compact" aria-label="核心功能">
      <a
        v-for="item in featureNav"
        :key="item.label"
        :class="{ active: currentView === item.view }"
        href="#"
        @click.prevent="$emit('navigate', item.view)"
      >
        <el-icon><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
      </a>
    </nav>

    <div class="nav-group-title">系统管理</div>
    <nav class="sidebar-nav compact" aria-label="系统管理">
      <a
        v-for="item in systemNav"
        :key="item.label"
        :class="{ active: currentView === item.view, disabled: !canAccessSystemView(item.view) }"
        :aria-disabled="!canAccessSystemView(item.view)"
        href="#"
        @click.prevent="$emit('navigate', item.view)"
      >
        <el-icon><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
        <small v-if="!canAccessSystemView(item.view)">受限</small>
      </a>
    </nav>

    <section class="usage-card">
      <h3>今日使用统计</h3>
      <div v-for="item in usageStats" :key="item.label" class="usage-row">
        <span :class="['usage-dot', item.tone]">
          <el-icon><component :is="item.icon" /></el-icon>
        </span>
        <b>{{ item.label }}</b>
        <strong>{{ item.value }}</strong>
      </div>
    </section>
  </aside>
</template>

<script setup>
defineProps({
  currentView: { type: String, required: true },
  primaryNav: { type: Array, default: () => [] },
  featureNav: { type: Array, default: () => [] },
  systemNav: { type: Array, default: () => [] },
  usageStats: { type: Array, default: () => [] },
  canAccessSystemView: { type: Function, required: true },
})

defineEmits(['navigate'])
</script>
