<template>
      <main class="main">
        <AppTopbar
          v-model:query="queryModel"
          :profile="profile"
          :unread-notification-count="unreadNotificationCount"
          @run-full-agent="runFullAgent"
          @open-notifications="openNotificationDrawer"
          @open-help="openHelp"
          @profile-command="handleProfileCommand"
        />

        <el-alert
          v-if="error"
          class="status-alert"
          type="error"
          :title="error"
          show-icon
          :closable="true"
          @close="emit('clear-error')"
        />

        <template v-if="currentView === 'home'">
          <section class="hero">
            <div class="hero-copy">
              <h1>你好，{{ profile.name }}</h1>
              <p>欢迎使用科学文献研究智能体，开启高效的科研之旅！</p>
              <div class="hero-actions">
                <el-button type="primary" :loading="fullAgentRunning" @click="runFullAgent">
                  一键生成研究报告
                </el-button>
                <el-button :loading="loading === 'search'" @click="runSearch">仅检索文献</el-button>
              </div>
              <el-alert
                v-if="fullAgentStatus"
                class="pipeline-alert"
                type="info"
                :title="fullAgentStatus"
                show-icon
                :closable="false"
              />
            </div>
            <div class="hero-art" aria-hidden="true">
              <div class="platform"></div>
              <div class="glass-card center-card">
                <span></span>
                <i></i>
                <b></b>
              </div>
              <div class="glass-card mini-card one"></div>
              <div class="glass-card mini-card two"></div>
              <div class="glass-card mini-card three"></div>
              <div class="circuit-line a"></div>
              <div class="circuit-line b"></div>
            </div>
          </section>

          <section class="stats-grid">
            <article v-for="card in statCards" :key="card.label" class="stat-card">
              <div :class="['stat-icon', card.tone]">
                <el-icon><component :is="card.icon" /></el-icon>
              </div>
              <div>
                <span>{{ card.label }}</span>
                <strong>{{ card.value }}</strong>
                <p><em :class="card.changeTone">{{ card.change }}</em></p>
              </div>
            </article>
          </section>

          <section class="content-grid">
            <article class="panel trend-panel">
              <div class="panel-head">
                <h2>研究热点趋势</h2>
                <div class="trend-tools">
                  <el-tag :type="trendStats.record_count ? 'success' : 'info'" effect="light">
                    {{ trendStats.record_count ? `真实记录 ${trendStats.record_count} 篇` : '暂无真实统计' }}
                  </el-tag>
                  <el-select v-model="trendRangeModel" size="small" class="range-select">
                    <el-option label="近两个月" value="2m" />
                    <el-option label="近半年" value="6m" />
                  </el-select>
                </div>
              </div>
              <div v-if="trendSeries.length" class="legend">
                <span v-for="series in trendSeries" :key="series.name">
                  <i :style="{ background: series.color }"></i>{{ series.name }}
                </span>
              </div>
              <svg v-if="trendSeries.length" class="line-chart" viewBox="0 0 760 260" role="img" aria-label="研究热点趋势折线图">
                <g class="grid-lines">
                  <line v-for="y in [42, 92, 142, 192, 232]" :key="y" x1="54" :y1="y" x2="724" :y2="y" />
                </g>
                <g class="axis-labels">
                  <text v-for="item in trendYAxisLabels" :key="`${item.label}-${item.y}`" :x="item.x" :y="item.y">
                    {{ item.label }}
                  </text>
                </g>
                <polyline
                  v-for="series in trendSeries"
                  :key="series.name"
                  :points="linePoints(series.values)"
                  fill="none"
                  :stroke="series.color"
                  stroke-width="3"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
                <g class="month-labels">
                  <text v-for="item in chartMonths" :key="item.label" :x="item.x" y="254">{{ item.label }}</text>
                </g>
              </svg>
              <el-empty v-else class="trend-empty" :description="trendEmptyText" />
            </article>

            <article class="panel radar-panel">
              <div class="panel-head">
                <h2>研究空白识别</h2>
                <el-tag :type="gapStats.record_count ? 'success' : 'info'" effect="light">
                  {{ gapStats.record_count ? `${gapStats.research_area?.name || '相关领域'} · ${gapStats.record_count} 篇真实记录` : '暂无真实统计' }}
                </el-tag>
              </div>
              <svg v-if="gapStats.record_count" class="radar-chart" viewBox="0 0 300 280" role="img" aria-label="研究空白识别雷达图">
                <g class="radar-grid">
                  <polygon v-for="level in [0.25, 0.5, 0.75, 1]" :key="level" :points="radarGrid(level)" />
                  <line v-for="axis in 6" :key="axis" x1="150" y1="136" :x2="radarAxis(axis - 1).x" :y2="radarAxis(axis - 1).y" />
                </g>
                <polygon class="radar-average" :points="radarPolygon(radarAverageValues)" />
                <polygon class="radar-current" :points="radarPolygon(radarCurrentValues)" />
                <circle v-for="point in radarPoints(radarCurrentValues)" :key="`${point.x}-${point.y}`" :cx="point.x" :cy="point.y" r="4" />
                <text
                  v-for="(metric, index) in radarMetrics"
                  :key="metric.key"
                  :x="radarLabelPosition(index).x"
                  :y="radarLabelPosition(index).y"
                  :text-anchor="radarLabelPosition(index).anchor"
                >
                  {{ metric.label }}
                </text>
              </svg>
              <el-empty v-else class="trend-empty" :description="gapLoading ? '正在加载真实研究空白统计' : '暂无真实空白统计，请先完成一次真实文献检索'" />
              <div v-if="gapStats.record_count" class="radar-legend">
                <span><i></i>高潜力空白领域</span>
                <span><i class="dash"></i>同领域真实文献均值</span>
              </div>
            </article>

            <article class="panel todo-panel">
              <div class="panel-head">
                <h2>待办事项</h2>
              </div>
              <div class="todo-list">
                <label v-for="item in todoItems" :key="item.id" :class="['todo-row', { completed: isTodoDone(item.id) }]">
                  <el-checkbox :model-value="isTodoDone(item.id)" @change="toggleTodo(item.id)" />
                  <span>
                    <strong>{{ item.title }}</strong>
                    <small>{{ item.desc }}</small>
                  </span>
                  <em :class="{ urgent: item.urgent && !isTodoDone(item.id) }">
                    {{ isTodoDone(item.id) ? '已完成' : item.time }}
                  </em>
                </label>
              </div>
              <el-button class="wide-button" text bg type="primary" @click="openTodoDrawer">查看全部待办</el-button>
            </article>
          </section>

          <section class="bottom-grid">
            <article class="panel quick-panel">
              <div class="panel-head">
                <h2>快速开始</h2>
              </div>
              <div class="quick-actions">
                <button v-for="item in quickActions" :key="item.label" type="button" @click="item.action()">
                  <span :class="['quick-icon', item.tone]">
                    <el-icon><component :is="item.icon" /></el-icon>
                  </span>
                  <strong>{{ item.label }}</strong>
                  <small>{{ item.desc }}</small>
                </button>
              </div>
            </article>

            <article class="panel activity-panel">
              <div class="panel-head">
                <h2>最近活动</h2>
              </div>
              <div v-if="recentActivities.length" class="activity-list">
                <div v-for="item in recentActivities" :key="item.text" class="activity-row">
                  <span :class="['activity-dot', item.tone]">
                    <el-icon><component :is="item.icon" /></el-icon>
                  </span>
                  <p>{{ item.text }}</p>
                  <time>{{ item.time }}</time>
                </div>
              </div>
              <el-empty v-else class="compact-empty" description="暂无科研活动" />
              <el-button text type="primary" class="activity-link" @click="openActivityDrawer">查看全部活动</el-button>
            </article>

            <article class="panel status-panel">
              <div class="panel-head">
                <h2>系统状态</h2>
              </div>
              <div class="status-list">
                <div v-for="item in systemStatus" :key="item.label" class="status-row">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                </div>
              </div>
              <div class="load-meter">
                <span>系统负载</span>
                <b>{{ systemLoad }}%</b>
                <el-progress :percentage="systemLoad" :show-text="false" />
              </div>
            </article>
          </section>
        </template>

        <template v-else>
          <section class="page-hero">
            <div>
              <p>{{ currentPage.eyebrow }}</p>
              <h1>{{ currentPage.title }}</h1>
              <span>{{ currentPage.description }}</span>
            </div>
            <el-button
              v-if="currentView !== 'literature' && currentPage.primaryAction && currentPage.actionText"
              type="primary"
              :icon="currentPage.icon"
              @click="currentPage.primaryAction"
            >
              {{ currentPage.actionText }}
            </el-button>
          </section>

          <section v-if="currentView === 'literature'" class="page-grid single">
            <article class="panel">
              <div class="panel-head">
                <h2>跨库文献检索</h2>
                <el-tag type="success">PubMed / arXiv / Crossref</el-tag>
              </div>
              <el-form label-position="top" class="feature-form">
                <el-form-item label="研究主题或关键词">
                  <el-input v-model="queryModel" type="textarea" :rows="3" maxlength="240" show-word-limit />
                </el-form-item>
                <el-form-item label="真实数据源">
                  <el-checkbox-group v-model="selectedSourcesModel">
                    <el-checkbox-button label="pubmed">PubMed</el-checkbox-button>
                    <el-checkbox-button label="arxiv">arXiv</el-checkbox-button>
                    <el-checkbox-button label="crossref">Crossref</el-checkbox-button>
                  </el-checkbox-group>
                </el-form-item>
                <el-button type="primary" :loading="loading === 'search'" @click="runSearch">开始真实检索</el-button>
              </el-form>
            </article>

            <article class="panel">
              <div class="panel-head">
                <h2>检索结果与结构化综述</h2>
                <el-tag v-if="task" type="info">{{ task.result_count }} 篇真实记录</el-tag>
              </div>
              <el-table v-if="task" :data="task.records" stripe border>
                <el-table-column prop="source" label="来源" width="110" />
                <el-table-column label="题名" min-width="320">
                  <template #default="{ row }">
                    <a :href="row.url" target="_blank" rel="noreferrer">{{ row.title }}</a>
                    <div class="record-meta">
                      {{ row.published_at || '未知日期' }}
                      <template v-if="row.doi"> · DOI: {{ row.doi }}</template>
                      <template v-if="row.raw_metadata?.pmid"> · PMID: {{ row.raw_metadata.pmid }}</template>
                      <template v-if="row.raw_metadata?.arxiv_id"> · arXiv: {{ row.raw_metadata.arxiv_id }}</template>
                    </div>
                  </template>
                </el-table-column>
                <el-table-column label="关键词" min-width="220">
                  <template #default="{ row }">
                    <el-space wrap>
                      <el-tag v-for="keyword in row.keywords.slice(0, 4)" :key="keyword" size="small" effect="plain">
                        {{ keyword }}
                      </el-tag>
                    </el-space>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-else description="暂无检索结果" />
              <div v-if="task" class="generation-inline result-space">
                <el-tag size="small" :type="generationType(task)" effect="light">{{ generationLabel(task) }}</el-tag>
                <span>{{ generationDescription(task) }}</span>
              </div>
              <pre v-if="task" class="text-preview result-space">{{ task.review_text }}</pre>
            </article>
          </section>

          <section v-else-if="currentView === 'gaps'" class="page-grid">
            <article class="panel">
              <div class="panel-head">
                <h2>热点关键词</h2>
                <div class="result-actions">
                  <el-tag v-if="analysis" :type="keywordGenerationType(analysis)" effect="light">
                    {{ keywordGenerationLabel(analysis) }}
                  </el-tag>
                  <el-button :disabled="!task" :loading="loading === 'analysis'" @click="runAnalysis">重新分析</el-button>
                </div>
              </div>
              <el-empty v-if="!analysis" description="请先完成文献检索并点击分析" />
              <div v-else class="keyword-bars">
                <div v-for="item in analysis.hotspots.slice(0, 8)" :key="item.keyword" class="keyword-bar">
                  <div class="keyword-bar-head">
                    <span>{{ item.keyword }}</span>
                    <em>出现 {{ item.count }} 次</em>
                  </div>
                  <el-progress :percentage="progressValue(item.count, hotspotMax)" :stroke-width="10" :show-text="false" />
                </div>
              </div>
            </article>

            <article class="panel">
              <div class="panel-head">
                <h2>潜在研究空白</h2>
                <div class="result-actions">
                  <el-tag v-if="analysis" :type="generationType(analysis)" effect="light">
                    研究空白：{{ generationLabel(analysis) }}
                  </el-tag>
                  <el-button type="primary" :disabled="!analysis" @click="generateExperiment">转为实验方案</el-button>
                </div>
              </div>
              <div v-if="analysis" class="gap-list">
                <article v-for="gap in analysis.gaps" :key="gap.title" class="gap-row">
                  <strong>{{ gap.title }}</strong>
                  <div v-if="gap.category || gap.confidence || gap.evidence_count" class="gap-meta">
                    <el-tag size="small" :type="generationType(gap)" effect="light">{{ generationLabel(gap) }}</el-tag>
                    <el-tag v-if="gap.category" size="small" effect="plain">{{ gap.category }}</el-tag>
                    <el-tag v-if="gap.confidence" size="small" type="success" effect="light">可信度：{{ gap.confidence }}</el-tag>
                    <span v-if="gap.evidence_count">证据记录 {{ gap.evidence_count }} 条</span>
                  </div>
                  <p>{{ gap.rationale }}</p>
                  <el-tag type="warning" effect="light">{{ gap.suggested_question }}</el-tag>
                </article>
              </div>
              <el-empty v-else description="暂无研究空白" />
            </article>
          </section>

          <section v-else-if="currentView === 'experiment'" class="page-grid">
            <article class="panel experiment-plan-panel">
              <div class="panel-head">
                <h2>实验方案设计</h2>
                <div class="result-actions">
                  <el-tag v-if="experiment" :type="generationType(experiment)" effect="light">{{ generationLabel(experiment) }}</el-tag>
                  <el-button type="primary" :loading="loading === 'experiment'" @click="generateExperiment">RAG 生成方案</el-button>
                </div>
              </div>
              <el-empty v-if="!experiment" description="暂无实验方案" />
              <div v-else class="experiment-plan-body">
                <h3>{{ experiment.question }}</h3>
                <p class="summary">{{ experiment.goal }}</p>
                <el-steps class="experiment-route-steps" direction="vertical" :active="experiment.route.length" finish-status="success">
                  <el-step v-for="step in experiment.route" :key="step" :title="step" />
                </el-steps>
              </div>
            </article>

            <article class="panel experiment-method-panel">
              <div class="panel-head">
                <h2>方法推荐与风险控制</h2>
              </div>
              <el-empty v-if="!experiment" description="生成实验方案后展示推荐方法" />
              <div v-else class="experiment-method-body">
                <div class="method-grid">
                  <article v-for="method in experiment.methods" :key="method.name">
                    <strong>{{ method.name }}</strong>
                    <p>{{ method.reason }}</p>
                    <el-tag>{{ method.tool }}</el-tag>
                  </article>
                </div>
                <el-divider />
                <div class="gap-list">
                  <article v-for="risk in experiment.risks" :key="risk.risk" class="gap-row">
                    <strong>{{ risk.risk }}</strong>
                    <p>{{ risk.solution }}</p>
                  </article>
                </div>
              </div>
            </article>
          </section>

          <section v-else-if="currentView === 'writing'" class="page-grid single">
            <article class="panel">
              <div class="panel-head">
                <h2>论文写作辅助</h2>
                <div class="result-actions">
                  <el-tag v-if="drafts.length" :type="generationType(drafts[0])" effect="light">{{ generationLabel(drafts[0]) }}</el-tag>
                  <el-button type="primary" :loading="loading === 'writing'" @click="generateAllDrafts">RAG 生成全部章节</el-button>
                </div>
              </div>
              <el-alert type="info" show-icon :closable="false" title="优先调用 GPT + RAG，根据真实检索文献证据生成摘要、引言、方法、结果和讨论；未配置大模型时会显示规则兜底。" />
              <div class="draft-toolbar">
                <el-button v-for="section in draftSections" :key="section.key" :disabled="!experiment" @click="generateDraft(section.key)">
                  RAG 生成{{ section.label }}
                </el-button>
              </div>
              <el-collapse v-if="drafts.length" v-model="activeDraftPanels">
                <el-collapse-item
                  v-for="(draft, index) in drafts"
                  :key="draft.id || `${draft.section}-${index}`"
                  :title="draft.section"
                  :name="draftPanelName(draft, index)"
                >
                  <div class="generation-inline">
                    <el-tag size="small" :type="generationType(draft)" effect="light">{{ generationLabel(draft) }}</el-tag>
                    <span>{{ generationDescription(draft) }}</span>
                  </div>
                  <p class="draft-content">{{ draft.content }}</p>
                </el-collapse-item>
              </el-collapse>
              <el-empty v-else description="暂无章节草稿" />
            </article>
          </section>

          <section v-else-if="currentView === 'report'" class="page-grid single">
            <article class="panel">
              <div class="panel-head">
                <h2>可视化与报告生成</h2>
                <div class="result-actions">
                  <el-tag v-if="report" :type="generationType(report)" effect="light">{{ generationLabel(report) }}</el-tag>
                  <el-button type="primary" :loading="loading === 'report'" @click="generateReport">
                    {{ report ? '重新生成报告' : '生成报告' }}
                  </el-button>
                  <a v-if="report" :href="downloadUrl" target="_blank" rel="noreferrer" :download="downloadFilename">
                    <el-button :icon="Download">{{ downloadButtonLabel }}</el-button>
                  </a>
                </div>
              </div>
              <pre v-if="report" class="text-preview">{{ report.content_md }}</pre>
              <el-empty v-else description="暂无报告，请点击生成报告" />
            </article>
          </section>

          <section v-else-if="currentView === 'users'" class="page-grid">
            <article class="panel">
              <div class="panel-head">
                <h2>用户与权限管理</h2>
                <el-button type="primary" @click="openCreateUser">新增用户</el-button>
              </div>
              <el-table :data="users" stripe border>
                <el-table-column prop="name" label="用户" />
                <el-table-column prop="username" label="账号" />
                <el-table-column prop="role" label="角色" />
                <el-table-column prop="scope" label="权限范围" />
                <el-table-column prop="source" label="类型" width="100" />
                <el-table-column prop="status" label="状态">
                  <template #default="{ row }">
                    <el-tag type="success">{{ row.status }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="120">
                  <template #default="{ row }">
                    <div class="user-actions">
                      <el-button text type="primary" @click="openEditUser(row)">修改</el-button>
                      <el-button text type="danger" :disabled="row.deleteLocked" @click="deleteManagedUser(row)">删除</el-button>
                    </div>
                  </template>
                </el-table-column>
              </el-table>
            </article>

            <article class="panel">
              <div class="panel-head">
                <h2>角色权限说明</h2>
              </div>
              <div class="role-list">
                <article v-for="role in roles" :key="role.name">
                  <strong>{{ role.name }}</strong>
                  <p>{{ role.desc }}</p>
                </article>
              </div>
            </article>
          </section>

          <section v-else-if="currentView === 'logs'" class="page-grid single">
            <article class="panel">
              <div class="panel-head">
                <h2>系统日志</h2>
                <el-button :loading="loading === 'refresh'" @click="refreshLogs">刷新日志</el-button>
              </div>
              <el-table :data="logRows" stripe border>
                <el-table-column prop="time" label="时间" width="150" />
                <el-table-column prop="actor" label="用户" width="120" />
                <el-table-column prop="username" label="账号" width="150" />
                <el-table-column prop="action" label="操作" />
                <el-table-column prop="status" label="状态" width="100">
                  <template #default="{ row }">
                    <el-tag :type="row.status === '成功' ? 'success' : 'warning'">{{ row.status }}</el-tag>
                  </template>
                </el-table-column>
              </el-table>
            </article>
          </section>

          <section v-else-if="currentView === 'settings'" class="page-grid">
            <article class="panel">
              <div class="panel-head">
                <h2>系统设置</h2>
                <el-button type="primary" @click="saveSettings">保存设置</el-button>
              </div>
              <el-form label-position="top" class="feature-form">
                <el-form-item label="后端 API 地址">
                  <el-input v-model="settings.apiBase" />
                </el-form-item>
                <el-form-item label="默认检索源">
                  <el-checkbox-group v-model="selectedSourcesModel">
                    <el-checkbox-button label="pubmed">PubMed</el-checkbox-button>
                    <el-checkbox-button label="arxiv">arXiv</el-checkbox-button>
                    <el-checkbox-button label="crossref">Crossref</el-checkbox-button>
                  </el-checkbox-group>
                </el-form-item>
                <el-form-item label="生成策略">
                  <el-switch v-model="settings.requireEvidence" active-text="要求绑定文献证据" />
                </el-form-item>
                <el-form-item label="报告格式">
                  <el-radio-group v-model="settings.reportFormat">
                    <el-radio-button label="Markdown" />
                    <el-radio-button label="PDF" />
                    <el-radio-button label="Word" />
                  </el-radio-group>
                </el-form-item>
              </el-form>
            </article>

            <article class="panel">
              <div class="panel-head">
                <h2>服务状态</h2>
              </div>
              <div class="status-list">
                <div v-for="item in systemStatus" :key="item.label" class="status-row">
                  <span>{{ item.label }}</span>
                  <strong>{{ item.value }}</strong>
                </div>
              </div>
            </article>
          </section>
        </template>

        <footer class="footer">© 2026 科学文献研究智能体平台 | 基于 Python、Django、LangChain、Vue.js 构建</footer>
      </main>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Download } from '@element-plus/icons-vue'
