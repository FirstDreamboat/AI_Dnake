<template>
  <div class="test-points-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-button size="small" @click="goBack">
              <el-icon><Back /></el-icon>返回
            </el-button>
            <span class="page-title">测试点管理</span>
          </div>
          <div>
            <el-button type="primary" size="small" @click="openCreate">新增测试点</el-button>
          </div>
        </div>
      </template>

      <el-form inline class="mb16">
        <el-form-item label="类型">
          <el-select v-model="filterType" clearable placeholder="全部类型" style="width: 160px" @change="loadData">
            <el-option v-for="(t, k) in typeMap" :key="k" :label="t" :value="k" />
          </el-select>
        </el-form-item>
      </el-form>

      <el-table :data="list" border stripe v-loading="loading">
        <el-table-column type="index" label="#" width="50" />
        <el-table-column prop="name" label="测试点内容" min-width="260" show-overflow-tooltip />
        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-tag :type="typeColor[row.type] || 'info'" size="small">{{ typeMap[row.type] || row.type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="220" show-overflow-tooltip />
        <el-table-column prop="created_at" label="创建时间" width="170">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        class="mt16"
        layout="total, prev, pager, next"
        :total="total"
        :page-size="pageSize"
        :current-page="page"
        @current-change="(p: number) => { page = p; loadData() }"
      />
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑测试点' : '新增测试点'" width="560px">
      <el-form :model="form" label-width="90px">
        <el-form-item v-if="!editing" label="所属文档" required>
          <el-select v-model="form.document_id" style="width: 100%">
            <el-option v-for="d in docs" :key="d.id" :label="d.title" :value="d.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="测试点内容" required>
          <el-input v-model="form.name" placeholder="如：登录成功后应跳转到首页" />
        </el-form-item>
        <el-form-item label="类型" required>
          <el-select v-model="form.type" style="width: 100%">
            <el-option v-for="(t, k) in typeMap" :key="k" :label="t" :value="k" />
          </el-select>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="补充测试点说明" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { documentApi, testPointApi } from '@/api'

const route = useRoute()
const router = useRouter()
const projectId = Number(route.params.id)

// 返回上一级；测试点管理的唯一入口是需求文档页（/projects/:id/documents）。
// 若上一页是本站其他有效页面则返回，否则（直链打开/刷新/历史循环）直接回到需求文档页
const goBack = () => {
  const back = window.history.state?.back || ''
  const isValidPrev = back && !back.includes('/test-points') && back !== window.location.pathname
  if (isValidPrev) {
    router.back()
  } else {
    router.push(`/projects/${projectId}/documents`)
  }
}

const typeMap: Record<string, string> = {
  function: '功能测试',
  boundary: '边界测试',
  exception: '异常测试',
  performance: '性能测试',
  security: '安全测试',
  implicit: '隐式场景',
}
const typeColor: Record<string, string> = {
  function: 'primary',
  boundary: 'warning',
  exception: 'danger',
  performance: 'success',
  security: 'purple',
  implicit: 'info',
}

const loading = ref(false)
const saving = ref(false)
const list = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const filterType = ref('')
const docs = ref<any[]>([])

const dialogVisible = ref(false)
const editing = ref<any>(null)
const form = reactive({ document_id: 0, name: '', type: 'function', description: '' })

const fmtTime = (t?: string) => (t ? t.replace('T', ' ').slice(0, 19) : '-')

const loadData = async () => {
  loading.value = true
  try {
    const [pointsRes, docsRes] = await Promise.all([
      testPointApi.list({ project_id: projectId, type: filterType.value || undefined, page: page.value, page_size: pageSize }),
      documentApi.list({ project_id: projectId, page_size: 200 }),
    ])
    const data = pointsRes?.data ?? pointsRes
    list.value = data.list ?? []
    total.value = data.total ?? 0
    const dData = docsRes?.data ?? docsRes
    docs.value = dData.list ?? []
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

const openCreate = () => {
  editing.value = null
  Object.assign(form, { document_id: docs.value[0]?.id ?? 0, name: '', type: 'function', description: '' })
  dialogVisible.value = true
}

const openEdit = (row: any) => {
  editing.value = row
  Object.assign(form, { name: row.name, type: row.type, description: row.description || '' })
  dialogVisible.value = true
}

const handleSave = async () => {
  if (!form.name.trim()) {
    ElMessage.warning('请输入测试点内容')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      await testPointApi.update(editing.value.id, { name: form.name, type: form.type, description: form.description })
      ElMessage.success('更新成功')
    } else {
      await testPointApi.create({
        document_id: form.document_id,
        project_id: projectId,
        name: form.name,
        type: form.type,
        description: form.description,
      })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    loadData()
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    saving.value = false
  }
}

const handleDelete = async (row: any) => {
  await ElMessageBox.confirm(`确定删除测试点「${row.name}」吗？`, '提示', { type: 'warning' })
  try {
    await testPointApi.remove(row.id)
    ElMessage.success('删除成功')
    loadData()
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

onMounted(loadData)
</script>

<style scoped>
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
.page-title {
  font-size: 15px;
  font-weight: 600;
}
.mb16 {
  margin-bottom: 16px;
}
.mt16 {
  margin-top: 16px;
}
</style>
