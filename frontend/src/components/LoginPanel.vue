<template>
  <section class="login-shell">
    <div class="login-art">
      <div class="brand login-brand">
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
      <h1>科研流程，一站式完成</h1>
      <p>登录后可使用真实文献检索、研究空白探测、实验方案生成、论文写作辅助和可视化报告功能。</p>
      <div class="login-metrics">
        <span><b>PubMed</b>真实检索</span>
        <span><b>arXiv</b>论文接入</span>
        <span><b>Crossref</b>DOI 溯源</span>
      </div>
    </div>

    <div class="login-card">
      <el-tabs v-model="authModeProxy" stretch>
        <el-tab-pane label="账号登录" name="login">
          <el-form label-position="top" @submit.prevent>
            <el-form-item label="账号">
              <el-input v-model="loginForm.username" placeholder="请输入账号" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="loginForm.password" type="password" show-password placeholder="请输入密码" @keyup.enter="$emit('login')" />
            </el-form-item>
            <el-button class="login-button" type="primary" :loading="loading === 'login'" @click="$emit('login')">登录进入系统</el-button>
          </el-form>
        </el-tab-pane>
        <el-tab-pane label="注册使用" name="register">
          <el-form label-position="top" @submit.prevent>
            <el-form-item label="姓名">
              <el-input v-model="registerForm.name" placeholder="请输入姓名" />
            </el-form-item>
            <el-form-item label="账号">
              <el-input v-model="registerForm.username" placeholder="请输入账号" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="registerForm.password" type="password" show-password placeholder="至少 6 位" @keyup.enter="$emit('register')" />
            </el-form-item>
            <el-button class="login-button" type="primary" @click="$emit('register')">注册并登录</el-button>
            <p class="register-note">注册后默认为分析师，可使用核心功能和系统设置，不能访问系统日志、用户与权限管理。</p>
          </el-form>
        </el-tab-pane>
      </el-tabs>

      <div class="account-panel">
        <h3>账号安全说明</h3>
        <p>请使用管理员在数据库中创建的账号登录；新用户可注册使用核心科研功能，默认角色为分析师。</p>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  authMode: { type: String, required: true },
  loginForm: { type: Object, required: true },
  registerForm: { type: Object, required: true },
  loading: { type: String, default: '' },
})

const emit = defineEmits(['update:authMode', 'login', 'register'])

const authModeProxy = computed({
  get: () => props.authMode,
  set: (value) => emit('update:authMode', value),
})
</script>
