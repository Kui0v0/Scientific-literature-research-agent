<template>
  <el-config-provider namespace="el">
    <LoginPanel
      v-if="!isAuthenticated"
      v-model:auth-mode="authMode"
      :login-form="loginForm"
      :register-form="registerForm"
      :loading="loading"
      @login="login"
      @register="register"
    />

    <div v-else class="dashboard-shell">
      <AppSidebar
        :current-view="currentView"
        :primary-nav="primaryNav"
        :feature-nav="featureNav"
        :system-nav="systemNav"
        :usage-stats="usageStats"
        :can-access-system-view="canAccessSystemView"
        @navigate="navigateTo"
      />

      <MainContent
        v-model:query="query"
        v-model:trend-range="trendRange"
        v-model:selected-sources="selectedSources"
        :profile="profile"
        :unread-notification-count="unreadNotificationCount"
        :error="error"
        :current-view="currentView"
        :current-page="currentPage"
        :loading="loading"
        :stat-cards="statCards"
        :trend-stats="trendStats"
        :trend-series="trendSeries"
        :trend-y-axis-labels="trendYAxisLabels"
        :chart-months="chartMonths"
        :trend-empty-text="trendEmptyText"
        :gap-stats="gapStats"
        :gap-loading="gapLoading"
        :radar-metrics="radarMetrics"
        :radar-current-values="radarCurrentValues"
        :radar-average-values="radarAverageValues"
        :radar-label-position="radarLabelPosition"
        :todo-items="todoItems"
        :quick-actions="quickActions"
        :recent-activities="recentActivities"
        :open-activity-drawer="openActivityDrawer"
        :system-status="systemStatus"
        :system-load="systemLoad"
        :task="task"
        :analysis="analysis"
        :hotspot-max="hotspotMax"
        :experiment="experiment"
        :draft-sections="draftSections"
        :drafts="drafts"
        :report="report"
        :download-url="downloadUrl"
        :users="users"
        :roles="roles"
        :log-rows="logRows"
        :settings="settings"
        :full-agent-status="fullAgentStatus"
        :run-full-agent="runFullAgent"
        :run-search="runSearch"
        :open-notification-drawer="openNotificationDrawer"
        :open-help="openHelp"
        :handle-profile-command="handleProfileCommand"
        :line-points="linePoints"
        :radar-grid="radarGrid"
        :radar-axis="radarAxis"
        :radar-polygon="radarPolygon"
        :radar-points="radarPoints"
        :is-todo-done="isTodoDone"
        :toggle-todo="toggleTodo"
        :open-todo-drawer="openTodoDrawer"
        :navigate-to="navigateTo"
        :run-analysis="runAnalysis"
        :progress-value="progressValue"
        :generate-experiment="generateExperiment"
        :generate-all-drafts="generateAllDrafts"
        :generate-draft="generateDraft"
        :generate-report="generateReport"
        :open-create-user="openCreateUser"
        :open-edit-user="openEditUser"
        :delete-managed-user="deleteManagedUser"
        :refresh-logs="refreshLogs"
        :save-settings="saveSettings"
        @clear-error="error = ''"
      />
    </div>

    <ProfileDialog
      v-model="profileDialogVisible"
      :profile="profile"
      :profile-form="profileForm"
      @avatar-change="handleAvatarFile"
      @clear-avatar="clearAvatarImage"
      @save="saveProfile"
    />

    <UserDialog
      v-model="userDialogVisible"
      :editing-user-username="editingUserUsername"
      :role-locked="editingUserRoleLocked"
      :user-form="userForm"
      @save="saveManagedUser"
    />

    <NotificationDrawer
      v-model="notificationDrawerVisible"
      :notifications="notifications"
      :is-expanded="isNotificationExpanded"
      :is-unread="isNotificationUnread"
      @toggle="toggleNotification"
      @closed="markNotificationsRead"
    />

    <ActivityDrawer
      v-model="activityDrawerVisible"
      :activities="activityRows"
      :profile="profile"
    />

    <TodoDrawer
      v-model="todoDrawerVisible"
      v-model:active-tab="activeTodoTab"
      :profile="profile"
      :todo-progress="todoProgress"
      :pending-todo-count="pendingTodoCount"
      :completed-todo-count="completedTodoCount"
      :expired-todo-count="expiredTodoCount"
      :pending-todo-items="pendingTodoItems"
      :completed-todo-items="completedTodoItems"
      :expired-todo-items="expiredTodoItems"
      :all-todo-items="allTodoItems"
      :selected-pending-todo-ids="selectedPendingTodoIds"
      :selected-completed-todo-ids="selectedCompletedTodoIds"
      :todo-form="todoForm"
      :editing-todo-id="editingTodoId"
      :is-todo-selected="isTodoSelected"
      :toggle-todo-selection="toggleTodoSelection"
      :complete-selected-todos="completeSelectedTodos"
      :restore-selected-todos="restoreSelectedTodos"
      :is-todo-expired="isTodoExpired"
      :is-todo-done="isTodoDone"
      :start-edit-todo="startEditTodo"
      :delete-todo="deleteTodo"
      :save-todo-form="saveTodoForm"
      :reset-todo-form="resetTodoForm"
    />
  </el-config-provider>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Bell,
  DataAnalysis,
  Document,
  EditPen,
  Files,
  MagicStick,
  Operation,
  Reading,
  Search,
  Setting,
  User,
} from '@element-plus/icons-vue'
import api from './api'
import AppSidebar from './components/AppSidebar.vue'
import LoginPanel from './components/LoginPanel.vue'
import MainContent from './components/MainContent.vue'
import NotificationDrawer from './components/NotificationDrawer.vue'
import ProfileDialog from './components/ProfileDialog.vue'
import TodoDrawer from './components/TodoDrawer.vue'
import UserDialog from './components/UserDialog.vue'
import ActivityDrawer from './components/ActivityDrawer.vue'
import {
  emptyGapStats,
  formatNumber,
  normalizeReportFormat,
  normalizeUserStats,
  progressValue,
  radarAxis,
  radarGrid,
  radarLabelPosition,
  radarPoints,
  radarPolygon,
  readJsonStorage,
  writeJsonStorage,
} from './utils/appUtils'