import AppTopbar from './AppTopbar.vue'

const props = defineProps([
  'query',
  'profile',
  'unreadNotificationCount',
  'error',
  'currentView',
  'currentPage',
  'loading',
  'statCards',
  'trendStats',
  'trendRange',
  'trendSeries',
  'trendYAxisLabels',
  'chartMonths',
  'trendEmptyText',
  'gapStats',
  'gapLoading',
  'radarMetrics',
  'radarCurrentValues',
  'radarAverageValues',
  'todoItems',
  'quickActions',
  'recentActivities',
  'openActivityDrawer',
  'systemStatus',
  'systemLoad',
  'selectedSources',
  'task',
  'analysis',
  'hotspotMax',
  'experiment',
  'draftSections',
  'drafts',
  'report',
  'downloadUrl',
  'users',
  'roles',
  'logRows',
  'settings',
  'fullAgentStatus',
  'runFullAgent',
  'runSearch',
  'openNotificationDrawer',
  'openHelp',
  'handleProfileCommand',
  'linePoints',
  'radarGrid',
  'radarAxis',
  'radarPolygon',
  'radarPoints',
  'radarLabelPosition',
  'isTodoDone',
  'toggleTodo',
  'openTodoDrawer',
  'navigateTo',
  'runAnalysis',
  'progressValue',
  'generateExperiment',
  'generateAllDrafts',
  'generateDraft',
  'generateReport',
  'openCreateUser',
  'openEditUser',
  'deleteManagedUser',
  'refreshLogs',
  'saveSettings',
])

