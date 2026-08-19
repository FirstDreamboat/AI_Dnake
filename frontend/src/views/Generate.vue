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
                <el-checkbox value="P0">P0</el-checkbox>
                <el-checkbox value="P1">P1</el-checkbox>
                <el-checkbox value="P2">P2</el-checkbox>
                <el-checkbox value="P3">P3</el-checkbox>
                <el-checkbox value="P4">P4</el-checkbox>
              </el-checkbox-group>
            </div>
            <el-checkbox v-model="form.enable_rag">启用 RAG 知识库增强</el-checkbox>
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
        <span class="card-title">任务进度</span>
        <el-tag :type="taskStatusMap[task.status]?.type" class="ml8">{{ taskStatusMap[task.status]?.label }}</el-tag>
      </template>
      <el-progress :percentage="task.progress" :status="task.status === 'failed' ? 'exception' : undefined" />
      <div class="stage-text">{{ stageText }}</div>
      <div v-if="task.status === 'success'" class="result-box">
        <el-result icon="success" title="生成完成" :sub-title="`共生成 ${task.total_case} 条测试用例`">
          <template #extra>
            <el-button type="primary" @click="goCases">查看用例</el-button>
            <el-button @click="viewCoverage">查看覆盖率</el-button>
            <el-button @click="reviewVisible = true">查看评审</el-button>
          </template>
        </el-result>
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
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { documentApi, generateApi, projectApi } from '@/api'

const route = useRoute()
const router = useRouter()

const projects = ref<any[]>([])
const documents = ref<any[]>([])
const form = reactive({
  project_id: Number(route.query.project_id) || undefined,
  document_ids: route.query.document_id ? [Number(route.query.document_id)] : [],
  include_types: ['function', 'boundary', 'exception'],
  priority_levels: ['P0', 'P1', 'P2', 'P3', 'P4'],
  enable_rag: true,
})

const creating = ref(false)
const task = ref<any>(null)
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

const handleGenerate = async () => {
  if (!form.project_id) return ElMessage.warning('请选择项目')
  if (!form.document_ids.length) return ElMessage.warning('请选择需求文档')
  creating.value = true
  try {
    const res = await generateApi.create({
      project_id: form.project_id,
      document_ids: form.document_ids,
      options: {
        include_types: form.include_types,
        priority_levels: form.priority_levels,
        enable_rag: form.enable_rag,
      },
    })
    task.value = { ...res, progress: 0, stage: 'pending', status: 'pending' }
    ElMessage.success(`任务已创建：${res.task_no}`)
    startPolling(res.task_id)
  } finally {
    creating.value = false
  }
}

const startPolling = (taskId: number) => {
  const timer = setInterval(async () => {
    try {
      const t = await generateApi.detail(taskId)
      task.value = t
      if (['success', 'failed', 'cancelled'].includes(t.status)) {
        clearInterval(timer)
      }
    } catch (e: any) {
      // 临时错误（网络抖动/后端瞬时故障）不中断轮询，任务仍在后台执行；
      // 仅当任务不存在（404）或明确终止时才停止
      if (e?.response?.status === 404) {
        clearInterval(timer)
      }
    }
  }, 3000)
}

const goCases = () => router.push(`/projects/${form.project_id}/cases`)
const viewCoverage = async () => {
  coverage.value = await generateApi.coverage(task.value.id)
  coverageVisible.value = true
}

onMounted(loadProjects)
</script>

<style scoped>
.mb16 {
  margin-bottom: 16px;
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

.ml8 {
  margin-left: 8px;
}

.stage-text {
  margin-top: 12px;
  color: #606266;
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