const NOTIFICATION_READ_KEY = 'research-agent-notification-read-map'
const SETTINGS_STORAGE_KEY = 'research-agent-settings'
const DEFAULT_SOURCES = Object.freeze(['pubmed', 'arxiv', 'crossref'])
const EMPTY_PROFILE = Object.freeze({
  name: '',
  role: '分析师',
  avatarText: '',
  avatarUrl: '',
  email: '',
  username: '',
  canManageSystem: false,
  canManageUsers: false,
})
const systemViews = ['users', 'logs', 'settings']
const adminOnlyViews = ['users', 'logs']

const isAuthenticated = ref(false)
const authMode = ref('login')
const loginForm = reactive({
  username: '',
  password: '',
})
const registerForm = reactive({
  name: '',
  username: '',
  password: '',
})
const currentView = ref('home')
const query = ref('')
const selectedSources = ref([...DEFAULT_SOURCES])
const loading = ref('')
const error = ref('')
const activeTab = ref('literature')
const trendRange = ref('2m')
const trendStats = ref({
  record_count: 0,
  buckets: [],
  series: [],
  is_real: true,
})
const trendLoading = ref(false)
const gapStats = ref(emptyGapStats())
const gapLoading = ref(false)
const task = ref(null)
const analysis = ref(null)
const legacyKeywordRefreshTaskId = ref(null)
const experiment = ref(null)
const drafts = ref([])
const report = ref(null)
const fullAgentStatus = ref('')
const systemLogRows = ref([])
const serverNotifications = ref([])
const activityRows = ref([])
const healthStatus = ref(null)
const expandedNotificationIds = ref([])
const notificationReadMap = ref(readJsonStorage(NOTIFICATION_READ_KEY, {}))
const allTodoItems = ref([])
const users = ref([])
const profileDialogVisible = ref(false)
const userDialogVisible = ref(false)
const notificationDrawerVisible = ref(false)
const activityDrawerVisible = ref(false)
const todoDrawerVisible = ref(false)
const activeTodoTab = ref('pending')
const selectedPendingTodoIds = ref([])
const selectedCompletedTodoIds = ref([])
const editingTodoId = ref('')
const todoForm = reactive({
  title: '',
  desc: '',
  dueDate: '',
  urgent: false,
})
const dashboard = ref(emptyDashboard())
const profile = reactive({ ...EMPTY_PROFILE })
const profileForm = reactive({ ...EMPTY_PROFILE })
const editingUserUsername = ref('')
const editingUserId = ref(null)
const editingUserRoleLocked = ref(false)
const userForm = reactive({
  name: '',
  username: '',
  password: '',
  role: '分析师',
  email: '',
})
const savedSettings = readJsonStorage(SETTINGS_STORAGE_KEY, {})
const settings = reactive({
  apiBase: api.baseUrl,
  requireEvidence: savedSettings.requireEvidence ?? true,
  reportFormat: savedSettings.reportFormat || 'Markdown',
})

