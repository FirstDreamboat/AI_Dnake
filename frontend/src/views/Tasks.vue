<template>
  <div class="tasks-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>生成任务历史</span>
          <div class="header-right">
            <el-select v-model="query.status" placeholder="状态" clearable style="width: 140px" @change="load">
              <el-option label="待执行" value="pending" />
              <el-option label="执行中" value="running" />
              <el-option label="成功" value="success" />
              <el-option label="失败" value="failed" />
              <el-option label="已取消" value="cancelled" />
            </el-select>
            <el-button :icon="Refresh" @click="load">刷新</el-button>
          </div>
        </div>
      </template>
      <el-table :data="tasks" v-loading="loading" stripe>
        <el-table-column prop="task_no" label="任务编号" width="160" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="进度" width="140">
          <template #default="{ row }">
            <el-progress v-if="row.status === 'running' || row.status === 'pending'" :percentage="row.progress || 0" :stroke-width="10" />
            <span v-else class="muted">{{ row.progress || 0 }}%</span>
          </template>
        </el-table-column>
        <el-table-column prop="total_case" label="用例数" width="80" align="center">
          <template #default="{ row }">{{ row.total_case || 0 }}</template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="error_msg" label="失败原因" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.error_msg" class="error-text">{{ row.error_msg }}</span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button v-if="canRetry(row)" link type="primary" @click="retry(row)">重试</el-button>
            <el-button link type="warning" @click="viewSummary(row)">查看结果</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        v-model:current-page="query.page"
        :page-size="query.page_size"
        :total="total"
        layout="total, prev, pager, next"
        class="pager"
        @current-change="load"
      />
    </el-card>

    <el-dialog v-model="summaryVisible" title="任务结果摘要" width="720px">
      <el-descriptions :column="2" border>
        <el-descriptions-item label="任务编号">{{ current?.task_no }}</el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="statusType(current?.status)" size="small">{{ statusLabel(current?.status) }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="用例数">{{ current?.total_case || 0 }}</el-descriptions-item>
        <el-descriptions-item label="完成时间">{{ formatTime(current?.finished_at) }}</el-descriptions-item>
      </el-descriptions>
      <el-divider content-position="left">生成结果</el-divider>
      <div v-if="summaryText" class="summary-text">{{ summaryText }}</div>
      <el-empty v-else description="暂无结果数据" :image-size="80" />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { generateApi } from '@/api'

const loading = ref(false)
const tasks = ref<any[]>([])
const total = ref(0)
const query = reactive({ page: 1, page_size: 10, status: '' })

const summaryVisible = ref(false)
const current = ref<any>(null)
const summaryText = ref('')

const statusLabel = (s: string) =>
  ({ pending: '待执行', running: '执行中', success: '成功', failed: '失败', cancelled: '已取消' }[s] || s || '-')

const statusType = (s: string) =>
  ({ pending: 'info', running: 'warning', success: 'success', failed: 'danger', cancelled: 'info' }[s] || 'info') as any

const canRetry = (row: any) => row.status === 'failed' || row.status === 'cancelled'

const formatTime = (t?: string) => (t ? new Date(t).toLocaleString('zh-CN', { hour12: false }) : '-')

const load = async () => {
  loading.value = true
  try {
    const data: any = await generateApi.list(query)
    tasks.value = data.list || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

const retry = async (row: any) => {
  await ElMessageBox.confirm(`确认重试任务 ${row.task_no}？将基于原文档重新生成。`, '重试任务', { type: 'warning' })
  const data: any = await generateApi.retry(row.id)
  ElMessage.success(`任务 ${data.task_no} 已重新加入队列`)
  load()
}

const viewSummary = async (row: any) => {
  current.value = row
  summaryText.value = ''
  try {
    const data: any = await generateApi.summary(row.id)
    summaryText.value = typeof data === 'string' ? data : JSON.stringify(data, null, 2)
  } catch {
    summaryText.value = ''
  }
  summaryVisible.value = true
}

onMounted(load)
</script>

<style scoped>
.tasks-page {
  padding: 4px;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.header-right {
  display: flex;
  gap: 8px;
  align-items: center;
}
.pager {
  margin-top: 16px;
  justify-content: flex-end;
}
.muted {
  color: #c0c4cc;
}
.error-text {
  color: #f56c6c;
  font-size: 12px;
}
.summary-text {
  white-space: pre-wrap;
  font-size: 13px;
  color: #303133;
  max-height: 320px;
  overflow-y: auto;
  background: #f5f7fa;
  padding: 12px;
  border-radius: 6px;
}
</style>