const emit = defineEmits(['update:query', 'update:trendRange', 'update:selectedSources', 'clear-error'])

const queryModel = computed({
  get: () => props.query,
  set: (value) => emit('update:query', value),
})

const trendRangeModel = computed({
  get: () => props.trendRange,
  set: (value) => emit('update:trendRange', value),
})

const selectedSourcesModel = computed({
  get: () => props.selectedSources || [],
  set: (value) => emit('update:selectedSources', value),
})

const downloadButtonLabel = computed(() => `下载${props.settings?.reportFormat || 'Markdown'}`)
const fullAgentRunning = computed(() => Boolean(props.fullAgentStatus))
const downloadFilename = computed(() => {
  const format = String(props.settings?.reportFormat || 'Markdown').toLowerCase()
  const extension = format === 'pdf' ? 'pdf' : format === 'word' ? 'docx' : 'md'
  return props.report ? `report-${props.report.id}.${extension}` : ''
})
const activeDraftPanels = ref([])

watch(
  () => props.drafts,
  (drafts) => {
    activeDraftPanels.value = (drafts || []).map((draft, index) => draftPanelName(draft, index))
  },
  { immediate: true, deep: true }
)

function draftPanelName(draft, index = 0) {
  return String(draft?.id ?? draft?.section ?? index)
}