const primaryNav = [{ label: '首页', icon: Reading, view: 'home' }]
const featureNav = [
  { label: '文献检索与摘要', icon: Search, view: 'literature' },
  { label: '研究空白与前沿探测', icon: MagicStick, view: 'gaps' },
  { label: '实验方案设计', icon: Operation, view: 'experiment' },
  { label: '论文写作辅助', icon: EditPen, view: 'writing' },
  { label: '可视化与报告生成', icon: Document, view: 'report' },
]
const systemNav = [
  { label: '用户与权限管理', icon: User, view: 'users' },
  { label: '系统日志', icon: Files, view: 'logs' },
  { label: '系统设置', icon: Setting, view: 'settings' },
]
const draftSections = [
  { key: 'abstract', label: '摘要' },
  { key: 'introduction', label: '引言' },
  { key: 'methods', label: '方法' },
  { key: 'results', label: '结果' },
  { key: 'discussion', label: '讨论' },
]
const currentUserStats = computed(() =>
  normalizeUserStats({
    literature: dashboard.value.stats.literature,
    summaries: dashboard.value.stats.summaries,
    experiments: dashboard.value.stats.experiments,
    reports: dashboard.value.stats.reports,
  })
)
const usageStats = computed(() => [
  { label: '检索文献', value: `${formatNumber(currentUserStats.value.literature)} 篇`, icon: Search, tone: 'blue' },
  { label: '生成摘要', value: `${formatNumber(currentUserStats.value.summaries)} 篇`, icon: Files, tone: 'orange' },
  { label: '实验方案', value: `${formatNumber(currentUserStats.value.experiments)} 个`, icon: Operation, tone: 'purple' },
  { label: '报告生成', value: `${formatNumber(currentUserStats.value.reports)} 份`, icon: Document, tone: 'red' },
])
const statCards = computed(() => [
  { label: '文献检索', value: `${formatNumber(currentUserStats.value.literature)} 篇`, change: '当前账号累计', changeTone: '', icon: Files, tone: 'blue' },
  { label: '摘要生成', value: `${formatNumber(currentUserStats.value.summaries)} 篇`, change: '当前账号累计', changeTone: '', icon: Reading, tone: 'green' },
  { label: '实验方案', value: `${formatNumber(currentUserStats.value.experiments)} 个`, change: '当前账号累计', changeTone: '', icon: Operation, tone: 'purple' },
  { label: '报告生成', value: `${formatNumber(currentUserStats.value.reports)} 份`, change: '当前账号累计', changeTone: '', icon: DataAnalysis, tone: 'orange' },
])
const trendSeries = computed(() => trendStats.value.series || [])
const chartMonths = computed(() => {
  const buckets = trendStats.value.buckets || []
  const lastIndex = Math.max(buckets.length - 1, 1)
  return buckets.map((item, index) => ({
    label: item.label,
    x: 54 + (index * 670) / lastIndex,
  }))
})
const trendMax = computed(() => Math.max(...trendSeries.value.flatMap((series) => series.values || []), 1))
const trendYAxisLabels = computed(() => [
  { label: trendMax.value, x: 18, y: 46 },
  { label: Math.ceil(trendMax.value * 0.75), x: 18, y: 96 },
  { label: Math.ceil(trendMax.value * 0.5), x: 18, y: 146 },
  { label: Math.ceil(trendMax.value * 0.25), x: 18, y: 196 },
  { label: 0, x: 36, y: 236 },
])
const trendEmptyText = computed(() =>
  trendLoading.value
    ? '正在加载真实统计数据'
    : trendStats.value.record_count
      ? '已有真实记录，但暂无可聚合的学科分类趋势'
      : '暂无真实趋势数据，请先完成一次真实文献检索'
)
const defaultRadarMetrics = [
  { key: 'heat', label: '研究热度', current: 0, average: 0 },
  { key: 'volume', label: '文献数量', current: 0, average: 0 },
  { key: 'innovation', label: '创新性', current: 0, average: 0 },
  { key: 'feasibility', label: '可行性', current: 0, average: 0 },
  { key: 'application', label: '应用价值', current: 0, average: 0 },
  { key: 'maturity', label: '研究成熟度', current: 0, average: 0 },
]
const radarMetrics = computed(() => (gapStats.value.metrics?.length ? gapStats.value.metrics : defaultRadarMetrics))
const radarCurrentValues = computed(() => radarMetrics.value.map((item) => Number(item.current || 0)))
const radarAverageValues = computed(() => radarMetrics.value.map((item) => Number(item.average || 0)))
const expiredTodoItems = computed(() => allTodoItems.value.filter((item) => isTodoExpired(item)))
const pendingTodoItems = computed(() => allTodoItems.value.filter((item) => item.status === 'pending'))
const completedTodoItems = computed(() => allTodoItems.value.filter((item) => item.status === 'completed'))
const todoItems = computed(() => pendingTodoItems.value.slice(0, 4))
const completedTodoCount = computed(() => completedTodoItems.value.length)
const pendingTodoCount = computed(() => pendingTodoItems.value.length)
const expiredTodoCount = computed(() => expiredTodoItems.value.length)
const actionableTodoCount = computed(() => pendingTodoCount.value + completedTodoCount.value)
const todoProgress = computed(() => (actionableTodoCount.value ? Math.round((completedTodoCount.value / actionableTodoCount.value) * 100) : 0))
const quickActions = [
  { label: '文献检索', desc: '跨库检索与摘要', icon: Search, tone: 'blue', action: () => navigateTo('literature') },
  { label: '研究空白探测', desc: '发现研究空白', icon: MagicStick, tone: 'purple', action: () => navigateTo('gaps') },
  { label: '实验方案设计', desc: '生成实验方案', icon: Operation, tone: 'cyan', action: () => navigateTo('experiment') },
  { label: '论文写作辅助', desc: '生成论文章节', icon: EditPen, tone: 'violet', action: () => navigateTo('writing') },
  { label: '报告生成', desc: '生成可视化报告', icon: Document, tone: 'orange', action: () => navigateTo('report') },
]
const roles = [
  { name: '管理员', desc: '管理用户、角色、系统设置、运行日志和部署配置。' },
  { name: '运营人员', desc: '查看系统设置，维护演示数据，协助生成汇报材料；系统日志仅管理员可查看。' },
  { name: '分析师', desc: '执行文献检索、热点分析、实验方案生成和报告导出，可查看系统设置；系统日志仅管理员可查看。' },
]
const systemStatus = computed(() => {
  const health = healthStatus.value
  if (!health) {
    return [
      { label: '服务运行状态', value: '待检测' },
      { label: '数据库连接', value: '待检测' },
      { label: 'Milvus 向量库', value: '待检测' },
      { label: 'AI 模型服务', value: '待检测' },
    ]
  }
  const llm = health.llm || {}
  const rag = health.rag || {}
  const milvusValue = !rag.use_milvus
    ? '未启用'
    : rag.reachable === false
      ? '未连接'
      : `已连接：${rag.collection || '默认集合'}`
  return [
    { label: '服务运行状态', value: health.ok === false ? '异常' : '正常' },
    { label: '数据库连接', value: health.runtime?.db_engine ? '正常' : health.ok === false ? '未知' : '已配置' },
    { label: 'Milvus 向量库', value: milvusValue },
    { label: 'AI 模型服务', value: llm.enabled ? `${llm.provider || 'LLM'} 已启用` : '未启用' },
  ]
})
const systemLoad = computed(() => (healthStatus.value?.ok === false ? 0 : Math.min(86, 20 + dashboard.value.stats.tasks * 2)))
const reportDownloadFormat = computed(() => normalizeReportFormat(settings.reportFormat))
const downloadUrl = computed(() =>
  report.value
    ? `${api.baseUrl}/reports/${report.value.id}/download/?format=${encodeURIComponent(reportDownloadFormat.value)}`
    : '#'
)
const hotspotMax = computed(() => Math.max(...(analysis.value?.hotspots || []).map((item) => item.count), 1))
const canManageSystem = computed(() => Boolean(profile.canManageSystem))
const canManageUsers = computed(() => Boolean(profile.canManageUsers))
const currentPage = computed(() => {
  const pages = {
    literature: { title: '文献检索与摘要', eyebrow: '跨库真实检索', description: '连接 PubMed、arXiv、Crossref，生成结构化综述与简明摘要。', icon: Search, actionText: '开始检索', primaryAction: runSearch },
    gaps: { title: '研究空白与前沿探测', eyebrow: '热点趋势分析', description: '基于文献数据识别研究热点、趋势和潜在研究空白。', icon: MagicStick, actionText: '运行分析', primaryAction: runAnalysis },
    experiment: { title: '实验方案设计', eyebrow: '从科学问题到技术路线', description: '围绕研究空白生成实验目标、技术路线、方法推荐和风险控制。', icon: Operation },
    writing: { title: '论文写作辅助', eyebrow: '学术章节草稿', description: '生成摘要、引言、方法、结果和讨论等论文草稿。', icon: EditPen },
    report: { title: '可视化与报告生成', eyebrow: '科研汇报材料', description: '整合检索、分析、实验和草稿，导出 Markdown、PDF 或 Word 研究报告。', icon: Document },
    users: { title: '用户与权限管理', eyebrow: '系统管理', description: '维护管理员、运营人员、分析师等角色和功能访问范围。', icon: User, actionText: '新增用户', primaryAction: openCreateUser },
    logs: { title: '系统日志', eyebrow: '审计追踪', description: '查看检索、分析、生成、导出等关键操作行为。', icon: Files, actionText: '刷新日志', primaryAction: refreshLogs },
    settings: { title: '系统设置', eyebrow: '运行配置', description: '配置默认数据源、报告格式和系统运行偏好。', icon: Setting, actionText: '保存设置', primaryAction: saveSettings },
  }
  return pages[currentView.value] || pages.literature
})
const recentActivities = computed(() => activityRows.value.slice(0, 4))
const iconMap = { Bell, DataAnalysis, Document, EditPen, Files, MagicStick, Operation, Search, User }
const notifications = computed(() => serverNotifications.value.map(decorateIconPayload))
const unreadNotificationCount = computed(() => notifications.value.filter((item) => isNotificationUnread(item.id)).length)
const logRows = computed(() => systemLogRows.value)

