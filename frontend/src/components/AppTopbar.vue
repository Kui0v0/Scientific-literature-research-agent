<template>
  <header class="topbar">
    <div class="search-wrap">
      <el-input
        v-model="queryProxy"
        :prefix-icon="Search"
        size="large"
        placeholder="搜索文献、主题、功能..."
        @keyup.enter="$emit('run-full-agent')"
      />
    </div>
    <div class="topbar-actions">
      <el-badge :value="unreadNotificationCount" :hidden="unreadNotificationCount === 0" :max="99" type="danger">
        <el-button :icon="Bell" circle @click="$emit('open-notifications')" />
      </el-badge>
      <el-button :icon="QuestionFilled" circle @click="$emit('open-help')" />

      <el-dropdown trigger="click" @command="$emit('profile-command', $event)">
        <button class="profile" type="button">
          <span class="profile-avatar">
            <img v-if="profile.avatarUrl" :src="profile.avatarUrl" :alt="`${profile.name}头像`" />
            <template v-else>{{ profile.avatarText }}</template>
          </span>
          <div>
            <strong>{{ profile.name }}</strong>
            <span>{{ profile.role }}</span>
          </div>
          <el-icon><ArrowDown /></el-icon>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="profile">个人资料</el-dropdown-item>
            <el-dropdown-item command="avatar">修改头像</el-dropdown-item>
            <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { ArrowDown, Bell, QuestionFilled, Search } from '@element-plus/icons-vue'

const props = defineProps({
  query: { type: String, required: true },
  profile: { type: Object, required: true },
  unreadNotificationCount: { type: Number, default: 0 },
})

const emit = defineEmits([
  'update:query',
  'run-full-agent',
  'open-notifications',
  'open-help',
  'profile-command',
])

const queryProxy = computed({
  get: () => props.query,
  set: (value) => emit('update:query', value),
})
</script>
