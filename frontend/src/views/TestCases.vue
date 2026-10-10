<template>
  <div>
    <el-card shadow="never" class="mb16">
      <div class="toolbar">
        <el-button @click="router.back()">
          <el-icon><Back /></el-icon>返回
        </el-button>
        <div class="flex-1"></div>
        <el-select v-model="filters.priority" placeholder="用例等级" clearable class="filter">
          <el-option-group label="规范等级 L1~L4">
            <el-option v-for="p in ['L1', 'L2', 'L3', 'L4']" :key="p" :label="p" :value="p" />
          </el-option-group>
          <el-option-group label="历史等级 P0~P4">
            <el-option v-for="p in ['P0', 'P1', 'P2', 'P3', 'P4']" :key="p" :label="p" :value="p" />
          </el-option-group>
        </el-select>
        <el-select v-model="filters.status" placeholder="状态" clearable class="filter">
          <el-option label="草稿" value="draft" />
          <el-option label="已评审" value="reviewed" />
          <el-option label="已通过" value="approved" />
        </el-select>
        <el-select v-model="filters.module" placeholder="模块" clearable filterable class="filter" style="width: 150px">
          <el-option v-for="m in moduleOptions" :key="m" :label="m" :value="m" />
        </el-select>
        <el-select
          v-model="filters.task_id"
          placeholder="生成批次"
          clearable
          class="task-filter"
          @change="onTaskFilterChange"
        >
          <el-option v-for="t in taskOptions" :key="t.task_id" :label="taskLabel(t)" :value="t.task_id" />
        </el-select>
        <el-button type="primary" @click="loadData(true)">查询</el-button>
        <span v-if="selectedCount" class="selected-info">已选 {{ selectedCount }} 条</span>
        <el-button type="success" :disabled="!selectedCount" @click="handleBatchApprove">批量通过</el-button>
        <el-button type="warning" plain :disabled="!selectedCount" @click="handleBatchRegenerate">批量重生成</el-button>
        <el-button
          type="primary"
          plain
          :disabled="!filters.task_id"
          :loading="selfChecking"
          @click="handleSelfCheckByTask"
        >整批自查</el-button>
        <el-button type="primary" plain :disabled="!selectedCount" :loading="selfChecking" @click="handleSelfCheck(selectedIdsArr)">AI 自查</el-button>
        <el-button
          type="warning"
          plain
          :disabled="!filters.task_id && !selectedCount"
          :loading="dedupScanning"
          @click="handleDedupScan"
        >重复扫描</el-button>
        <el-button
          type="danger"
          plain
          :disabled="!filters.task_id && !selectedCount"
          :loading="dedupCleaning"
          @click="handleDedupCleanup"
        >一键清理重复</el-button>
        <el-button type="danger" plain :disabled="!selectedCount" @click="handleBatchDelete">批量删除</el-button>
        <el-button type="danger" :disabled="!selectedCount" @click="openScriptDialog">生成脚本</el-button>
        <el-dropdown :disabled="!selectedCount" @command="handleExport">
          <el-button type="warning">
            导出<el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="excel">导出 Excel</el-dropdown-item>
              <el-dropdown-item command="markdown">导出 Markdown</el-dropdown-item>
              <el-dropdown-item command="json">导出 JSON</el-dropdown-item>
              <el-dropdown-item command="xmind">导出 XMind</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-card>

    <el-table
      ref="tableRef"
      :data="list"
      row-key="id"
      v-loading="loading"
      border
      stripe
      @selection-change="handleSelectionChange"
      @select-all="handleSelectAll"
    >
      <el-table-column type="selection" width="45" reserve-selection />
      <el-table-column prop="case_no" label="用例编号" width="120" />
      <el-table-column prop="title" label="用例标题" min-width="200" show-overflow-tooltip />
      <el-table-column prop="module" label="模块" width="120" show-overflow-tooltip>
        <template #default="{ row }">
          <el-tag v-if="row.module" type="info" size="small" effect="plain">{{ row.module }}</el-tag>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="用例等级" width="90">
        <template #default="{ row }">
          <el-tag :type="priorityType[row.priority]" size="small">{{ row.priority }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="类型" width="100">
        <template #default="{ row }">{{ row.test_type }}</template>
      </el-table-column>
      <el-table-column label="来源" width="90">
        <template #default="{ row }">
          <el-tag :type="row.source === 'ai' ? 'warning' : row.source === 'ai_reviewed' ? 'success' : 'info'" size="small">
            {{ sourceMap[row.source] }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="statusType[row.status]" size="small">{{ statusMap[row.status] }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="AI反馈" width="100" align="center">
        <template #default="{ row }">
          <el-tooltip content="质量好" placement="top">
            <el-button
              link
              :type="row.feedback === 'good' ? 'success' : 'info'"
              :disabled="row.source !== 'ai'"
              @click="handleFeedback(row, 'good')"
            >👍</el-button>
          </el-tooltip>
          <el-tooltip content="质量差" placement="top">
            <el-button
              link
              :type="row.feedback === 'bad' ? 'danger' : 'info'"
              :disabled="row.source !== 'ai'"
              @click="handleFeedback(row, 'bad')"
            >👎</el-button>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="重复标记" width="100" align="center">
        <template #default="{ row }">
          <el-tooltip v-if="row.dup_group_no != null" placement="top" :show-after="200">
            <template #content>
              <div class="check-tip">
                被判定与同批其他用例语义重复（第 {{ row.dup_group_no }} 组）。建议每组只保留 1 条代表用例，
                其余可点上方「一键清理重复」批量处理。
              </div>
            </template>
            <el-tag type="danger" size="small" effect="dark" style="cursor: pointer">重复·组{{ row.dup_group_no }}</el-tag>
          </el-tooltip>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="AI自查" width="150" fixed="right">
        <template #default="{ row }">
          <el-tooltip v-if="row.ai_remark" placement="top" :show-after="200">
            <template #content>
              <div class="check-tip">{{ row.ai_remark }}</div>
            </template>
            <el-tag type="warning" size="small" effect="dark" style="cursor: pointer">
              {{ row.ai_remark.split('\n').length }} 处待复核
            </el-tag>
          </el-tooltip>
          <span v-else-if="row.ai_checked_at" class="check-ok">已自查</span>
          <span v-else>-</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="230" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDetail(row)">详情</el-button>
          <el-button v-if="row.source !== 'manual'" link type="warning" :loading="selfChecking" @click="handleSelfCheck([row.id], row)">自查</el-button>
          <el-button v-if="row.source === 'ai'" link type="warning" @click="handleRegenerate(row)">重生成</el-button>
          <el-button v-if="row.status === 'draft'" link type="success" @click="handleReview(row)">通过</el-button>
          <el-button v-if="row.status !== 'approved'" link type="danger" @click="openReject(row)">驳回</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      class="pagination"
      v-model:current-page="page"
      :page-size="pageSize"
      :total="total"
      layout="total, prev, pager, next"
      @current-change="loadData"
    />

    <!-- 用例详情 -->
    <el-dialog v-model="detailVisible" title="用例详情" width="780px">
      <template v-if="current">
        <!-- 查看模式 -->
        <template v-if="!editing">
          <div class="detail-title">{{ current.title }}</div>
          <div class="detail-meta">
            <el-tag size="small">{{ current.case_no }}</el-tag>
            <el-tag size="small" type="info" effect="plain">{{ current.module || '未分类' }}</el-tag>
            <el-tag size="small" :type="priorityType[current.priority]">{{ current.priority }}</el-tag>
            <el-tag size="small" type="info">{{ current.test_type }}</el-tag>
            <el-tag size="small" :type="statusType[current.status]">{{ statusMap[current.status] }}</el-tag>
          </div>
          <el-descriptions :column="1" border class="mt16">
            <el-descriptions-item label="前置条件">{{ current.preconditions || '-' }}</el-descriptions-item>
          </el-descriptions>
          <div class="step-title">测试步骤</div>
          <el-table :data="current.steps || []" border size="small">
            <el-table-column prop="step_no" label="#" width="50" />
            <el-table-column prop="action" label="操作" />
            <el-table-column prop="expected" label="预期" />
          </el-table>
          <div class="step-title">预期结果</div>
          <div class="expected-box">{{ current.expected_result }}</div>
          <div v-if="current.ai_remark" class="step-title">AI 自查备注</div>
          <div v-if="current.ai_remark" class="expected-box warn-box">{{ current.ai_remark }}</div>
          <div v-else-if="current.ai_checked_at" class="check-ok mt16">AI 自查未发现问题</div>
        </template>
        <!-- 编辑模式 -->
        <el-form v-else :model="editForm" label-width="90px">
          <el-form-item label="用例标题" required>
            <el-input v-model="editForm.title" />
          </el-form-item>
          <el-form-item label="模块">
            <el-select
              v-model="editForm.module"
              placeholder="选择或输入模块，如登录注册"
              filterable
              allow-create
              default-first-option
              clearable
              style="width: 100%"
            >
              <el-option v-for="m in moduleOptions" :key="m" :label="m" :value="m" />
            </el-select>
          </el-form-item>
          <el-form-item label="用例等级">
            <el-select v-model="editForm.priority" style="width: 140px">
              <el-option-group label="规范等级 L1~L4">
                <el-option v-for="p in ['L1', 'L2', 'L3', 'L4']" :key="p" :label="p" :value="p" />
              </el-option-group>
              <el-option-group label="历史等级 P0~P4">
                <el-option v-for="p in ['P0', 'P1', 'P2', 'P3', 'P4']" :key="p" :label="p" :value="p" />
              </el-option-group>
            </el-select>
          </el-form-item>
          <el-form-item label="测试类型">
            <el-input v-model="editForm.test_type" />
          </el-form-item>
          <el-form-item label="前置条件">
            <el-input v-model="editForm.preconditions" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item label="测试步骤">
            <el-table :data="editForm.steps" border size="small">
              <el-table-column label="#" width="50">
                <template #default="{ $index }">{{ $index + 1 }}</template>
              </el-table-column>
              <el-table-column label="操作">
                <template #default="{ row }">
                  <el-input v-model="row.action" placeholder="操作步骤" />
                </template>
              </el-table-column>
              <el-table-column label="预期">
                <template #default="{ row }">
                  <el-input v-model="row.expected" placeholder="该步骤预期" />
                </template>
              </el-table-column>
              <el-table-column width="60">
                <template #default="{ $index }">
                  <el-button link type="danger" @click="editForm.steps.splice($index, 1)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
            <el-button class="mt8" size="small" @click="addStep">+ 添加步骤</el-button>
          </el-form-item>
          <el-form-item label="预期结果">
            <el-input v-model="editForm.expected_result" type="textarea" :rows="3" />
          </el-form-item>
        </el-form>
      </template>
      <template #footer>
        <template v-if="editing">
          <el-button @click="cancelEdit">取消</el-button>
          <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
        </template>
        <template v-else>
          <el-button @click="detailVisible = false">关闭</el-button>
          <el-button type="warning" plain :loading="selfChecking" @click="handleSelfCheck([current.id], true)">AI 自查</el-button>
          <el-button type="warning" :loading="completing" @click="handleAutoComplete">AI 补全</el-button>
          <el-button type="primary" @click="startEdit">编辑</el-button>
        </template>
      </template>
    </el-dialog>

    <!-- 驳回弹窗 -->
    <el-dialog v-model="rejectVisible" title="驳回用例" width="440px">
      <el-input v-model="rejectComment" type="textarea" :rows="3" placeholder="请填写驳回原因（可选）" />
      <template #footer>
        <el-button @click="rejectVisible = false">取消</el-button>
        <el-button type="danger" :loading="rejecting" @click="confirmReject">确认驳回</el-button>
      </template>
    </el-dialog>

    <!-- 生成脚本 -->
    <ScriptGenerateDialog ref="scriptDialogRef" :project-id="projectId" :case-ids="selectedIdsArr" :case-count="selectedCount" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, ElLoading } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { testCaseApi } from '@/api'
import ScriptGenerateDialog from '@/components/ScriptGenerateDialog.vue'

const route = useRoute()
const router = useRouter()
const projectId = Number(route.params.id)

const list = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const filters = reactive({ priority: '', status: '', module: '', task_id: null as number | null })
const moduleOptions = ref<string[]>([])
const taskOptions = ref<any[]>([])

// ===== 跨页选中集合（id -> source），全选可覆盖当前查询条件下的全部用例 =====
const tableRef = ref<any>(null)
const selectedMap = ref<Map<number, string>>(new Map())
let skipSelectAllSync = false

const selectedIdsArr = computed(() => Array.from(selectedMap.value.keys()))
const selectedCount = computed(() => selectedMap.value.size)

const detailVisible = ref(false)
const current = ref<any>(null)
const editing = ref(false)
const saving = ref(false)
const completing = ref(false)
const selfChecking = ref(false)
const dedupScanning = ref(false)
const dedupCleaning = ref(false)
const scriptDialogRef = ref<InstanceType<typeof ScriptGenerateDialog> | null>(null)

const editForm = reactive({ title: '', priority: 'L2', test_type: '', preconditions: '', expected_result: '', steps: [] as any[] })

const rejectVisible = ref(false)
const rejecting = ref(false)
const rejectComment = ref('')
const rejectTarget = ref<any>(null)

const priorityType: Record<string, string> = {
  // 规范等级 L1~L4（《测试用例等级定义规范》）
  L1: 'danger', L2: 'warning', L3: 'primary', L4: 'info',
  // 历史等级 P0~P4（存量数据）
  P0: 'danger', P1: 'warning', P2: 'primary', P3: 'info', P4: 'info',
}
const sourceMap: Record<string, string> = { ai: 'AI生成', manual: '人工', ai_reviewed: 'AI审校' }
const statusMap: Record<string, string> = { draft: '草稿', reviewed: '已评审', approved: '已通过' }
const statusType: Record<string, string> = { draft: 'info', reviewed: 'success', approved: 'primary' }

const loadData = async (resetSelection = false) => {
  if (resetSelection) {
    selectedMap.value = new Map()
    tableRef.value?.clearSelection()
  }
  loading.value = true
  try {
    const data = await testCaseApi.list({
      project_id: projectId,
      page: page.value,
      page_size: pageSize.value,
      priority: filters.priority || undefined,
      status: filters.status || undefined,
      module: filters.module || undefined,
      task_id: filters.task_id || undefined,
    })
    list.value = data.list
    total.value = data.total
  } finally {
    loading.value = false
  }
}

// ===== 模块下拉数据 =====
const loadModules = async () => {
  try {
    const res: any = await testCaseApi.modules(projectId)
    moduleOptions.value = res?.modules ?? res?.data?.modules ?? []
  } catch (e: any) {
    // 模块列表加载失败不影响用例列表展示
  }
}

// ===== 生成批次下拉数据（第N次生成 + 用例数/自查进度） =====
const loadTasks = async () => {
  try {
    const res: any = await testCaseApi.tasks(projectId)
    taskOptions.value = res?.items ?? res?.data?.items ?? []
  } catch (e: any) {
    // 批次列表加载失败不影响用例列表展示
  }
}

const taskLabel = (t: any) => {
  const at = (t.created_at || '').toString().slice(5, 16).replace('T', ' ')
  const state = t.checked_count > 0
    ? t.flagged_count > 0
      ? ` · ${t.flagged_count}处待复核`
      : ' · 已自查'
    : ''
  return `第${t.seq}次 · ${t.task_no} · ${at} · ${t.case_count}条${state}`
}

const onTaskFilterChange = () => {
  loadData(true)
}

// ===== 跨页全选 =====
const collectAllIds = async () => {
  const res: any = await testCaseApi.listIds({
    project_id: projectId,
    priority: filters.priority || undefined,
    status: filters.status || undefined,
    module: filters.module || undefined,
    task_id: filters.task_id || undefined,
  })
  const items: { id: number; source: string }[] = res?.items ?? []
  const map = new Map<number, string>()
  for (const it of items) map.set(it.id, it.source)
  selectedMap.value = map
  return map.size
}

const handleSelectAll = async (rows: any[]) => {
  if (rows.length) {
    // 勾选表头全选：选中当前查询条件下全部用例（跨页）
    skipSelectAllSync = true
    try {
      const count = await collectAllIds()
      ElMessage.success(`已全选 ${count} 条用例`)
    } catch (e: any) {
      ElMessage.error(e?.message || '获取全部用例失败')
      tableRef.value?.clearSelection()
    }
  } else {
    // 取消全选
    skipSelectAllSync = true
    selectedMap.value = new Map()
  }
}

const handleSelectionChange = (rows: any[]) => {
  // 全选触发后紧随的 selection-change 已由 handleSelectAll 处理，跳过
  if (skipSelectAllSync) {
    skipSelectAllSync = false
    return
  }
  // 手动勾选/取消单行（含翻页后的 reserve-selection 同步）：只增删当前页对应 id
  const selectedPageIds = new Set(rows.map((r: any) => r.id))
  const next = new Map(selectedMap.value)
  for (const r of list.value) {
    if (selectedPageIds.has(r.id)) next.set(r.id, r.source)
    else next.delete(r.id)
  }
  selectedMap.value = next
}

const openDetail = (row: any) => {
  current.value = row
  editing.value = false
  detailVisible.value = true
}

const handleReview = async (row: any) => {
  await testCaseApi.review(row.id, 'approve')
  ElMessage.success('已通过')
  loadData()
}

const openReject = (row: any) => {
  rejectTarget.value = row
  rejectComment.value = ''
  rejectVisible.value = true
}

const confirmReject = async () => {
  rejecting.value = true
  try {
    await testCaseApi.review(rejectTarget.value.id, 'reject', rejectComment.value)
    ElMessage.success('已驳回')
    rejectVisible.value = false
    loadData()
  } catch (e: any) {
    ElMessage.error(e?.message || '驳回失败')
  } finally {
    rejecting.value = false
  }
}

// ===== 编辑 =====
const startEdit = () => {
  Object.assign(editForm, {
    title: current.value.title,
    module: current.value.module || '',
    priority: current.value.priority || 'L2',
    test_type: current.value.test_type || '功能测试',
    preconditions: current.value.preconditions || '',
    expected_result: current.value.expected_result || '',
    steps: (current.value.steps || []).map((s: any, i: number) => ({
      step_no: i + 1,
      action: s.action || '',
      expected: s.expected || '',
    })),
  })
  editing.value = true
}

const cancelEdit = () => {
  editing.value = false
}

const addStep = () => {
  editForm.steps.push({ step_no: editForm.steps.length + 1, action: '', expected: '' })
}

const saveEdit = async () => {
  if (!editForm.title.trim()) {
    ElMessage.warning('请输入用例标题')
    return
  }
  saving.value = true
  try {
    const payload = {
      title: editForm.title,
      module: editForm.module || null,
      priority: editForm.priority,
      test_type: editForm.test_type,
      preconditions: editForm.preconditions,
      expected_result: editForm.expected_result,
      steps: editForm.steps.map((s: any, i: number) => ({ step_no: i + 1, action: s.action, expected: s.expected })),
    }
    const res = await testCaseApi.update(current.value.id, payload)
    ElMessage.success('保存成功')
    current.value = res?.data ?? res
    editing.value = false
    loadData()
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

// ===== AI 补全 (FR-5.5) =====
const handleAutoComplete = async () => {
  completing.value = true
  try {
    const res = await testCaseApi.autoComplete(current.value.id)
    ElMessage.success(res?.message || 'AI 补全完成')
    const data = res?.data ?? res
    if (data?.case) {
      current.value = data.case
    }
    loadData()
  } catch (e: any) {
    ElMessage.error(e?.message || '补全失败')
  } finally {
    completing.value = false
  }
}

const handleBatchApprove = async () => {
  await testCaseApi.batch({ case_ids: selectedIdsArr.value, action: 'approve' })
  ElMessage.success('批量通过成功')
  loadData()
}

// ===== AI 自查：逐条比对需求原文，标注存疑/不符（不改动用例） =====
const describeSelfCheck = (res: any) => {
  if (!res || typeof res !== 'object' || !('checked' in res)) return 'AI 自查完成'
  let msg = `AI 自查完成：${res.checked} 条已检查`
  if (res.flagged > 0) msg += `，${res.flagged} 条发现问题`
  else msg += `，未发现问题`
  if (res.skipped > 0) msg += `；${res.skipped} 条缺少原文依据已跳过`
  if (res.failed_batches > 0) msg += `；${res.failed_batches} 批调用失败`
  return msg
}

const handleSelfCheck = async (ids: number[], fromDetail = false) => {
  if (!ids?.length) return
  const overlay = fromDetail
    ? null
    : ElLoading.service({ text: 'AI 自查中（逐批比对需求原文，可能需要几分钟）…', fullscreen: true })
  selfChecking.value = true
  try {
    const res: any = await testCaseApi.selfCheck({ case_ids: ids })
    ElMessage.success(describeSelfCheck(res))
    await loadData()
    if (fromDetail && current.value) {
      current.value = list.value.find((r: any) => r.id === current.value.id) ?? current.value
    }
  } catch (e: any) {
    ElMessage.error(e?.message || 'AI 自查失败')
  } finally {
    selfChecking.value = false
    overlay?.close()
  }
}

// ===== 按生成批次整批 AI 自查（复用 task_id 自查接口） =====
const handleSelfCheckByTask = async () => {
  if (!filters.task_id) return
  const t = taskOptions.value.find((o: any) => o.task_id === filters.task_id)
  const overlay = ElLoading.service({
    text: `整批 AI 自查「第${t?.seq ?? ''}次 · ${t?.task_no ?? ''}」（约 ${t?.case_count ?? 0} 条，逐批比对需求原文，可能需要几分钟）…`,
    fullscreen: true,
  })
  selfChecking.value = true
  try {
    const res: any = await testCaseApi.selfCheck({ task_id: Number(filters.task_id) })
    ElMessage.success(describeSelfCheck(res))
    await loadTasks()
    await loadData()
  } catch (e: any) {
    ElMessage.error(e?.message || '整批自查失败')
  } finally {
    selfChecking.value = false
    overlay?.close()
  }
}

// ===== 重复扫描（按批次或选中条数，识别同义重复并标注，不改动用例） =====
const handleDedupScan = async () => {
  const payload: any = filters.task_id
    ? { task_id: Number(filters.task_id) }
    : selectedIdsArr.length
      ? { case_ids: selectedIdsArr }
      : null
  if (!payload) return
  const overlay = ElLoading.service({
    text: '正在扫描同义重复用例（分组比对，可能需要几分钟）…',
    fullscreen: true,
  })
  dedupScanning.value = true
  try {
    const res: any = await testCaseApi.dedupScan(payload)
    const groups = res?.groups ?? 0
    const flagged = res?.flagged ?? 0
    if (groups > 0) {
      ElMessage.success(`重复扫描完成：发现 ${groups} 组疑似重复，已标注 ${flagged} 条（查看详情备注，每组保留1条）`)
    } else {
      ElMessage.success(`重复扫描完成：检查 ${res?.scanned ?? 0} 条，未发现疑似重复`)
    }
    await loadTasks()
    await loadData()
  } catch (e: any) {
    ElMessage.error(e?.message || '重复扫描失败')
  } finally {
    dedupScanning.value = false
    overlay?.close()
  }
}

// ===== 一键清理重复：按批次或选中范围预览 → 确认后删除冗余（每组保留代表用例） =====
const handleDedupCleanup = async () => {
  const payload: any = filters.task_id
    ? { task_id: Number(filters.task_id) }
    : selectedIdsArr.length
      ? { case_ids: selectedIdsArr }
      : null
  if (!payload) return
  dedupCleaning.value = true
  try {
    // 第一步：预览（dry_run），只统计不删除
    const prev: any = await testCaseApi.dedupCleanup({ ...payload, dry_run: true })
    const deleted = prev?.deleted ?? 0
    if (!deleted) {
      ElMessage.info('当前范围内没有可清理的疑似重复用例')
      return
    }
    const skipped = prev?.skipped_good ?? 0
    // 第二步：确认
    await ElMessageBox.confirm(
      `将按 ${prev?.groups ?? 0} 个重复组各保留 1 条代表用例（共 ${prev?.keep_count ?? 0} 条），` +
        `删除冗余 ${deleted} 条` +
        (skipped ? `（跳过已反馈 good 的 ${skipped} 条）` : '') +
        '。删除后不可恢复，是否继续？',
      '一键清理重复',
      { type: 'warning', confirmButtonText: '确认清理', cancelButtonText: '再想想' },
    )
    // 第三步：执行删除
    const res: any = await testCaseApi.dedupCleanup({ ...payload, dry_run: false })
    ElMessage.success(res?.message || '清理完成')
    await loadTasks()
    await loadData()
  } catch (e: any) {
    // 用户取消确认不提示错误
    if (e !== 'cancel' && e !== 'close') {
      ElMessage.error(e?.message || '清理失败')
    }
  } finally {
    dedupCleaning.value = false
  }
}

// ===== AI 质量反馈 (FR-3.9) =====
const handleFeedback = async (row: any, feedback: 'good' | 'bad') => {
  try {
    const next = row.feedback === feedback ? 'clear' : feedback
    await testCaseApi.feedback(row.id, next as any)
    row.feedback = next === 'clear' ? null : next
    ElMessage.success(next === 'clear' ? '已清除反馈' : '已记录反馈')
  } catch (e: any) {
    ElMessage.error(e?.message || '反馈失败')
  }
}

// ===== 批量重生成 (FR-3.8) =====
const handleBatchRegenerate = async () => {
  const ids = Array.from(selectedMap.value.entries())
    .filter(([, source]) => source === 'ai')
    .map(([id]) => id)
  if (!ids.length) {
    ElMessage.warning('请选择 AI 生成的用例')
    return
  }
  await ElMessageBox.confirm(`将重新生成 ${ids.length} 条 AI 用例并覆盖原内容，是否继续？`, '批量重生成', { type: 'warning' })
  const loading = ElLoading.service({ text: '正在重新生成，请稍候…', fullscreen: true })
  try {
    const res: any = await testCaseApi.batchRegenerate(ids)
    ElMessage.success(res?.message || `已重生成 ${ids.length} 条用例`)
    loadData()
  } catch (e: any) {
    ElMessage.error(e?.message || '重生成失败')
  } finally {
    loading.close()
  }
}

const handleRegenerate = async (row: any) => {
  await ElMessageBox.confirm(`确认重新生成用例「${row.case_no}」？将覆盖原内容。`, '重新生成', { type: 'warning' })
  const res: any = await testCaseApi.batchRegenerate([row.id])
  ElMessage.success(res?.message || '重生成完成')
  loadData()
}

const handleBatchDelete = async () => {
  await ElMessageBox.confirm(`确认删除选中的 ${selectedCount.value} 条用例？删除后不可恢复。`, '批量删除', { type: 'error' })
  await testCaseApi.batch({ case_ids: selectedIdsArr.value, action: 'delete' })
  ElMessage.success('批量删除成功')
  loadData()
}

const openScriptDialog = () => {
  scriptDialogRef.value?.open()
}

const handleExport = async (format: 'excel' | 'markdown' | 'json' | 'xmind' = 'excel') => {
  const blob = (await testCaseApi.export(selectedIdsArr.value, format)) as any
  const url = URL.createObjectURL(new Blob([blob]))
  const a = document.createElement('a')
  const ext = format === 'excel' ? 'xlsx' : format
  a.href = url
  a.download = `test_cases_${projectId}.${ext}`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(() => {
  loadData()
  loadModules()
  loadTasks()
})
</script>

<style scoped>
.mb16 {
  margin-bottom: 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.flex-1 {
  flex: 1;
}

.filter {
  width: 130px;
}

.task-filter {
  width: 260px;
}

.selected-info {
  margin: 0 4px;
  color: #606266;
  font-size: 13px;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}

.detail-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 8px;
}

.detail-meta {
  display: flex;
  gap: 8px;
}

.mt16 {
  margin-top: 16px;
}

.mt8 {
  margin-top: 8px;
}

.step-title {
  font-weight: 600;
  margin: 16px 0 8px;
}

.expected-box {
  padding: 12px;
  background: #f5f7fa;
  border-radius: 4px;
  white-space: pre-wrap;
  line-height: 1.6;
}

.warn-box {
  background: #fdf6ec;
  color: #7a5c2a;
  border: 1px solid #faecd8;
}

.check-tip {
  white-space: pre-wrap;
  max-width: 520px;
  line-height: 1.7;
}

.check-ok {
  color: #909399;
  font-size: 12px;
}
</style>