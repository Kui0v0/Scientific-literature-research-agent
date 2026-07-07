<template>
  <el-drawer v-model="visible" title="全部活动" size="460px">
    <div class="todo-summary">
      <strong>{{ profile.name }} 的科研活动</strong>
      <span>仅显示检索、分析、实验设计、论文写作和报告生成等业务活动。</span>
    </div>

    <div v-if="activities.length" class="activity-list activity-drawer-list">
      <div v-for="item in activities" :key="item.id" class="activity-row activity-drawer-row">
        <span :class="['activity-dot', item.tone]">
          <el-icon><component :is="item.icon" /></el-icon>
        </span>
        <div class="activity-drawer-main">
          <p>{{ item.text }}</p>
          <time>{{ item.time }}</time>
        </div>
      </div>
    </div>
    <el-empty v-else description="当前用户暂无科研活动" />
  </el-drawer>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  activities: { type: Array, default: () => [] },
  profile: { type: Object, required: true },
})

const emit = defineEmits(['update:modelValue'])

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})
</script>