onMounted(() => {
  restoreSession()
  fetchTrendStatistics()
})

watch(trendRange, fetchTrendStatistics)
watch([currentView, analysis], () => {
  refreshLegacyKeywordAnalysis()
}, { immediate: true })

function canAccessSystemView(view) {
  if (!systemViews.includes(view)) return true
  if (adminOnlyViews.includes(view)) return canManageUsers.value
  return true
}

function normalizeRole(role) {
  return role && role !== '注册用户' ? role : '分析师'
}

function toggleNotification(id) {
  expandedNotificationIds.value = expandedNotificationIds.value.includes(id)
    ? expandedNotificationIds.value.filter((item) => item !== id)
    : [...expandedNotificationIds.value, id]
}

function isNotificationExpanded(id) {
  return expandedNotificationIds.value.includes(id)
}

function isNotificationUnread(id) {
  const readIds = notificationReadMap.value[profile.username] || []
  return !readIds.includes(id)
}

function markNotificationsRead() {
  if (!profile.username || !notifications.value.length) return
  notificationReadMap.value = {
    ...notificationReadMap.value,
    [profile.username]: notifications.value.map((item) => item.id),
  }
  writeJsonStorage(NOTIFICATION_READ_KEY, notificationReadMap.value)
  expandedNotificationIds.value = []
}

function openHelp() {
  ElMessage.info('提示：左侧标签可进入功能页面，顶部搜索框回车可一键生成完整研究流程。')
}

function handleAvatarFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  if (!file.type.startsWith('image/')) {
    ElMessage.warning('请选择图片文件作为头像')
    event.target.value = ''
    return
  }
  if (file.size > 2 * 1024 * 1024) {
    ElMessage.warning('头像图片请控制在 2MB 以内')
    event.target.value = ''
    return
  }
  const reader = new FileReader()
  reader.onload = () => {
    profileForm.avatarUrl = String(reader.result || '')
    ElMessage.success('头像图片已导入，保存资料后生效')
  }
  reader.readAsDataURL(file)
  event.target.value = ''
}

function clearAvatarImage() {
  profileForm.avatarUrl = ''
  profileForm.avatarText = (profileForm.avatarText || profileForm.name.slice(0, 1) || '研').slice(0, 2)
}

async function refreshDashboard() {
  await runStep('refresh', async () => {
    const payload = await api.get('/dashboard/')
    dashboard.value = payload
  }, { silent: true })
}

async function fetchTrendStatistics() {
  trendLoading.value = true
  try {
    const payload = await api.get(`/statistics/trends/?range=${trendRange.value}`)
    trendStats.value = {
      record_count: payload.record_count || 0,
      buckets: payload.buckets || [],
      series: payload.series || [],
      is_real: payload.is_real !== false,
    }
  } catch (err) {
    trendStats.value = { record_count: 0, buckets: [], series: [], is_real: true }
  } finally {
    trendLoading.value = false
  }
}

async function fetchGapStatistics() {
  if (!task.value?.id) {
    gapStats.value = emptyGapStats()
    return
  }
  gapLoading.value = true
  try {
    const params = new URLSearchParams()
    params.set('task_id', task.value.id)
    const payload = await api.get(`/statistics/gaps/?${params.toString()}`)
    gapStats.value = {
      is_real: payload.is_real !== false,
      query: payload.query || '',
      record_count: payload.record_count || 0,
      field_record_count: payload.field_record_count || 0,
      research_area: payload.research_area || null,
      metrics: payload.metrics || [],
      current_values: payload.current_values || [],
      average_values: payload.average_values || [],
    }
  } catch (err) {
    gapStats.value = emptyGapStats()
  } finally {
    gapLoading.value = false
  }
}

async function runStep(name, callback, options = {}) {
  loading.value = name
  if (!options.silent) error.value = ''
  try {
    await callback()
  } catch (err) {
    if (!options.silent) error.value = err.message
  } finally {
    loading.value = ''
  }
}

function ensureSources() {
  if (!selectedSources.value.length) throw new Error('至少选择一个真实数据源')
}

function emptyDashboard() {
  return {
    stats: { tasks: 0, literature: 0, analyses: 0, summaries: 0, experiments: 0, reports: 0 },
    recent_tasks: [],
    source_distribution: [],
  }
}

function resetResearchWorkspace() {
  query.value = ''
  selectedSources.value = [...DEFAULT_SOURCES]
  loading.value = ''
  error.value = ''
  activeTab.value = 'literature'
  trendRange.value = '2m'
  trendStats.value = {
    record_count: 0,
    buckets: [],
    series: [],
    is_real: true,
  }
  trendLoading.value = false
  gapStats.value = emptyGapStats()
  gapLoading.value = false
  task.value = null
  analysis.value = null
  legacyKeywordRefreshTaskId.value = null
  experiment.value = null
  drafts.value = []
  report.value = null
  fullAgentStatus.value = ''
  dashboard.value = emptyDashboard()
}

