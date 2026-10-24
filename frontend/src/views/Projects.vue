<template>
  <div>
    <el-card shadow="never" class="mb16">
      <div class="toolbar">
        <el-input
          v-model="query.keyword"
          placeholder="搜索项目名称"
          clearable
          style="width: 220px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-select v-model="query.product_line" placeholder="产品线" clearable style="width: 160px" @change="handleSearch">
          <el-option label="楼宇对讲" value="intercom" />
          <el-option label="智能家居" value="smart_home" />
          <el-option label="医院" value="hospital" />
        </el-select>
        <el-select v-model="query.status" placeholder="状态" clearable style="width: 140px" @change="handleSearch">
          <el-option label="进行中" value="active" />
          <el-option label="已归档" value="archived" />
        </el-select>
        <el-button type="primary" @click="handleSearch">
          <el-icon><Search /></el-icon>查询
        </el-button>
        <div class="flex-1"></div>
        <el-button type="primary" @click="openCreate">
          <el-icon><Plus /></el-icon>新建项目
        </el-button>
      </div>
    </el-card>

    <el-card shadow="never">
      <el-table :data="list" v-loading="loading" border stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="项目名称" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <el-link type="primary" @click="goDetail(row)">{{ row.name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="产品线" width="120">
          <template #default="{ row }">
            <el-tag :type="productLineMap[row.product_line]?.type ?? 'info'" size="small">
              {{ productLineMap[row.product_line]?.label ?? row.product_line }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'" size="small">
              {{ row.status === 'active' ? '进行中' : '已归档' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="文档数" width="90" align="center">
          <template #default="{ row }">{{ row.stats?.document_count ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="用例数" width="90" align="center">
          <template #default="{ row }">{{ row.stats?.test_case_count ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="生成任务" width="90" align="center">
          <template #default="{ row }">{{ row.stats?.task_count ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="覆盖率" width="110" align="center">
          <template #default="{ row }">
            <el-progress :percentage="row.stats?.coverage ?? 0" :stroke-width="10" />
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.description || '-' }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }">{{ (row.created_at || '').replace('T', ' ').slice(0, 19) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="goDocuments(row)">需求文档</el-button>
            <el-button link type="success" @click="goCases(row)">测试用例</el-button>
            <el-button link type="warning" @click="goCaseFiles(row)">测试用例管理</el-button>
            <el-button link type="warning" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="row.status === 'active'" link type="info" @click="handleArchive(row)">归档</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="mt16"
        layout="total, prev, pager, next, sizes"
        :total="total"
        :current-page="query.page"
        :page-size="query.page_size"
        :page-sizes="[10, 20, 50]"
        @current-change="handlePageChange"
        @size-change="handleSizeChange"
      />
    </el-card>

    <!-- 新建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑项目' : '新建项目'" width="480px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="项目名称" prop="name">
          <el-input v-model="form.name" placeholder="请输入项目名称" maxlength="100" />
        </el-form-item>
        <el-form-item label="产品线" prop="product_line">
          <el-select v-model="form.product_line" placeholder="请选择产品线" style="width: 100%">
            <el-option label="楼宇对讲" value="intercom" />
            <el-option label="智能家居" value="smart_home" />
            <el-option label="医院" value="hospital" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述" prop="description">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="请输入项目描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { projectApi } from '@/api'

const router = useRouter()

const productLineMap: Record<string, { label: string; type: string }> = {
  intercom: { label: '楼宇对讲', type: 'primary' },
  smart_home: { label: '智能家居', type: 'success' },
  hospital: { label: '医院', type: 'warning' },
}

const list = ref<any[]>([])
const total = ref(0)
const loading = ref(false)
const query = reactive({ page: 1, page_size: 10, keyword: '', product_line: '', status: '' })

const loadData = async () => {
  loading.value = true
  try {
    const params: any = { page: query.page, page_size: query.page_size }
    if (query.keyword) params.keyword = query.keyword
    if (query.product_line) params.product_line = query.product_line
    if (query.status) params.status = query.status
    const data = await projectApi.list(params)
    list.value = data.list
    total.value = data.total
  } finally {
    loading.value = false
  }
}

const handleSearch = () => {
  query.page = 1
  loadData()
}

const handlePageChange = (page: number) => {
  query.page = page
  loadData()
}

const handleSizeChange = (size: number) => {
  query.page_size = size
  query.page = 1
  loadData()
}

const goDetail = (row: any) => router.push(`/projects/${row.id}/documents`)
const goDocuments = (row: any) => router.push(`/projects/${row.id}/documents`)
const goCases = (row: any) => router.push(`/projects/${row.id}/cases`)
const goCaseFiles = (row: any) => router.push(`/projects/${row.id}/case-files`)

// 新建/编辑
const dialogVisible = ref(false)
const saving = ref(false)
const formRef = ref<FormInstance>()
const form = reactive({ id: 0, name: '', product_line: '', description: '' })

const rules: FormRules = {
  name: [{ required: true, message: '请输入项目名称', trigger: 'blur' }],
  product_line: [{ required: true, message: '请选择产品线', trigger: 'change' }],
}

const openCreate = () => {
  form.id = 0
  form.name = ''
  form.product_line = ''
  form.description = ''
  dialogVisible.value = true
}

const openEdit = (row: any) => {
  form.id = row.id
  form.name = row.name
  form.product_line = row.product_line
  form.description = row.description || ''
  dialogVisible.value = true
}

const handleSubmit = async () => {
  if (!formRef.value) return
  await formRef.value.validate()
  saving.value = true
  try {
    const payload = { name: form.name, product_line: form.product_line, description: form.description || null }
    if (form.id) {
      await projectApi.update(form.id, payload)
      ElMessage.success('项目更新成功')
    } else {
      await projectApi.create(payload)
      ElMessage.success('项目创建成功')
    }
    dialogVisible.value = false
    loadData()
  } finally {
    saving.value = false
  }
}

const handleArchive = async (row: any) => {
  await ElMessageBox.confirm(`确认归档项目「${row.name}」？归档后不再参与日常生成。`, '提示', { type: 'warning' })
  await projectApi.archive(row.id)
  ElMessage.success('项目已归档')
  loadData()
}

const handleDelete = async (row: any) => {
  await ElMessageBox.confirm(`确认删除项目「${row.name}」？该操作将同时删除其下的文档、测试点与用例，不可恢复！`, '警告', {
    type: 'warning',
    confirmButtonText: '删除',
    confirmButtonClass: 'el-button--danger',
  })
  await projectApi.remove(row.id)
  ElMessage.success('删除成功')
  loadData()
}

onMounted(loadData)
</script>

<style scoped>
.mb16 {
  margin-bottom: 16px;
}

.mt16 {
  margin-top: 16px;
  justify-content: flex-end;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.flex-1 {
  flex: 1;
}
</style>