function generationMode(item) {
  const text = [item?.content, item?.content_md, item?.review_text, item?.rationale, item?.summary].filter(Boolean).join(' ')
  if (/规则模板兜底/.test(text)) return 'rules'
  if (/\[R\d+\]|(DeepSeek|OpenAI|GPT|大模型)\s*\+\s*(?:Milvus\s+)?RAG/.test(text)) return 'llm_rag'
  const explicit = item?.generation_mode || item?.generation || item?.payload?.generation
  return explicit || 'rules'
}

function generationLabel(item) {
  if (generationMode(item) !== 'llm_rag') return '规则兜底'
  const text = [item?.content, item?.content_md, item?.review_text, item?.rationale, item?.summary].filter(Boolean).join(' ')
  if (/DeepSeek\s*\+\s*(?:Milvus\s+)?RAG/i.test(text)) return 'DeepSeek + RAG'
  if (/OpenAI\s*\+\s*(?:Milvus\s+)?RAG/i.test(text)) return 'OpenAI + RAG'
  return 'GPT + RAG'
}

function generationType(item) {
  return generationMode(item) === 'llm_rag' ? 'success' : 'warning'
}

function keywordGenerationMode(item) {
  const generations = (item?.hotspots || []).map((row) => row?.generation).filter(Boolean)
  if (generations.includes('llm_keywords')) return 'llm_keywords'
  if (generations.includes('metadata_keywords')) return 'metadata_keywords'
  return 'legacy_keywords'
}

function keywordGenerationLabel(item) {
  const mode = keywordGenerationMode(item)
  if (mode === 'llm_keywords') return 'AI 提取关键词'
  if (mode === 'metadata_keywords') return '元数据关键词'
  return '旧关键词统计'
}

function keywordGenerationType(item) {
  const mode = keywordGenerationMode(item)
  if (mode === 'llm_keywords') return 'success'
  if (mode === 'metadata_keywords') return 'warning'
  return 'info'
}

function generationDescription(item) {
  return generationMode(item) === 'llm_rag'
    ? '已基于真实检索文献证据包生成，正文中的 [R1] 等编号对应检索结果。'
    : '当前为规则模板兜底，通常是未配置大模型、请求超时或返回内容未通过校验。'
}
</script>