function linePoints(values) {
  const xStart = 54
  const xGap = values.length > 1 ? 670 / (values.length - 1) : 0
  const yBottom = 232
  const yHeight = 190
  const maxValue = trendMax.value || 1
  return values
    .map((value, index) => {
      const x = xStart + index * xGap
      const y = yBottom - (Math.min(value, maxValue) / maxValue) * yHeight
      return `${x},${y}`
    })
    .join(' ')
}

function decorateIconPayload(item = {}) {
  return {
    ...item,
    icon: iconMap[item.icon] || Bell,
  }
}

async function loadAuthenticatedContext() {
  await Promise.all([
    fetchHealthStatus(),
    refreshDashboard(),
    fetchTodos(),
    refreshActivityData(),
    fetchNotifications(),
    fetchTrendStatistics(),
  ])
  if (canManageUsers.value) {
    await Promise.all([fetchUsers(), refreshLogs({ silent: true })])
  } else {
    users.value = []
    systemLogRows.value = []
  }
}

async function fetchHealthStatus() {
  try {
    healthStatus.value = await api.get('/health/')
  } catch (err) {
    healthStatus.value = { ok: false, error: err.message || '健康检查失败' }
  }
}

function applyAccount(account, options = {}) {
  const displayName = account.name || account.username || ''
  const nextProfile = {
    name: displayName,
    role: normalizeRole(account.role),
    avatarText: account.avatarText || displayName.slice(0, 1) || '研',
    avatarUrl: account.avatarUrl || '',
    email: account.email || '',
    username: account.username || '',
    canManageSystem: Boolean(account.canManageSystem),
    canManageUsers: Boolean(account.canManageUsers),
  }
  Object.assign(profile, nextProfile)
  Object.assign(profileForm, nextProfile)
  isAuthenticated.value = true
  if (!options.keepView) currentView.value = 'home'
  error.value = ''
  expandedNotificationIds.value = []
}

async function ensureAuthenticatedSession() {
  if (!isAuthenticated.value) {
    throw new Error('请先登录后再使用检索功能')
  }
  const payload = await api.get('/auth/me/')
  if (!payload.user) {
    clearAuthenticatedState()
    throw new Error('登录状态已失效，请重新登录')
  }
  api.setAuthToken(payload.auth_token || '')
  applyAccount(payload.user, { keepView: true })
  return payload.user
}

async function login() {
  const username = loginForm.username.trim()
  const password = loginForm.password
  if (!username || !password) {
    ElMessage.warning('请输入账号和密码')
    return
  }
  loading.value = 'login'
  try {
    const payload = await api.post('/auth/login/', { username, password })
    api.setAuthToken(payload.auth_token || '')
    applyAccount(payload.user)
    await loadAuthenticatedContext()
    ElMessage.success(`欢迎回来，${profile.name}`)
  } catch (err) {
    ElMessage.error(err.message || '登录失败')
  } finally {
    loading.value = ''
  }
}

async function register() {
  const name = registerForm.name.trim()
  const username = registerForm.username.trim()
  const password = registerForm.password
  if (!name || !username || !password) {
    ElMessage.warning('请填写姓名、账号和密码')
    return
  }
  if (password.length < 6) {
    ElMessage.warning('密码至少需要 6 位')
    return
  }
  loading.value = 'register'
  try {
    const payload = await api.post('/auth/register/', { name, username, password })
    api.setAuthToken(payload.auth_token || '')
    applyAccount(payload.user)
    await loadAuthenticatedContext()
    registerForm.name = ''
    registerForm.username = ''
    registerForm.password = ''
    ElMessage.success('注册成功，已进入核心功能工作台')
  } catch (err) {
    ElMessage.error(err.message || '注册失败')
  } finally {
    loading.value = ''
  }
}

async function restoreSession() {
  loading.value = 'session'
  try {
    const payload = await api.get('/auth/me/')
    if (payload.user) {
      api.setAuthToken(payload.auth_token || '')
      applyAccount(payload.user)
      await loadAuthenticatedContext()
    } else {
      clearAuthenticatedState()
    }
  } catch {
    clearAuthenticatedState()
  } finally {
    loading.value = ''
  }
}

function clearAuthenticatedState() {
  isAuthenticated.value = false
  api.clearAuthToken()
  resetResearchWorkspace()
  users.value = []
  systemLogRows.value = []
  activityRows.value = []
  serverNotifications.value = []
  allTodoItems.value = []
  healthStatus.value = null
  currentView.value = 'home'
  Object.assign(profile, EMPTY_PROFILE)
  Object.assign(profileForm, profile)
}

async function navigateTo(view) {
  if (systemViews.includes(view) && !canAccessSystemView(view)) {
    const message =
      view === 'users'
        ? '只有管理员可以进入用户与权限管理。'
        : view === 'logs'
          ? '只有管理员可以查看系统日志。'
          : '当前账号不能访问该系统管理页面。'
    error.value = message
    ElMessage.warning(message)
    return
  }
  currentView.value = view
  error.value = ''
  if (view === 'users') await fetchUsers()
  if (view === 'logs') await refreshLogs({ silent: true })
  if (view === 'settings' || view === 'home') await fetchHealthStatus()
}

function resetUserForm() {
  editingUserUsername.value = ''
  editingUserId.value = null
  editingUserRoleLocked.value = false
  userForm.name = ''
  userForm.username = ''
  userForm.password = ''
  userForm.role = '分析师'
  userForm.email = ''
}

function openCreateUser() {
  if (!canManageUsers.value) {
    ElMessage.warning('只有管理员可以维护用户名单')
    return
  }
  resetUserForm()
  userDialogVisible.value = true
}

