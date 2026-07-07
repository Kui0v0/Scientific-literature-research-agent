<template>
  <el-dialog v-model="visible" title="个人资料与头像设置" width="520px">
    <div class="profile-editor">
      <div class="avatar-editor">
        <span class="profile-avatar large">
          <img v-if="profileForm.avatarUrl" :src="profileForm.avatarUrl" :alt="`${profileForm.name}头像预览`" />
          <template v-else>{{ profileForm.avatarText }}</template>
        </span>
        <input ref="avatarInput" class="visually-hidden" type="file" accept="image/*" @change="$emit('avatar-change', $event)" />
        <div class="avatar-actions">
          <el-button type="primary" plain @click="avatarInput?.click()">本地导入头像</el-button>
          <el-button text @click="$emit('clear-avatar')">使用文字头像</el-button>
        </div>
      </div>
      <el-form label-position="top">
        <el-form-item label="头像文字">
          <el-input v-model="profileForm.avatarText" maxlength="2" show-word-limit />
        </el-form-item>
        <el-form-item label="姓名">
          <el-input v-model="profileForm.name" />
        </el-form-item>
        <el-form-item label="角色">
          <el-input :model-value="profile.role" disabled />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="profileForm.email" />
        </el-form-item>
      </el-form>
    </div>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="$emit('save')">保存资料</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  profile: { type: Object, required: true },
  profileForm: { type: Object, required: true },
})

const emit = defineEmits(['update:modelValue', 'avatar-change', 'clear-avatar', 'save'])
const avatarInput = ref(null)

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})
</script>
