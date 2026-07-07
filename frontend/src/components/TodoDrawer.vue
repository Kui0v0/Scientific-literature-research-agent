<template>
  <el-drawer v-model="visible" title="我的待办事项" size="460px">
    <div class="todo-summary">
      <strong>{{ profile.name }}的待办</strong>
      <span>{{ pendingTodoCount }} 项待完成 / {{ completedTodoCount }} 项已完成 / {{ expiredTodoCount }} 项已过期</span>
      <el-progress :percentage="todoProgress" :show-text="false" />
    </div>
    <el-tabs v-model="activeTabProxy" class="todo-tabs">
      <el-tab-pane :label="`待完成 ${pendingTodoCount}`" name="pending">
        <div v-if="pendingTodoItems.length" class="todo-drawer-list">
          <div
            v-for="item in pendingTodoItems"
            :key="item.id"
            :class="['todo-detail-row', { selected: isTodoSelected('pending', item.id) }]"
          >
            <el-checkbox :model-value="isTodoSelected('pending', item.id)" @change="toggleTodoSelection('pending', item.id)" />
            <span>
              <strong>{{ item.title }}</strong>
              <small>{{ item.desc }}</small>
            </span>
            <em :class="{ urgent: item.urgent }">{{ item.time }}</em>
          </div>
          <div class="todo-batch-actions">
            <el-button type="primary" :disabled="!selectedPendingTodoIds.length" @click="completeSelectedTodos">已完成</el-button>
          </div>
        </div>
        <el-empty v-else description="当前账号暂无未完成待办" />
      </el-tab-pane>

      <el-tab-pane :label="`已完成 ${completedTodoCount}`" name="completed">
        <div v-if="completedTodoItems.length" class="todo-drawer-list">
          <div
            v-for="item in completedTodoItems"
            :key="item.id"
            :class="['todo-detail-row', 'completed', { selected: isTodoSelected('completed', item.id) }]"
          >
            <el-checkbox :model-value="isTodoSelected('completed', item.id)" @change="toggleTodoSelection('completed', item.id)" />
            <span>
              <strong>{{ item.title }}</strong>
              <small>{{ item.desc }}</small>
            </span>
            <em>已完成</em>
          </div>
          <div class="todo-batch-actions">
            <el-button type="primary" :disabled="!selectedCompletedTodoIds.length" @click="restoreSelectedTodos">未完成</el-button>
          </div>
        </div>
        <el-empty v-else description="还没有已完成待办" />
      </el-tab-pane>

      <el-tab-pane :label="`已过期 ${expiredTodoCount}`" name="expired">
        <div v-if="expiredTodoItems.length" class="todo-drawer-list">
          <div v-for="item in expiredTodoItems" :key="item.id" class="todo-detail-row expired">
            <span class="todo-expired-mark">过期</span>
            <span>
              <strong>{{ item.title }}</strong>
              <small>{{ item.desc }}</small>
            </span>
            <em>{{ item.time }}</em>
          </div>
        </div>
        <el-empty v-else description="当前账号暂无已过期待办" />
      </el-tab-pane>

      <el-tab-pane label="编辑" name="edit">
        <el-form class="todo-editor" label-position="top">
          <el-form-item label="待办标题">
            <el-input v-model="todoForm.title" maxlength="30" show-word-limit placeholder="请输入待办标题" />
          </el-form-item>
          <el-form-item label="待办说明">
            <el-input v-model="todoForm.desc" maxlength="80" show-word-limit placeholder="请输入待办说明" />
          </el-form-item>
          <el-form-item label="到期日期">
            <el-date-picker v-model="todoForm.dueDate" type="date" value-format="YYYY-MM-DD" placeholder="选择到期日期" />
          </el-form-item>
          <el-form-item>
            <el-checkbox v-model="todoForm.urgent">标记为紧急</el-checkbox>
          </el-form-item>
          <div class="todo-editor-actions">
            <el-button type="primary" @click="saveTodoForm">{{ editingTodoId ? '保存修改' : '添加待办' }}</el-button>
            <el-button v-if="editingTodoId" @click="resetTodoForm">取消修改</el-button>
          </div>
        </el-form>
        <div v-if="allTodoItems.length" class="todo-edit-list">
          <div v-for="item in allTodoItems" :key="item.id" class="todo-edit-row">
            <span>
              <strong>{{ item.title }}</strong>
              <small>{{ item.desc }} · {{ item.time }}</small>
            </span>
            <el-tag v-if="isTodoExpired(item)" type="danger" effect="light">已过期</el-tag>
            <el-tag v-else-if="isTodoDone(item.id)" type="success" effect="light">已完成</el-tag>
            <el-tag v-else type="warning" effect="light">待完成</el-tag>
            <div>
              <el-button text type="primary" @click="startEditTodo(item)">修改</el-button>
              <el-button text type="danger" @click="deleteTodo(item.id)">删除</el-button>
            </div>
          </div>
        </div>
        <el-empty v-else description="暂无可编辑待办" />
      </el-tab-pane>
    </el-tabs>
  </el-drawer>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, required: true },
  activeTab: { type: String, required: true },
  profile: { type: Object, required: true },
  todoProgress: { type: Number, default: 0 },
  pendingTodoCount: { type: Number, default: 0 },
  completedTodoCount: { type: Number, default: 0 },
  expiredTodoCount: { type: Number, default: 0 },
  pendingTodoItems: { type: Array, default: () => [] },
  completedTodoItems: { type: Array, default: () => [] },
  expiredTodoItems: { type: Array, default: () => [] },
  allTodoItems: { type: Array, default: () => [] },
  selectedPendingTodoIds: { type: Array, default: () => [] },
  selectedCompletedTodoIds: { type: Array, default: () => [] },
  todoForm: { type: Object, required: true },
  editingTodoId: { type: String, default: '' },
  isTodoSelected: { type: Function, required: true },
  toggleTodoSelection: { type: Function, required: true },
  completeSelectedTodos: { type: Function, required: true },
  restoreSelectedTodos: { type: Function, required: true },
  isTodoExpired: { type: Function, required: true },
  isTodoDone: { type: Function, required: true },
  startEditTodo: { type: Function, required: true },
  deleteTodo: { type: Function, required: true },
  saveTodoForm: { type: Function, required: true },
  resetTodoForm: { type: Function, required: true },
})

const emit = defineEmits(['update:modelValue', 'update:activeTab'])

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

const activeTabProxy = computed({
  get: () => props.activeTab,
  set: (value) => emit('update:activeTab', value),
})
</script>