function openEditUser(row) {
  if (!canManageUsers.value) {
    ElMessage.warning('只有管理员可以修改用户权限')
    return
  }
  editingUserId.value = row.id
  editingUserUsername.value = row.username
  editingUserRoleLocked.value = Boolean(row.roleLocked)
  userForm.name = row.name
  userForm.username = row.username
  userForm.password = ''
  userForm.role = normalizeRole(row.role)
  userForm.email = row.email || ''
  userDialogVisible.value = true
}

async function saveManagedUser() {
  if (!canManageUsers.value) {
    ElMessage.warning('只有管理员可以保存用户权限')
    return
  }
  const body = {
    name: userForm.name.trim(),
    username: userForm.username.trim(),
    password: userForm.password.trim(),
    role: normalizeRole(userForm.role),
    email: userForm.email.trim(),
  }
  if (!body.name || !body.username) {
    ElMessage.warning('请填写姓名和账号')
    return
  }
  if (!editingUserId.value && body.password.length < 6) {
    ElMessage.warning('新增用户密码至少需要 6 位')
    return
  }
  try {
    if (editingUserId.value) {
      await api.patch(`/users/${editingUserId.value}/`, body)
      ElMessage.success('用户权限已更新')
    } else {
      await api.post('/users/', body)
      ElMessage.success('用户已新增')
    }
    userDialogVisible.value = false
    resetUserForm()
    await fetchUsers()
    await refreshLogs({ silent: true })
  } catch (err) {
    ElMessage.error(err.message || '保存用户失败')
  }
}

async function deleteManagedUser(row) {
  if (!canManageUsers.value) {
    ElMessage.warning('只有管理员可以删除用户')
    return
  }
  if (row.deleteLocked) {
    ElMessage.warning('该管理员账号不能删除')
    return
  }
  try {
    await api.delete(`/users/${row.id}/`)
    await fetchUsers()
    await refreshLogs({ silent: true })
    ElMessage.success('用户已删除')
  } catch (err) {
    ElMessage.error(err.message || '删除用户失败')
  }
}

async function handleProfileCommand(command) {
  if (command === 'profile' || command === 'avatar') {
    Object.assign(profileForm, profile)
    profileDialogVisible.value = true
  } else if (command === 'logout') {
    try {
      await api.post('/auth/logout/', {})
    } finally {
      clearAuthenticatedState()
      loginForm.password = ''
      ElMessage.info('已退出登录')
    }
  }
}

async function saveProfile() {
  const body = {
    name: profileForm.name || profile.name,
    email: profileForm.email || '',
    avatarText: (profileForm.avatarText || profileForm.name?.slice(0, 1) || '研').slice(0, 2),
    avatarUrl: profileForm.avatarUrl || '',
  }
  try {
    const payload = await api.patch('/profile/', body)
    applyAccount(payload.user)
    await fetchNotifications()
    profileDialogVisible.value = false
    ElMessage.success('个人资料已更新')
  } catch (err) {
    ElMessage.error(err.message || '保存个人资料失败')
  }
}

async function refreshLogs(options = {}) {
  if (!canManageUsers.value) {
    if (!options.silent) ElMessage.warning('只有管理员可以查看和刷新系统日志')
    return
  }
  loading.value = options.silent ? loading.value : 'refresh'
  try {
    const payload = await api.get('/logs/')
    systemLogRows.value = (payload.logs || []).map(decorateIconPayload)
    if (!options.silent) ElMessage.success('系统日志已刷新')
  } catch (err) {
    if (!options.silent) ElMessage.error(err.message || '刷新日志失败')
  } finally {
    if (!options.silent) loading.value = ''
  }
}

async function fetchUsers() {
  if (!canManageUsers.value) {
    users.value = []
    return
  }
  const payload = await api.get('/users/')
  users.value = payload.users || []
}

async function refreshActivityData() {
  if (!isAuthenticated.value) return
  const payload = await api.get('/activity/')
  activityRows.value = (payload.activities || []).map(decorateIconPayload)
}

async function fetchNotifications() {
  if (!isAuthenticated.value) return
  const payload = await api.get('/notifications/')
  serverNotifications.value = payload.notifications || []
}

async function fetchTodos() {
  if (!isAuthenticated.value) return
  const payload = await api.get('/todos/')
  allTodoItems.value = payload.todos || []
}

async function openNotificationDrawer() {
  notificationDrawerVisible.value = true
  try {
    await fetchNotifications()
  } catch (err) {
    ElMessage.warning(err.message || '通知刷新失败')
  }
}

async function openActivityDrawer() {
  await refreshActivityData()
  activityDrawerVisible.value = true
}

async function openTodoDrawer() {
  await fetchTodos()
  activeTodoTab.value = pendingTodoCount.value ? 'pending' : expiredTodoCount.value ? 'expired' : completedTodoCount.value ? 'completed' : 'edit'
  selectedPendingTodoIds.value = []
  selectedCompletedTodoIds.value = []
  resetTodoForm()
  todoDrawerVisible.value = true
}

function todoDueDate(item) {
  return item.dueDate || item.time?.match(/\d{4}-\d{2}-\d{2}/)?.[0] || ''
}

function isTodoExpired(item) {
  return item.status === 'expired'
}

function isTodoDone(id) {
  return allTodoItems.value.some((item) => item.id === id && item.status === 'completed')
}

async function toggleTodo(id) {
  const item = allTodoItems.value.find((todo) => todo.id === id)
  if (!item || isTodoExpired(item)) return
  await updateTodoStatus(id, isTodoDone(id) ? 'pending' : 'completed')
}

function isTodoSelected(type, id) {
  const source = type === 'completed' ? selectedCompletedTodoIds.value : selectedPendingTodoIds.value
  return source.includes(id)
}

function toggleTodoSelection(type, id) {
  const target = type === 'completed' ? selectedCompletedTodoIds : selectedPendingTodoIds
  target.value = target.value.includes(id) ? target.value.filter((item) => item !== id) : [...target.value, id]
}

