<template>
  <div class="templates-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <span>脚本模板管理（FR-6.4 自定义模板）</span>
            <el-select v-model="filterType" placeholder="全部类型" clearable style="width: 150px" @change="loadData">
              <el-option label="pytest" value="pytest" />
              <el-option label="接口自动化" value="api" />
              <el-option label="UI 自动化" value="ui" />
              <el-option label="安卓APP自动化" value="android" />
              <el-option label="iOS APP自动化" value="ios" />
              <el-option label="自定义" value="custom" />
            </el-select>
            <el-input
              v-model="filterKeyword"
              placeholder="按名称搜索"
              clearable
              style="width: 200px"
              @keyup.enter="loadData"
              @clear="loadData"
            />
          </div>
          <div>
            <el-button type="primary" @click="openCreate">
              <el-icon><Plus /></el-icon>新建模板
            </el-button>
            <el-button @click="loadData">
              <el-icon><Refresh /></el-icon>刷新
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="list" border stripe v-loading="loading">
        <el-table-column prop="name" label="模板名称" min-width="180" show-overflow-tooltip />
        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="typeTag(row.script_type)">{{ typeLabel(row.script_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="framework" label="框架" width="130">
          <template #default="{ row }">{{ row.framework || '-' }}</template>
        </el-table-column>
        <el-table-column prop="language" label="语言" width="90" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.is_active ? 'success' : 'info'">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || '-' }}</template>
        </el-table-column>
        <el-table-column prop="updated_at" label="更新时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewDetail(row)">查看</el-button>
            <el-button link type="warning" @click="openEdit(row)">编辑</el-button>
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
    <el-dialog v-model="detailVisible" title="模板详情" width="820px" top="6vh">
      <div class="detail-meta">
        <el-tag size="small" :type="typeTag(detail.script_type)">{{ typeLabel(detail.script_type) }}</el-tag>
        <span class="meta-item">框架: {{ detail.framework || '-' }}</span>
        <span class="meta-item">语言: {{ detail.language || '-' }}</span>
        <el-tag size="small" :type="detail.is_active ? 'success' : 'info'">
          {{ detail.is_active ? '启用' : '停用' }}
        </el-tag>
      </div>
      <div v-if="detail.description" class="detail-desc">{{ detail.description }}</div>
      <pre class="code-block">{{ detail.template_content }}</pre>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 新建/编辑对话框 -->
    <el-dialog
      v-model="editVisible"
      :title="editForm.id ? '编辑模板' : '新建模板'"
      width="860px"
      top="4vh"
    >
      <el-form :model="editForm" label-width="90px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="模板名称" required>
              <el-input v-model="editForm.name" placeholder="如: 狄耐克设备 pytest 模板" maxlength="100" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="脚本类型" required>
              <el-select v-model="editForm.script_type" style="width: 100%">
                <el-option label="pytest" value="pytest" />
                <el-option label="接口自动化" value="api" />
                <el-option label="UI 自动化" value="ui" />
                <el-option label="安卓APP自动化" value="android" />
                <el-option label="iOS APP自动化" value="ios" />
                <el-option label="自定义" value="custom" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="框架">
              <el-input v-model="editForm.framework" placeholder="如: pytest + requests / Selenium" maxlength="50" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="语言">
              <el-select v-model="editForm.language" style="width: 100%">
                <el-option label="python" value="python" />
                <el-option label="java" value="java" />
                <el-option label="javascript" value="javascript" />
                <el-option label="go" value="go" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="状态">
          <el-switch v-model="editForm.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" placeholder="模板用途说明（可选）" maxlength="500" />
        </el-form-item>
        <el-form-item label="模板代码" required>
          <el-input
            v-model="editForm.template_content"
            type="textarea"
            :rows="18"
            class="code-textarea"
            spellcheck="false"
            placeholder="# 在此编写模板代码骨架&#10;# 可包含 import、常量、fixture、辅助函数与占位说明&#10;# AI 生成时将保留模板固定结构并填充对应用例实现"
          />
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
import { scriptTemplateApi } from '@/api'

const loading = ref(false)
const saving = ref(false)
const list = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const filterType = ref('')
const filterKeyword = ref('')

const detailVisible = ref(false)
const detail = ref<any>({})
const editVisible = ref(false)
const editForm = ref<any>({
  id: 0,
  name: '',
  script_type: 'custom',
  language: 'python',
  framework: '',
  template_content: '',
  description: '',
  is_active: true,
})

const typeMap: Record<string, { label: string; tag: string }> = {
  pytest: { label: 'pytest', tag: 'primary' },
  api: { label: '接口自动化', tag: 'success' },
  ui: { label: 'UI 自动化', tag: 'warning' },
  android: { label: '安卓APP自动化', tag: 'danger' },
  ios: { label: 'iOS APP自动化', tag: 'danger' },
  custom: { label: '自定义', tag: 'info' },
}
const typeLabel = (t: string) => typeMap[t]?.label || t || '-'
const typeTag = (t: string) => (typeMap[t]?.tag as any) || 'info'
const fmtTime = (s: string) => (s ? String(s).replace('T', ' ').slice(0, 19) : '-')

const loadData = async () => {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize.value }
    if (filterType.value) params.script_type = filterType.value
    if (filterKeyword.value) params.keyword = filterKeyword.value.trim()
    const data = await scriptTemplateApi.list(params)
    list.value = data?.list ?? []
    total.value = data?.total ?? 0
  } catch (e: any) {
    ElMessage.error(e?.message || '加载模板列表失败')
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  editForm.value = {
    id: 0,
    name: '',
    script_type: 'custom',
    language: 'python',
    framework: '',
    template_content: '',
    description: '',
    is_active: true,
  }
}

const openCreate = () => {
  resetForm()
  editVisible.value = true
}

const openEdit = (row: any) => {
  editForm.value = {
    id: row.id,
    name: row.name,
    script_type: row.script_type,
    language: row.language,
    framework: row.framework || '',
    template_content: row.template_content,
    description: row.description || '',
    is_active: row.is_active,
  }
  editVisible.value = true
}

const viewDetail = (row: any) => {
  detail.value = row
  detailVisible.value = true
}

const saveEdit = async () => {
  if (!editForm.value.name.trim()) {
    ElMessage.warning('请输入模板名称')
    return
  }
  if (!editForm.value.template_content.trim()) {
    ElMessage.warning('请输入模板代码')
    return
  }
  saving.value = true
  try {
    const payload: any = {
      name: editForm.value.name.trim(),
      script_type: editForm.value.script_type,
      language: editForm.value.language,
      framework: editForm.value.framework || null,
      template_content: editForm.value.template_content,
      description: editForm.value.description || null,
      is_active: editForm.value.is_active,
    }
    if (editForm.value.id) {
      await scriptTemplateApi.update(editForm.value.id, payload)
    } else {
      await scriptTemplateApi.create(payload)
    }
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
  await ElMessageBox.confirm(`确定删除模板「${row.name}」吗？`, '删除确认', { type: 'warning' })
  try {
    await scriptTemplateApi.remove(row.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

onMounted(loadData)
</script>

<style scoped>
.templates-page {
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
  max-height: 60vh;
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
