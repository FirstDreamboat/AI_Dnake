<template>
  <div class="scripts-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>测试脚本管理</span>
            <el-select v-model="filterType" placeholder="全部类型" clearable style="width: 130px" @change="loadData">
              <el-option label="pytest" value="pytest" />
              <el-option label="接口自动化" value="api" />
              <el-option label="UI 自动化" value="ui" />
              <el-option label="自定义" value="custom" />
            </el-select>
            <el-select v-model="filterProject" placeholder="全部项目" clearable filterable style="width: 180px" @change="loadData">
              <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </div>
          <el-button type="primary" @click="loadData">
            <el-icon><Refresh /></el-icon>刷新
          </el-button>
        </div>
      </template>

      <el-table :data="list" border stripe v-loading="loading">
        <el-table-column prop="name" label="脚本名称" min-width="200" show-overflow-tooltip />
        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="typeTag(row.script_type)">{{ typeLabel(row.script_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="language" label="语言" width="90" />
        <el-table-column prop="framework" label="框架" width="110">
          <template #default="{ row }">{{ row.framework || '-' }}</template>
        </el-table-column>
        <el-table-column prop="project_name" label="所属项目" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.project_name || '-' }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewDetail(row)">查看</el-button>
            <el-button link type="warning" @click="openEdit(row)">编辑</el-button>
            <el-button link type="success" @click="downloadScript(row)">下载</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @current-change="loadData"
          @size-change="loadData"
        />
      </div>
    </el-card>

    <!-- 详情对话框 -->
    <el-dialog v-model="detailVisible" title="脚本详情" width="760px" top="6vh">
      <div class="detail-meta">
        <el-tag size="small" :type="typeTag(detail.script_type)">{{ typeLabel(detail.script_type) }}</el-tag>
        <span class="meta-item">语言: {{ detail.language || '-' }}</span>
        <span class="meta-item">框架: {{ detail.framework || '-' }}</span>
        <span class="meta-item">创建时间: {{ fmtTime(detail.created_at) }}</span>
      </div>
      <div v-if="detail.description" class="detail-desc">{{ detail.description }}</div>
      <pre class="code-block">{{ detail.content }}</pre>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button type="primary" @click="downloadScript(detail)">下载脚本</el-button>
      </template>
    </el-dialog>

    <!-- 编辑对话框 -->
    <el-dialog v-model="editVisible" title="编辑脚本" width="760px" top="6vh">
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="脚本名称">
          <el-input v-model="editForm.name" placeholder="脚本名称" maxlength="200" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" placeholder="脚本描述（可选）" maxlength="500" />
        </el-form-item>
        <el-form-item label="脚本内容">
          <el-input v-model="editForm.content" type="textarea" :rows="18" class="code-textarea" spellcheck="false" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { scriptApi, projectApi } from '@/api'

const loading = ref(false)
const saving = ref(false)
const list = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const filterType = ref('')
const filterProject = ref<number | ''>('')
const projects = ref<any[]>([])

const detailVisible = ref(false)
const detail = ref<any>({})
const editVisible = ref(false)
const editForm = ref<any>({ id: 0, name: '', description: '', content: '' })

const typeMap: Record<string, { label: string; tag: string }> = {
  pytest: { label: 'pytest', tag: 'primary' },
  api: { label: '接口自动化', tag: 'success' },
  ui: { label: 'UI 自动化', tag: 'warning' },
  custom: { label: '自定义', tag: 'info' },
}
const typeLabel = (t: string) => typeMap[t]?.label || t || '-'
const typeTag = (t: string) => (typeMap[t]?.tag as any) || 'info'
const fmtTime = (s: string) => (s ? String(s).replace('T', ' ').slice(0, 19) : '-')

const loadProjects = async () => {
  try {
    const data = await projectApi.list({ page: 1, page_size: 100 })
    projects.value = data?.list ?? []
  } catch {
    projects.value = []
  }
}

const loadData = async () => {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize.value }
    if (filterType.value) params.script_type = filterType.value
    if (filterProject.value) params.project_id = filterProject.value
    const data = await scriptApi.list(params)
    list.value = data?.list ?? []
    total.value = data?.total ?? 0
  } catch (e: any) {
    ElMessage.error(e?.message || '加载脚本列表失败')
  } finally {
    loading.value = false
  }
}

const viewDetail = (row: any) => {
  detail.value = row
  detailVisible.value = true
}

const openEdit = (row: any) => {
  editForm.value = { id: row.id, name: row.name, description: row.description || '', content: row.content }
  editVisible.value = true
}

const saveEdit = async () => {
  if (!editForm.value.name.trim()) {
    ElMessage.warning('请输入脚本名称')
    return
  }
  if (!editForm.value.content.trim()) {
    ElMessage.warning('请输入脚本内容')
    return
  }
  saving.value = true
  try {
    await scriptApi.update(editForm.value.id, {
      name: editForm.value.name.trim(),
      description: editForm.value.description || null,
      content: editForm.value.content,
    })
    ElMessage.success('保存成功')
    editVisible.value = false
    loadData()
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

const handleDelete = async (row: any) => {
  await ElMessageBox.confirm(`确定删除脚本「${row.name}」吗？`, '删除确认', { type: 'warning' })
  try {
    await scriptApi.remove(row.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

const downloadScript = async (row: any) => {
  try {
    const blob: Blob = await scriptApi.download(row.id)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${row.name || 'script'}.py`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    ElMessage.error(e?.message || '下载失败')
  }
}

onMounted(() => {
  loadProjects()
  loadData()
})
</script>

<style scoped>
.scripts-page {
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
.detail-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
  color: #606266;
  font-size: 13px;
}
.detail-desc {
  background: #f5f7fa;
  border-radius: 4px;
  padding: 10px 12px;
  color: #606266;
  font-size: 13px;
  margin-bottom: 12px;
}
.code-block {
  background: #0d1117;
  color: #c9d1d9;
  border-radius: 6px;
  padding: 16px;
  max-height: 55vh;
  overflow: auto;
  font-family: 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre;
  word-break: normal;
}
.code-textarea :deep(textarea) {
  font-family: 'JetBrains Mono', Consolas, Menlo, monospace;
  font-size: 13px;
  line-height: 1.6;
}
</style>