async function completeSelectedTodos() {
  if (!selectedPendingTodoIds.value.length) {
    ElMessage.warning('请先勾选要完成的待办')
    return
  }
  await Promise.all(selectedPendingTodoIds.value.map((id) => updateTodoStatus(id, 'completed', false)))
  selectedPendingTodoIds.value = []
  await fetchTodos()
  ElMessage.success('已标记为完成')
}

async function restoreSelectedTodos() {
  if (!selectedCompletedTodoIds.value.length) {
    ElMessage.warning('请先勾选要恢复的待办')
    return
  }
  await Promise.all(selectedCompletedTodoIds.value.map((id) => updateTodoStatus(id, 'pending', false)))
  selectedCompletedTodoIds.value = []
  await fetchTodos()
  ElMessage.success('已恢复为未完成')
}

async function updateTodoStatus(id, status, refresh = true) {
  try {
    const payload = await api.patch(`/todos/${id}/`, { status })
    upsertTodo(payload.todo)
    if (refresh) {
      await Promise.all([fetchTodos(), refreshActivityData(), fetchNotifications()])
      ElMessage.success(status === 'completed' ? '已标记为完成' : '已恢复为未完成')
    }
  } catch (err) {
    ElMessage.error(err.message || '更新待办失败')
  }
}

function upsertTodo(todo) {
  if (!todo) return
  allTodoItems.value = allTodoItems.value.some((item) => item.id === todo.id)
    ? allTodoItems.value.map((item) => (item.id === todo.id ? todo : item))
    : [todo, ...allTodoItems.value]
}

function resetTodoForm() {
  editingTodoId.value = ''
  todoForm.title = ''
  todoForm.desc = ''
  todoForm.dueDate = ''
  todoForm.urgent = false
}

async function saveTodoForm() {
  const title = todoForm.title.trim()
  const desc = todoForm.desc.trim()
  if (!title || !desc || !todoForm.dueDate) {
    ElMessage.warning('请填写标题、说明和到期日期')
    return
  }
  const body = { title, desc, dueDate: todoForm.dueDate, urgent: todoForm.urgent }
  try {
    if (editingTodoId.value) {
      const payload = await api.patch(`/todos/${editingTodoId.value}/`, body)
      upsertTodo(payload.todo)
      ElMessage.success('待办已修改')
    } else {
      const payload = await api.post('/todos/', body)
      upsertTodo(payload.todo)
      ElMessage.success('待办已添加')
    }
    await Promise.all([fetchTodos(), refreshActivityData(), fetchNotifications()])
    resetTodoForm()
  } catch (err) {
    ElMessage.error(err.message || '保存待办失败')
  }
}

function startEditTodo(item) {
  editingTodoId.value = item.id
  todoForm.title = item.title
  todoForm.desc = item.desc
  todoForm.dueDate = todoDueDate(item)
  todoForm.urgent = Boolean(item.urgent)
  activeTodoTab.value = 'edit'
}

async function deleteTodo(id) {
  try {
    await api.delete(`/todos/${id}/`)
    allTodoItems.value = allTodoItems.value.filter((todo) => todo.id !== id)
    selectedPendingTodoIds.value = selectedPendingTodoIds.value.filter((itemId) => itemId !== id)
    selectedCompletedTodoIds.value = selectedCompletedTodoIds.value.filter((itemId) => itemId !== id)
    if (editingTodoId.value === id) resetTodoForm()
    await Promise.all([refreshActivityData(), fetchNotifications()])
    ElMessage.success('待办已删除')
  } catch (err) {
    ElMessage.error(err.message || '删除待办失败')
  }
}

async function runSearch() {
  currentView.value = 'literature'
  await runStep('search', async () => {
    await ensureAuthenticatedSession()
    ensureSources()
    gapStats.value = emptyGapStats()
    legacyKeywordRefreshTaskId.value = null
    const payload = await api.post('/literature/search/', {
      query: query.value,
      sources: selectedSources.value,
      limit: 9,
    })
    task.value = payload.task
    analysis.value = null
    experiment.value = null
    drafts.value = []
    report.value = null
    activeTab.value = 'literature'
    await Promise.all([refreshDashboard(), fetchTrendStatistics(), refreshActivityData(), fetchNotifications()])
    await fetchGapStatistics()
    ElMessage.success('真实文献检索完成')
  })
}

async function runAnalysis() {
  if (!task.value) await runSearch()
  if (!task.value) return
  currentView.value = currentView.value === 'home' ? 'home' : 'gaps'
  await runStep('analysis', async () => {
    await ensureAuthenticatedSession()
    const payload = await api.post('/analysis/', { task_id: task.value.id })
    analysis.value = payload.analysis
    if (!isLegacyKeywordAnalysis(analysis.value)) {
      legacyKeywordRefreshTaskId.value = null
    }
    activeTab.value = 'gaps'
    await Promise.all([refreshDashboard(), refreshActivityData(), fetchNotifications()])
    ElMessage.success('研究热点与空白分析完成')
  })
}

async function generateExperiment() {
  if (!analysis.value) await runAnalysis()
  if (!analysis.value) return
  currentView.value = currentView.value === 'home' ? 'home' : 'experiment'
  await runStep('experiment', async () => {
    await ensureAuthenticatedSession()
    const question = analysis.value.gaps?.[0]?.suggested_question || query.value
    const payload = await api.post('/experiment/', {
      analysis_id: analysis.value.id,
      question,
    })
    experiment.value = payload.experiment
    activeTab.value = 'report'
    await Promise.all([refreshDashboard(), refreshActivityData(), fetchNotifications()])
    ElMessage.success('实验方案已生成')
  })
}

async function generateDraft(section) {
  if (!experiment.value) await generateExperiment()
  if (!experiment.value) return
  currentView.value = 'writing'
  await runStep(`writing-${section}`, async () => {
    await ensureAuthenticatedSession()
    const payload = await api.post('/writing/', {
      experiment_id: experiment.value.id,
      section,
    })
    drafts.value = [...drafts.value, payload.draft]
    await Promise.all([refreshActivityData(), fetchNotifications()])
    ElMessage.success(`${draftSections.find((item) => item.key === section)?.label || '章节'}草稿已生成`)
  })
}

