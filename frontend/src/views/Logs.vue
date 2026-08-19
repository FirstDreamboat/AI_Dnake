<template>
  <div class="logs-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>操作日志</span>
            <el-select v-model="filterModule" placeholder="模块" clearable style="width: 130px" @change="loadData">
              <el-option
                v-for="m in modules"
                :key="m.value"
                :label="m.label"
                :value="m.value"
              />
            </el-select>
            <el-input
              v-model="filterUser"
              placeholder="操作人"
              clearable
              style="width: 140px"
              @keyup.enter="loadData"
              @clear="loadData"
            />
            <el-input
              v-model="filterKeyword"
              placeholder="动作 / 路径关键字"
              clearable
              style="width: 200px"
              @keyup.enter="loadData"
              @clear="loadData"
            />
          </div>
          <div class="header-right">
            <el-button type="success" plain @click="handleExport">
              <el-icon><Download /></el-icon>导出
            </el-button>
            <el-button type="danger" plain @click="handleClear" :disabled="!isAdmin">
              <el-icon><Delete /></el-icon>清空日志
            </el-button>
            <el-button @click="loadData">
              <el-icon><Refresh /></el-icon>刷新
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="list" border stripe v-loading="loading" size="small">
        <el-table-column prop="created_at" label="时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作人" width="110">
          <template #default="{ row }">{{ row.username || '未登录' }}</template>
        </el-table-column>
        <el-table-column label="模块" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ moduleLabel(row.module) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="方法" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="methodTag(row.method)">{{ row.method }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="action" label="动作" width="150" show-overflow-tooltip />
        <el-table-column prop="path" label="路径" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <code class="path-code">{{ row.path }}</code>
          </template>
        </el-table-column>
        <el-table-column prop="detail" label="详情" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ shortDetail(row.detail) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status_code < 400 ? 'success' : 'danger'">{{ row.status_code }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="ip" label="IP" width="130" />
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next"
          @current-change="loadData"
          @size-change="loadData"
        />
      </div>
    </el-card>

    <el-dialog v-model="detailVisible" title="日志详情" width="640px">
      <template v-if="current">
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item label="时间">{{ fmtTime(current.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="操作人">{{ current.username || '未登录' }}</el-descriptions-item>
          <el-descriptions-item label="模块">{{ moduleLabel(current.module) }}</el-descriptions-item>
          <el-descriptions-item label="动作">{{ current.action }}</el-descriptions-item>
          <el-descriptions-item label="请求">
            <code class="detail-code">{{ current.method }} {{ current.path }}</code>
          </el-descriptions-item>
          <el-descriptions-item label="状态码">
            <el-tag size="small" :type="current.status_code < 400 ? 'success' : 'danger'">{{ current.status_code }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="IP">{{ current.ip || '-' }}</el-descriptions-item>
          <el-descriptions-item label="详情">
            <pre class="detail-pre">{{ current.detail || '-' }}</pre>
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download } from '@element-plus/icons-vue'
import { logApi } from '@/api'

const detailVisible = ref(false)
const current = ref<any>(null)

const openDetail = (row: any) => {
  current.value = row
  detailVisible.value = true
}

const handleExport = async () => {
  try {
    const params: any = {}
    if (filterModule.value) params.module = filterModule.value
    if (filterUser.value) params.username = filterUser.value.trim()
    if (filterKeyword.value) params.keyword = filterKeyword.value.trim()
    const blob = (await logApi.export(params)) as any
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `operation_logs_${Date.now()}.csv`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('日志已导出')
  } catch (e: any) {
    ElMessage.error(e?.message || '导出失败')
  }
}

const loading = ref(false)
const list = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const filterModule = ref('')
const filterUser = ref('')
const filterKeyword = ref('')

const isAdmin = ref(false)

const modules = [
  { label: '用户', value: 'users' },
  { label: '项目', value: 'projects' },
  { label: '文档', value: 'documents' },
  { label: '测试点', value: 'test-points' },
  { label: '用例', value: 'test-cases' },
  { label: '任务', value: 'generate' },
  { label: '知识库', value: 'knowledge' },
  { label: '脚本', value: 'scripts' },
  { label: '模板', value: 'script-templates' },
]
const moduleMap = Object.fromEntries(modules.map((m) => [m.value, m.label]))
const moduleLabel = (m: string) => moduleMap[m] || m || '-'
const methodTag = (m: string) =>
  m === 'POST' ? 'primary' : m === 'PUT' ? 'warning' : 'danger'
const fmtTime = (s: string) => (s ? String(s).replace('T', ' ').slice(0, 19) : '-')
const shortDetail = (d: string) => {
  if (!d) return '-'
  const t = d.length > 120 ? d.slice(0, 120) + '…' : d
  return t.replace(/\n/g, ' ')
}

const loadData = async () => {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize.value }
    if (filterModule.value) params.module = filterModule.value
    if (filterUser.value) params.username = filterUser.value.trim()
    if (filterKeyword.value) params.keyword = filterKeyword.value.trim()
    const data = await logApi.list(params)
    list.value = data?.list ?? []
    total.value = data?.total ?? 0
  } catch (e: any) {
    ElMessage.error(e?.message || '加载日志失败')
  } finally {
    loading.value = false
  }
}

const handleClear = async () => {
  if (!isAdmin.value) {
    ElMessage.warning('仅管理员可清空日志')
    return
  }
  await ElMessageBox.confirm('确定清空全部操作日志吗？该操作不可恢复。', '清空确认', { type: 'warning' })
  try {
    const res = await logApi.clear()
    ElMessage.success(res?.message || '清空成功')
    loadData()
  } catch (e: any) {
    ElMessage.error(e?.message || '清空失败')
  }
}

onMounted(() => {
  try {
    const info = JSON.parse(localStorage.getItem('user_info') || 'null')
    isAdmin.value = !!info && info.role === 'admin'
  } catch {
    isAdmin.value = false
  }
  loadData()
})
</script>

<style scoped>
.logs-page {
  padding: 4px;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.path-code {
  font-family: Consolas, Menlo, monospace;
  font-size: 12px;
  background: #f0f2f5;
  padding: 1px 6px;
  border-radius: 3px;
  color: #606266;
}
.header-right {
  display: flex;
  gap: 8px;
}
.detail-code {
  font-family: Consolas, Menlo, monospace;
  font-size: 12px;
  background: #f0f2f5;
  padding: 2px 8px;
  border-radius: 3px;
  color: #303133;
}
.detail-pre {
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 12px;
  line-height: 1.6;
  background: #f8f9fb;
  padding: 10px;
  border-radius: 4px;
  margin: 0;
  max-height: 260px;
  overflow-y: auto;
  color: #303133;
}
</style>
