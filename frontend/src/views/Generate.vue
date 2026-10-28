<template>
  <div>
    <el-card shadow="never" class="mb16">
      <template #header>
        <span class="card-title">AI 用例生成</span>
        <span class="card-desc">上传需求文档后，由 AI 智能体流水线自动生成测试用例</span>
      </template>
      <el-form label-width="90px">
        <el-form-item label="选择项目" required>
          <el-select v-model="form.project_id" placeholder="选择项目" style="width: 320px" @change="loadDocuments">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="需求文档" required>
          <el-select v-model="form.document_ids" multiple placeholder="选择需求文档" style="width: 480px">
            <el-option v-for="d in documents" :key="d.id" :label="d.title" :value="d.id" />
          </el-select>
          <div class="tip">提示：请先在「项目管理 → 文档」中上传并解析需求文档</div>
        </el-form-item>
        <el-form-item label="生成选项">
          <div class="options">
            <div class="opt-row">
              <span class="opt-label">测试类型：</span>
              <el-checkbox-group v-model="form.include_types">
                <el-checkbox value="function">功能</el-checkbox>
                <el-checkbox value="boundary">边界</el-checkbox>
                <el-checkbox value="exception">异常</el-checkbox>
                <el-checkbox value="performance">性能</el-checkbox>
                <el-checkbox value="security">安全</el-checkbox>
                <el-checkbox value="implicit">隐式</el-checkbox>
              </el-checkbox-group>
            </div>
            <div class="opt-row">
              <span class="opt-label">用例等级：</span>
              <el-checkbox-group v-model="form.priority_levels">
                <el-checkbox value="L1">L1 基本</el-checkbox>
                <el-checkbox value="L2">L2 重要</el-checkbox>
                <el-checkbox value="L3">L3 一般</el-checkbox>
                <el-checkbox value="L4">L4 轻微</el-checkbox>
              </el-checkbox-group>
            </div>
            <div class="tip level-tip">
              等级按《测试用例等级定义规范》判定，目标占比 L1≈10% / L2≈20% / L3≈60% / L4≈10%。
              L1 主流程与主要入口功能；L2 常用正常功能、有效等价类与有效边界值；
              L3 无效等价类、特殊字符、超长、超时、性能与兼容性；L4 深层路径、生僻前置条件、易用性与体验问题
            </div>
            <div class="opt-row">
              <span class="opt-label">生成倍数：</span>
              <el-slider
                v-model="form.case_multiplier"
                :min="1"
                :max="5"
                :step="1"
                :show-tooltip="false"
                class="multiplier-slider"
              />
              <span class="multiplier-val">{{ form.case_multiplier }}x</span>
              <span class="multiplier-hint">{{ multiplierHints[form.case_multiplier] }}</span>
            </div>
            <div class="opt-row est-row" v-if="estimate">
              <span class="opt-label">预计生成：</span>
              <span class="est-text">
                约 <b class="est-num">{{ estimate.est_cases }}</b> 条用例
                <span class="est-sub">（预估 {{ estimate.est_points }} 个测试点 × {{ form.case_multiplier }} 条/点，粗估）</span>
              </span>
              <el-tag v-if="estimate.unparsed > 0" type="warning" size="small">
                有 {{ estimate.unparsed }} 个文档未解析完成，预估可能偏低
              </el-tag>
            </div>
            <div class="opt-row est-row" v-else-if="estLoading">
              <span class="opt-label">预计生成：</span>
              <span class="est-sub">估算中...</span>
            </div>
            <div class="opt-row">
              <el-checkbox v-model="form.enable_rag">启用 RAG 知识库增强</el-checkbox>
              <el-checkbox v-model="form.replace_existing">
                覆盖重建：先清空所选文档原有测试点/用例再生成
              </el-checkbox>
            </div>
            <div class="opt-row">
              <el-checkbox v-model="form.auto_dedup">
                生成后自动重复扫描：对本批结果打【疑似重复】标注（只标不删）
              </el-checkbox>
            </div>
            <div class="opt-row">
              <el-checkbox v-model="form.dedup_on_generate">
                入库前防重：与库内已有用例操作路径高度相似的候选不再写入（仅拦明显重复）
              </el-checkbox>
            </div>
            <div class="opt-row replace-hint" v-if="form.replace_existing">
              <span class="tip">注意：勾选后将删除所选文档名下已有的全部测试点与用例（含历史结果），用本次新结果替代，用于清理旧数据/多余用例。</span>
            </div>
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="large" :loading="creating" @click="handleGenerate">
            <el-icon><MagicStick /></el-icon>开始生成
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 任务进度 -->
    <el-card v-if="task" shadow="never">
      <template #header>
        <div class="progress-head">
          <span>
            <span class="card-title">任务进度</span>
            <el-tag :type="taskStatusMap[task.status]?.type" class="ml8">{{ taskStatusMap[task.status]?.label }}</el-tag>
            <el-tag v-if="!isOwner" type="info" class="ml8">只读（{{ ownerName }} 的任务）</el-tag>
          </span>
          <el-select
            v-if="runningList.length > 1"
            :model-value="task.id"
            size="small"
            style="width: 300px"
            @change="switchRunningTask"
          >
            <el-option v-for="t in runningList" :key="t.id" :value="t.id"
                       :label="`${t.task_no} · ${t.progress}% · ${taskStatusMap[t.status]?.label || t.status}`" />
          </el-select>
        </div>
      </template>
      <el-progress :percentage="task.progress" :status="task.status === 'failed' ? 'exception' : undefined" />
      <div class="stage-text">{{ stageText }}</div>
      <div v-if="task.status === 'success'" class="result-box">
        <el-result icon="success" title="生成完成" :sub-title="`共生成 ${task.total_case} 条测试用例`">
          <template #extra>
            <template v-if="isOwner">
              <el-button type="primary" @click="goCases">查看用例</el-button>
              <el-button type="warning" plain :loading="checking" @click="handleSelfCheck">AI 自查</el-button>
              <el-button @click="viewCoverage">查看覆盖率</el-button>
            </template>
            <el-button @click="reviewVisible = true">查看评审</el-button>
          </template>
        </el-result>
        <el-alert
          v-if="autoDedupInfo"
          :type="autoDedupInfo.type"
          :title="autoDedupInfo.title"
          :description="autoDedupInfo.description"
          :closable="false"
          show-icon
          class="auto-dedup-alert"
        />
        <el-alert
          v-if="dedupSkippedInfo"
          type="info"
          :title="dedupSkippedInfo.title"
          :description="dedupSkippedInfo.description"
          :closable="false"
          show-icon
          class="auto-dedup-alert"
        />
      </div>
      <el-alert v-if="task.error_msg" type="error" :title="task.error_msg" show-icon />
    </el-card>

    <!-- 评审结果弹窗（FR-5.2 评审结果展示） -->
    <el-dialog v-model="reviewVisible" title="AI 评审结果" width="720px">
      <template v-if="review">
        <div class="review-score">
          <span>综合评分：</span>
          <el-rate :model-value="review.overall_score / 20" disabled show-score score-template="{value} 分" />
          <el-tag :type="review.overall_score >= 80 ? 'success' : review.overall_score >= 60 ? 'warning' : 'danger'" class="ml8">
            {{ review.overall_score >= 80 ? '优秀' : review.overall_score >= 60 ? '待改进' : '较差' }}
          </el-tag>
        </div>

        <el-tabs>
          <el-tab-pane label="问题清单">
            <el-table v-if="review.issues && review.issues.length" :data="review.issues" border size="small" max-height="280">
              <el-table-column type="index" width="50" />
              <el-table-column prop="case_no" label="用例编号" width="120" />
              <el-table-column prop="issue" label="问题描述" />
            </el-table>
            <el-empty v-else description="无评审问题，用例质量良好" :image-size="80" />
          </el-tab-pane>
          <el-tab-pane label="缺失覆盖">
            <el-table v-if="review.missing_coverage && review.missing_coverage.length" :data="review.missing_coverage" border size="small" max-height="280">
              <el-table-column type="index" width="50" />
              <el-table-column prop="point" label="缺失测试点" />
              <el-table-column prop="reason" label="原因" min-width="200" />
            </el-table>
            <el-empty v-else description="无明显缺失覆盖" :image-size="80" />
          </el-tab-pane>
          <el-tab-pane label="业务流程" v-if="businessFlows.length">
            <el-empty v-if="!businessFlows.length" description="无业务流程信息" :image-size="80" />
            <div v-for="(bf, i) in businessFlows" :key="i" class="flow-item">
              <div class="flow-title">{{ bf.no }} {{ bf.name }}</div>
              <el-steps :active="bf.flow.length" align-center simple>
                <el-step v-for="(step, si) in bf.flow" :key="si" :title="step" />
              </el-steps>
            </div>
          </el-tab-pane>
        </el-tabs>
      </template>
      <el-empty v-else description="暂无评审数据" :image-size="80" />
    </el-dialog>

    <!-- 覆盖率弹窗 -->
    <el-dialog v-model="coverageVisible" title="覆盖率分析" width="600px">
      <div class="coverage-summary">
        <span>覆盖率：</span>
        <el-progress :percentage="coverage.coverage_rate" style="width: 200px" />
      </div>
      <el-table :data="coverage.items || []" height="400" border>
        <el-table-column prop="name" label="测试点" min-width="160" />
        <el-table-column prop="type" label="类型" width="90">
          <template #default="{ row }">
            <el-tag size="small">{{ typeMap[row.type] }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="覆盖" width="80">
          <template #default="{ row }">
            <el-tag :type="row.covered ? 'success' : 'danger'" size="small">{{ row.covered ? '已覆盖' : '未覆盖' }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { documentApi, generateApi, projectApi, testCaseApi } from '@/api'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const projects = ref<any[]>([])
const documents = ref<any[]>([])
const form = reactive({
  project_id: Number(route.query.project_id) || undefined,
  document_ids: route.query.document_id ? [Number(route.query.document_id)] : [],
  include_types: ['function', 'boundary', 'exception'],
  priority_levels: ['L1', 'L2', 'L3', 'L4'],
  enable_rag: true,
  case_multiplier: 2, // 生成倍数：每个测试点生成的用例条数（1x~5x）
  replace_existing: false, // 覆盖重建：清空所选文档旧测试点/用例后重新生成
  auto_dedup: true, // 生成完成后自动对本批用例执行重复扫描标注
  dedup_on_generate: true, // 入库前防重：与库内已有用例操作路径高度相似的候选不入库
})
const multiplierHints: Record<number, string> = {
  1: '精简：每测试点约 1 条',
  2: '标准（默认）：每测试点约 2 条',
  3: '较全：每测试点约 3 条',
  4: '全面：每测试点约 4 条',
  5: '深度：每测试点约 5 条',
}

const creating = ref(false)
const checking = ref(false)
const task = ref<any>(null)
// 多任务并行支持：我的进行中任务列表 + 当前轮询定时器
const runningList = ref<any[]>([])
let pollTimer: number | null = null
const coverageVisible = ref(false)
const coverage = ref<any>({})
const reviewVisible = ref(false)

const taskStatusMap: Record<string, { label: string; type: string }> = {
  pending: { label: '等待中', type: 'info' },
  running: { label: '生成中', type: 'warning' },
  success: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
  cancelled: { label: '已取消', type: 'info' },
}
const typeMap: Record<string, string> = {
  function: '功能', boundary: '边界', exception: '异常', performance: '性能', security: '安全', implicit: '隐式',
}

// 任务归属：只有创建人（或 admin 在自己任务上）可执行后续操作，他人视角只读
const isOwner = computed(() => {
  if (!task.value) return false
  return !task.value.created_by || task.value.created_by === userStore.userInfo?.id || !userStore.userInfo?.id
})
const ownerName = computed(() => {
  const it = runningList.value.find((x) => x.id === task.value?.id)
  return it?.creator_name || '其他用户'
})
const review = computed(() => task.value?.result_summary?.review || null)
const businessFlows = computed(() => (task.value?.result_summary?.business_flows || []).map((f: any) => ({
  ...f,
  flow: (f.flow || '').split('>').map((s: string) => s.trim()).filter(Boolean),
})))

const stageText = computed(() => {
  if (!task.value) return ''
  const map: Record<string, string> = {
    pending: '等待调度...', requirement_parse: 'AI 解析需求...', test_point_extraction: 'AI 提取测试点...',
    rag_retrieval: '检索知识库...', case_generation: 'AI 生成用例...', case_review: 'AI 评审用例...', complete: '完成',
  }
  return map[task.value.stage] || ''
})

// 生成收尾自动重复扫描的结果展示（result_summary.auto_dedup）
const autoDedupInfo = computed(() => {
  const a = task.value?.result_summary?.auto_dedup
  if (!a) return null
  if (a.error) {
    return { type: 'warning', title: '本次重复扫描未能完成', description: String(a.error) }
  }
  if (a.groups && a.groups > 0) {
    return {
      type: 'warning',
      title: `发现 ${a.groups} 组疑似重复：已标注 ${a.flagged} 条（扫描 ${a.scanned || 0} 条）`,
      description: '可在「用例管理 → 按生成批次 → 一键清理重复」中保留每组代表并删除冗余。',
    }
  }
  return {
    type: 'success',
    title: '重复扫描完成：未发现疑似重复组',
    description: `已对本次生成的 ${a.scanned || 0} 条用例自动比对`,
  }
})

// 入库前防重拦截统计（result_summary.dedup_skipped）
const dedupSkippedInfo = computed(() => {
  const s = task.value?.result_summary?.dedup_skipped ?? 0
  if (s <= 0) return null
  const examples = (task.value?.result_summary?.dedup_skip_examples || []).slice(0, 2)
  return {
    title: `入库前防重：拦截 ${s} 条与库内已有用例重复的候选（未写入库）`,
    description: examples.length ? `示例：${examples.join('；')}` : '可通过取消“入库前防重”关闭本拦截',
  }
})

const loadProjects = async () => {
  const data = await projectApi.list({ page_size: 100 })
  projects.value = data.list
  if (form.project_id) loadDocuments()
}

const loadDocuments = async () => {
  if (!form.project_id) return
  const data = await documentApi.list({ project_id: form.project_id, page_size: 100 })
  documents.value = data.list
}

// ===== 预计生成量（生成倍数 × 预估测试点数） =====
const estimate = ref<any>(null)
const estLoading = ref(false)
const loadEstimate = async () => {
  estimate.value = null
  if (!form.project_id || !form.document_ids.length) return
  estLoading.value = true
  try {
    const res: any = await generateApi.preview({
      project_id: form.project_id,
      document_ids: form.document_ids,
    })
    estimate.value = {
      est_points: res.est_points,
      est_cases: Math.round(res.est_points * form.case_multiplier),
      unparsed: res.unparsed,
    }
  } catch {
    /* 预估失败不阻塞生成 */
  } finally {
    estLoading.value = false
  }
}
// 项目/文档变化时向后端请求预估测试点数
watch(
  () => [form.project_id, form.document_ids.slice().join(',')],
  loadEstimate,
)
// 拖动滑杆（倍数变化）仅本地重算，避免连续请求后端
watch(
  () => form.case_multiplier,
  (v) => {
    if (estimate.value && estimate.value.est_points) {
      estimate.value.est_cases = Math.round(estimate.value.est_points * v)
    }
  },
)
// 路由直带 project/document 时也触发一次预估
if (form.project_id && form.document_ids.length) {
  setTimeout(loadEstimate, 0)
}

const handleGenerate = async () => {
  if (!form.project_id) return ElMessage.warning('请选择项目')
  if (!form.document_ids.length) return ElMessage.warning('请选择需求文档')
  // 多账号并行提示：已有进行中任务时再创建会共享 LLM 配额
  const activeCount = runningList.value.filter((t) => ['pending', 'running'].includes(t.status)).length
  if (activeCount > 0) {
    try {
      await ElMessageBox.confirm(
        `你已有 ${activeCount} 个生成任务进行中。并行生成会共享 LLM 接口配额，可能拖慢彼此速度，确定继续？`,
        '存在进行中的任务',
        { type: 'warning', confirmButtonText: '继续生成', cancelButtonText: '先等完成' },
      )
    } catch {
      return
    }
  }
  creating.value = true
  try {
    const res = await generateApi.create({
      project_id: form.project_id,
      document_ids: form.document_ids,
      options: {
        include_types: form.include_types,
        priority_levels: form.priority_levels,
        enable_rag: form.enable_rag,
        case_multiplier: form.case_multiplier,
        replace_existing: form.replace_existing,
        auto_dedup: form.auto_dedup,
        dedup_on_generate: form.dedup_on_generate,
      },
    })
    task.value = { ...res, progress: 0, stage: 'pending', status: 'pending' }
    ElMessage.success(`任务已创建：${res.task_no}`)
    // task_id 写入 URL：刷新/跳转后可自动恢复进度
    router.replace({ query: { ...route.query, task_id: res.task_id } })
    startPolling(res.task_id)
    refreshRunningList()
  } finally {
    creating.value = false
  }
}

const stopPolling = () => {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const startPolling = (taskId: number) => {
  stopPolling()
  pollTimer = window.setInterval(async () => {
    try {
      const t = await generateApi.detail(taskId)
      task.value = t
      // 同步进行中任务列表里的进度
      const it = runningList.value.find((x) => x.id === taskId)
      if (it) {
        it.progress = t.progress
        it.status = t.status
      }
      if (['success', 'failed', 'cancelled'].includes(t.status)) {
        stopPolling()
        refreshRunningList()
      }
    } catch (e: any) {
      // 临时错误（网络抖动/后端瞬时故障）不中断轮询，任务仍在后台执行；
      // 仅当任务不存在（404）或明确终止时才停止
      if (e?.response?.status === 404) {
        stopPolling()
        refreshRunningList()
      }
    }
  }, 3000)
}

onUnmounted(stopPolling)

// 刷新"我的进行中任务"列表（普通用户后端只返回自己的；再按创建人过滤双保险）
const refreshRunningList = async () => {
  try {
    const res: any = await generateApi.list({ status: 'running', page: 1, page_size: 50 })
    const items = res?.list ?? res?.data?.list ?? res ?? []
    runningList.value = items.filter((t: any) => t.created_by === userStore.userInfo?.id)
  } catch {
    runningList.value = []
  }
}

// 恢复进度：URL 带 task_id 优先；否则自动接续我最近的进行中任务
const restoreProgress = async () => {
  const tid = Number(route.query.task_id)
  if (tid) {
    try {
      const t = await generateApi.detail(tid)
      task.value = t
      if (['pending', 'running'].includes(t.status)) startPolling(tid)
    } catch {
      /* 任务不存在则忽略，走自动接续 */
    }
  }
  await refreshRunningList()
  if (!task.value || ['success', 'failed', 'cancelled'].includes(task.value.status)) {
    const mine = runningList.value
      .filter((t) => ['pending', 'running'].includes(t.status))
      .sort((a, b) => b.id - a.id)
    if (mine.length) {
      const t = await generateApi.detail(mine[0].id)
      task.value = t
      startPolling(t.id)
      router.replace({ query: { ...route.query, task_id: t.id } })
    }
  }
}

// 多任务切换：切换展示的任务并继续轮询
const switchRunningTask = async (taskId: number) => {
  try {
    const t = await generateApi.detail(taskId)
    task.value = t
    if (['pending', 'running'].includes(t.status)) startPolling(taskId)
    else stopPolling()
    router.replace({ query: { ...route.query, task_id: taskId } })
  } catch {
    ElMessage.error('任务不存在或已被删除')
    refreshRunningList()
  }
}

const goCases = () => router.push(`/projects/${task.value?.project_id || form.project_id}/cases`)
const viewCoverage = async () => {
  coverage.value = await generateApi.coverage(task.value.id)
  coverageVisible.value = true
}

// AI 自查：对本次任务生成的全部用例逐条比对需求原文，标注存疑/不符（只标注不改动）
const handleSelfCheck = async () => {
  if (!task.value?.id) return
  checking.value = true
  try {
    const res: any = await testCaseApi.selfCheck({ task_id: task.value.id })
    if (res && typeof res === 'object' && 'checked' in res) {
      let msg = `AI 自查完成：${res.checked} 条已检查`
      if (res.flagged > 0) msg += `，${res.flagged} 条发现问题`
      else msg += `，未发现问题`
      if (res.skipped > 0) msg += `；${res.skipped} 条缺少原文依据已跳过`
      ElMessage.success(msg)
    } else {
      ElMessage.success('AI 自查完成，请到用例列表查看备注')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || 'AI 自查失败')
  } finally {
    checking.value = false
  }
}

onMounted(() => {
  loadProjects()
  restoreProgress()
})
</script>

<style scoped>
.mb16 {
  margin-bottom: 16px;
}

.progress-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.card-title {
  font-weight: 600;
}

.card-desc {
  margin-left: 12px;
  color: #909399;
  font-size: 12px;
}

.tip {
  margin-top: 4px;
  font-size: 12px;
  color: #c0c4cc;
}

.level-tip {
  margin: -2px 0 2px 0;
  line-height: 1.7;
  color: #a8abb2;
}

.options {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.opt-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.opt-label {
  color: #606266;
  font-size: 13px;
  flex-shrink: 0;
}

.multiplier-slider {
  width: 300px;
  flex-shrink: 0;
}

.multiplier-val {
  font-weight: 600;
  color: #409eff;
  min-width: 28px;
}

.multiplier-hint {
  color: #909399;
  font-size: 12px;
}

.est-row {
  color: #606266;
}

.est-text {
  font-size: 13px;
}

.est-num {
  color: #f56c6c;
  font-size: 16px;
}

.est-sub {
  color: #c0c4cc;
  font-size: 12px;
}

.ml8 {
  margin-left: 8px;
}

.stage-text {
  margin-top: 12px;
  color: #606266;
}

.auto-dedup-alert {
  margin: 14px 24px 4px;
  text-align: left;
}

.coverage-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.review-score {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.flow-item {
  margin-bottom: 20px;
}

.flow-title {
  font-weight: 600;
  margin-bottom: 8px;
}
</style>
