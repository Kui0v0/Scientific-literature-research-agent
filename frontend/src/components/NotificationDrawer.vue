<template>
  <el-drawer v-model="visible" title="通知中心" size="420px" @closed="$emit('closed')">
    <div v-if="notifications.length" class="activity-list notification-list">
      <div
        v-for="item in notifications"
        :key="item.id"
        :class="['activity-row', 'notification-row', { expanded: isExpanded(item.id), unread: isUnread(item.id) }]"
      >
        <span :class="['activity-dot', item.tone]">
          <el-icon><component :is="item.icon" /></el-icon>
        </span>
        <div class="notification-main">
          <p>{{ item.text }}</p>
          <div class="notification-meta">
            <time>{{ item.time }}</time>
            <span v-if="isUnread(item.id)">新通知</span>
            <button v-if="item.text.length > 24" type="button" @click="$emit('toggle', item.id)">
              {{ isExpanded(item.id) ? '收起' : '展开' }}
            </button>
          </div>
        </div>
      </div>
    </div>
    <el-empty v-else description="当前账号暂无通知" />
  </el-drawer>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  notifications: { type: Array, default: () => [] },
  isExpanded: { type: Function, required: true },
  isUnread: { type: Function, required: true },
})

const emit = defineEmits(['update:modelValue', 'closed', 'toggle'])

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})
</script>