async function generateAllDrafts() {
  if (!experiment.value) await generateExperiment()
  if (!experiment.value) return
  currentView.value = currentView.value === 'home' ? 'home' : 'writing'
  const sections = ['abstract', 'introduction', 'methods', 'results', 'discussion']
  await runStep('writing', async () => {
    await ensureAuthenticatedSession()
    const generated = []
    for (const section of sections) {
      const payload = await api.post('/writing/', {
        experiment_id: experiment.value.id,
        section,
      })
      generated.push(payload.draft)
    }
    drafts.value = generated
    await Promise.all([refreshActivityData(), fetchNotifications()])
    ElMessage.success('论文章节草稿已生成')
  })
}

async function generateReport() {
  if (!task.value) await runSearch()
  if (!analysis.value) await runAnalysis()
  if (!experiment.value) await generateExperiment()
  if (!task.value) return
  currentView.value = currentView.value === 'home' ? 'home' : 'report'
  await runStep('report', async () => {
    await ensureAuthenticatedSession()
    const payload = await api.post('/reports/', {
      task_id: task.value.id,
      experiment_id: experiment.value?.id,
    })
    report.value = payload.report
    activeTab.value = 'report'
    await Promise.all([refreshDashboard(), refreshActivityData(), fetchNotifications()])
    ElMessage.success('研究报告已生成')
  })
}

async function runFullAgent() {
  ensureSources()
  const topic = query.value.trim()
  if (!topic) {
    ElMessage.warning('请输入研究主题')
    return
  }
  if (fullAgentStatus.value) return

  const sections = ['abstract', 'introduction', 'methods', 'results', 'discussion']
  const generatedDrafts = []
  legacyKeywordRefreshTaskId.value = null
  gapStats.value = emptyGapStats()
  error.value = ''
  task.value = null
  analysis.value = null
  experiment.value = null
  drafts.value = []
  report.value = null

  try {
    currentView.value = 'home'
    await ensureAuthenticatedSession()
    await runPipelineStep('search', '第 1/5 步：正在检索真实文献并生成 RAG 综述...', async () => {
      const payload = await api.post('/literature/search/', {
        query: topic,
        sources: selectedSources.value,
        limit: 9,
      })
      task.value = payload.task
      activeTab.value = 'literature'
      await Promise.all([refreshDashboard(), fetchTrendStatistics(), refreshActivityData(), fetchNotifications()])
      await fetchGapStatistics()
    })

    await pauseBetweenAgentSteps()
    await runPipelineStep('analysis', '第 2/5 步：正在逐篇抽取 LLM 主题词并分析研究空白...', async () => {
      const payload = await api.post('/analysis/', { task_id: task.value.id })
      analysis.value = payload.analysis
      if (!isLegacyKeywordAnalysis(analysis.value)) legacyKeywordRefreshTaskId.value = null
      activeTab.value = 'gaps'
      await Promise.all([refreshDashboard(), refreshActivityData(), fetchNotifications()])
    })

    await pauseBetweenAgentSteps()
    await runPipelineStep('experiment', '第 3/5 步：正在基于研究空白生成实验方案...', async () => {
      const question = analysis.value?.gaps?.[0]?.suggested_question || topic
      const payload = await api.post('/experiment/', {
        analysis_id: analysis.value.id,
        question,
      })
      experiment.value = payload.experiment
      activeTab.value = 'report'
      await Promise.all([refreshDashboard(), refreshActivityData(), fetchNotifications()])
    })

    for (let index = 0; index < sections.length; index += 1) {
      const section = sections[index]
      const label = draftSections.find((item) => item.key === section)?.label || section
      await pauseBetweenAgentSteps()
      await runPipelineStep(
        'writing',
        `第 4/5 步：正在串行生成论文${label}草稿（${index + 1}/${sections.length}）...`,
        async () => {
          const payload = await api.post('/writing/', {
            experiment_id: experiment.value.id,
            section,
          })
          generatedDrafts.push(payload.draft)
          drafts.value = [...generatedDrafts]
          await Promise.all([refreshActivityData(), fetchNotifications()])
        },
      )
    }

    await pauseBetweenAgentSteps()
    await runPipelineStep('report', '第 5/5 步：正在整合文献、分析、方案和草稿生成研究报告...', async () => {
      const payload = await api.post('/reports/', {
        task_id: task.value.id,
        experiment_id: experiment.value.id,
      })
      report.value = payload.report
      activeTab.value = 'report'
      currentView.value = 'report'
      await Promise.all([refreshDashboard(), refreshActivityData(), fetchNotifications()])
    })

    fullAgentStatus.value = ''
    ElMessage.success('完整科研流程已按顺序生成完成')
  } catch (err) {
    error.value = err.message || '一键生成失败'
    ElMessage.error(error.value)
  } finally {
    fullAgentStatus.value = ''
    loading.value = ''
  }
}

async function runPipelineStep(name, status, callback) {
  loading.value = name
  fullAgentStatus.value = status
  await callback()
}

function pauseBetweenAgentSteps() {
  return new Promise((resolve) => window.setTimeout(resolve, 900))
}

async function refreshLegacyKeywordAnalysis() {
  if (currentView.value !== 'gaps' || !task.value?.id || !isLegacyKeywordAnalysis(analysis.value)) return
  if (loading.value || legacyKeywordRefreshTaskId.value === task.value.id) return
  legacyKeywordRefreshTaskId.value = task.value.id
  ElMessage.info('检测到旧版关键词统计，正在重新生成 AI 主题词')
  await runAnalysis()
}

function isLegacyKeywordAnalysis(item) {
  const hotspots = item?.hotspots || []
  if (!hotspots.length) return false
  return !hotspots.some((row) => ['llm_keywords', 'metadata_keywords'].includes(row?.generation))
}

function saveSettings() {
  writeJsonStorage(SETTINGS_STORAGE_KEY, {
    requireEvidence: settings.requireEvidence,
    reportFormat: settings.reportFormat,
  })
  ElMessage.success('系统设置已保存到当前会话')
}
</script>

