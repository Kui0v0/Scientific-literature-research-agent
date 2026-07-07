<template>
  <el-dialog v-model="visible" :title="editingUserUsername ? '编辑用户权限' : '新增用户账号'" width="520px">
    <el-form label-position="top" class="feature-form">
      <el-form-item label="姓名">
        <el-input v-model="userForm.name" placeholder="请输入姓名" />
      </el-form-item>
      <el-form-item label="账号">
        <el-input v-model="userForm.username" :disabled="Boolean(editingUserUsername)" placeholder="请输入登录账号" />
      </el-form-item>
      <el-form-item label="密码">
        <el-input
          v-model="userForm.password"
          type="password"
          show-password
          :placeholder="editingUserUsername ? '留空则不修改密码' : '请输入登录密码'"
        />
      </el-form-item>
      <el-form-item label="角色">
        <el-select v-model="userForm.role" :disabled="roleLocked">
          <el-option v-if="roleLocked" label="管理员" value="管理员" />
          <el-option label="分析师" value="分析师" />
          <el-option label="运营人员" value="运营人员" />
        </el-select>
      </el-form-item>
      <el-form-item label="邮箱">
        <el-input v-model="userForm.email" placeholder="请输入邮箱" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="$emit('save')">保存用户</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  editingUserUsername: { type: String, default: '' },
  roleLocked: { type: Boolean, default: false },
  userForm: { type: Object, required: true },
})

const emit = defineEmits(['update:modelValue', 'save'])

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})
</script>
