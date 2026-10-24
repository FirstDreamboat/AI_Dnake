<template>
  <div class="case-files">
    <div class="page-head">
      <div class="crumb">
        <el-button link type="primary" @click="router.push('/projects')">← 返回项目管理</el-button>
        <span class="divider">|</span>
        <span class="title">测试用例管理</span>
        <span class="proj">/ {{ projectName }}</span>
      </div>
      <el-button type="primary" :icon="Upload" @click="uploadVisible = true">上传用例表</el-button>
    </div>

    <el-table :data="list" v-loading="loading" border stripe>
      <el-table-column prop="filename" label="文件名" min-width="260">
        <template #default="{ row }">
          <el-link type="primary" :underline="false" @click="openFile(row)">📄 {{ row.filename }}</el-link>
        </template>
      </el-table-column>
      <el-table-column label="大小" width="100">
        <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
      </el-table-column>
      <el-table-column prop="uploaded_by_name" label="上传人" width="110">
        <template #default="{ row }">{{ row.uploaded_by_name || '-' }}</template>
      </el-table-column>
      <el-table-column label="更新时间" width="170">
        <template #default="{ row }">{{ (row.updated_at || '').slice(0, 19) }}</template>
      </el-table-column>
      <el-table-column label="状态" width="160">
        <template #default="{ row }">
          <el-tag v-if="row.lock.locked && row.lock.by_me" type="primary">我正在编辑</el-tag>
          <el-tag v-else-if="row.lock.locked" type="warning">🔒 {{ row.lock.holder_name }} 正在编辑</el-tag>
          <el-tag v-else type="success">可编辑</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button link type="info" @click="previewFile(row)">预览</el-button>
          <el-button link type="primary" @click="openFile(row)">
            {{ row.lock.locked && !row.lock.by_me ? '查看(只读)' : '打开编辑' }}
          </el-button>
          <el-button link type="primary" @click="download(row)">下载</el-button>
          <el-button v-if="row.can_delete" link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-if="!loading && list.length === 0" description="暂无用例文件，点击右上角上传">
      <el-button type="primary" :icon="Upload" @click="uploadVisible = true">上传用例表</el-button>
    </el-empty>

    <!-- 上传弹窗 -->
    <el-dialog v-model="uploadVisible" title="上传用例表" width="520px" @closed="resetUpload">
      <el-upload drag :auto-upload="false" :limit="1" :on-change="onPickFile" :on-remove="() => (pickFile = null)"
                 accept=".xlsx,.csv">
        <el-icon size="36" color="#c0c4cc"><UploadFilled /></el-icon>
        <div>将文件拖到此处，或 <em>点击选择文件</em></div>
        <template #tip>
          <div class="upload-tip">支持 .xlsx / .csv（csv 自动转为 xlsx），单个 ≤ 10MB；在线编辑保存后仅保留单元格文本内容</div>
        </template>
      </el-upload>
      <el-checkbox v-model="openAfterUpload" style="margin-top: 12px">上传完成后直接进入全屏编辑</el-checkbox>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" :disabled="!pickFile" @click="handleUpload">开始上传</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, UploadFilled } from '@element-plus/icons-vue'
import { caseFileApi } from '@/api'

const route = useRoute()
const router = useRouter()
const projectId = Number(route.params.id)
const projectName = (route.query.name as string) || `项目 #${projectId}`

const list = ref<any[]>([])
const loading = ref(false)
const uploadVisible = ref(false)
const uploading = ref(false)
const pickFile = ref<File | null>(null)
const openAfterUpload = ref(true)

const loadList = async () => {
  loading.value = true
  try {
    const res: any = await caseFileApi.list(projectId)
    list.value = res?.data ?? res ?? []
  } finally {
    loading.value = false
  }
}

const onPickFile = (file: any) => {
  pickFile.value = file.raw
}

const resetUpload = () => {
  pickFile.value = null
  openAfterUpload.value = true
}

const handleUpload = async () => {
  if (!pickFile.value) return
  uploading.value = true
  try {
    const res: any = await caseFileApi.upload(projectId, pickFile.value)
    ElMessage.success(res?.message || '上传成功')
    uploadVisible.value = false
    await loadList()
    const created = res?.data
    if (openAfterUpload.value && created?.id) {
      router.push(`/case-file-editor/${created.id}?project_id=${projectId}&name=${encodeURIComponent(created.filename)}`)
    }
  } finally {
    uploading.value = false
  }
}

const openFile = (row: any) => {
  router.push(`/case-file-editor/${row.id}?project_id=${projectId}&name=${encodeURIComponent(row.filename)}`)
}

const previewFile = (row: any) => {
  router.push(`/case-file-editor/${row.id}?project_id=${projectId}&preview=1&name=${encodeURIComponent(row.filename)}`)
}

const download = async (row: any) => {
  const blob: any = await caseFileApi.download(row.id)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = row.filename
  a.click()
  URL.revokeObjectURL(url)
}

const handleDelete = async (row: any) => {
  await ElMessageBox.confirm(`确认删除「${row.filename}」？删除后不可恢复！`, '警告', {
    type: 'warning',
    confirmButtonText: '删除',
  })
  await caseFileApi.remove(row.id)
  ElMessage.success('删除成功')
  loadList()
}

const formatSize = (n: number) => (n >= 1024 * 1024 ? `${(n / 1024 / 1024).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`)

onMounted(loadList)
</script>

<style scoped>
.case-files { padding: 20px; }
.page-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.crumb { display: flex; align-items: center; gap: 8px; font-size: 15px; }
.crumb .divider { color: #dcdfe6; }
.crumb .title { font-weight: bold; color: #303133; }
.crumb .proj { color: #909399; font-size: 13px; }
.upload-tip { font-size: 12px; color: #909399; margin-top: 8px; line-height: 1.6; }
</style>
