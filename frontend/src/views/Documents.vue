<template>
  <div>
    <el-card shadow="never" class="mb16">
      <div class="doc-actions">
        <el-button @click="router.back()">
          <el-icon><Back /></el-icon>返回
        </el-button>
        <div class="flex-1"></div>
        <el-button @click="router.push(`/projects/${projectId}/test-points`)">
          <el-icon><List /></el-icon>测试点
        </el-button>
        <el-button @click="urlVisible = true">
          <el-icon><Link /></el-icon>链接导入
        </el-button>
        <el-upload
          :show-file-list="false"
          :before-upload="handleUpload"
          accept=".pdf,.docx,.doc,.txt,.md"
        >
          <el-button type="primary">
            <el-icon><Upload /></el-icon>上传需求文档
          </el-button>
        </el-upload>
        <el-upload
          :show-file-list="false"
          :before-upload="handleImageUpload"
          accept=".png,.jpg,.jpeg,.gif,.webp,.bmp,.rp"
        >
          <el-button type="warning">
            <el-icon><Picture /></el-icon>上传原型图
          </el-button>
        </el-upload>
      </div>
    </el-card>

    <!-- 平台链接导入 (FR-1.2) -->
    <el-dialog v-model="urlVisible" title="平台链接导入" width="520px">
      <el-form :model="urlForm" label-width="70px">
        <el-form-item label="链接" required>
          <el-input v-model="urlForm.url" placeholder="https://xxx.feishu.cn/... 或 语雀/通用网页链接" />
        </el-form-item>
        <el-form-item label="标题">
          <el-input v-model="urlForm.title" placeholder="留空则自动从页面提取" />
        </el-form-item>
      </el-form>
      <el-alert
        type="info"
        :closable="false"
        title="支持通用网页与飞书/语雀等公开分享链接；需要登录的平台（TAPD/Confluence）可能无法抓取。"
      />
      <template #footer>
        <el-button @click="urlVisible = false">取消</el-button>
        <el-button type="primary" :loading="urlLoading" @click="handleParseUrl">解析并保存</el-button>
      </template>
    </el-dialog>

    <el-table :data="list" v-loading="loading" border stripe>
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="title" label="文档标题" min-width="220" />
      <el-table-column prop="file_type" label="格式" width="110">
        <template #default="{ row }">
          <el-tag size="small" :type="isPrototypeType(row.file_type) ? 'warning' : ''">
            {{ isPrototypeType(row.file_type) ? '原型图' : row.file_type.toUpperCase() }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="来源" width="130">
        <template #default="{ row }">
          <el-tag v-if="row.source_type === 'url'" size="small" type="success">平台链接</el-tag>
          <el-tag v-else size="small" type="info">本地上传</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="解析状态" width="110">
        <template #default="{ row }">
          <el-tag :type="statusMap[row.parse_status]?.type ?? 'info'" size="small">
            {{ statusMap[row.parse_status]?.label ?? row.parse_status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="上传时间" width="170">
        <template #default="{ row }">{{ (row.created_at || '').replace('T', ' ').slice(0, 19) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="handleParse(row)">解析</el-button>
          <el-button v-if="!isPrototypeType(row.file_type)" link type="success" @click="goGenerate(row)">生成用例</el-button>
          <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { documentApi } from '@/api'

const route = useRoute()
const router = useRouter()
const projectId = Number(route.params.id)

const urlVisible = ref(false)
const urlLoading = ref(false)
const urlForm = reactive({ url: '', title: '' })

const list = ref<any[]>([])
const loading = ref(false)
const statusMap: Record<string, { label: string; type: string }> = {
  pending: { label: '待解析', type: 'info' },
  parsing: { label: '解析中', type: 'warning' },
  done: { label: '已解析', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}

const loadData = async () => {
  loading.value = true
  try {
    const data = await documentApi.list({ project_id: projectId, page_size: 100 })
    list.value = data.list
  } finally {
    loading.value = false
  }
}

const imageTypes = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp']
const isImageType = (ft: string) => imageTypes.includes((ft || '').toLowerCase())
// 原型图类型：图片 + Axure .rp 工程文件（可上传存储，但无法直接文本解析生成用例）
const prototypeTypes = ['rp', ...imageTypes]
const isPrototypeType = (ft: string) => prototypeTypes.includes((ft || '').toLowerCase())

const handleUpload = async (file: File) => {
  await documentApi.upload(projectId, file)
  ElMessage.success('上传成功')
  loadData()
  return false
}

const handleImageUpload = async (file: File) => {
  await documentApi.upload(projectId, file)
  ElMessage.success('原型图上传成功')
  loadData()
  return false
}

const handleParse = async (row: any) => {
  const res = await documentApi.parse(row.id)
  ElMessage.success(`解析完成，提取 ${res.chars} 字符`)
  loadData()
}

const handleParseUrl = async () => {
  if (!urlForm.url.trim()) {
    ElMessage.warning('请输入链接')
    return
  }
  urlLoading.value = true
  try {
    await documentApi.parseUrl({ project_id: projectId, url: urlForm.url.trim(), title: urlForm.title || undefined })
    ElMessage.success('链接解析成功，已保存为需求文档')
    urlVisible.value = false
    urlForm.url = ''
    urlForm.title = ''
    loadData()
  } catch (e: any) {
    ElMessage.error(e?.message || '链接解析失败')
  } finally {
    urlLoading.value = false
  }
}

const handleDelete = async (row: any) => {
  await ElMessageBox.confirm(`确认删除文档「${row.title}」？`, '提示', { type: 'warning' })
  await documentApi.remove(row.id)
  ElMessage.success('删除成功')
  loadData()
}

const goGenerate = (row: any) =>
  router.push({ path: '/generate', query: { project_id: projectId, document_id: row.id } })

onMounted(loadData)
</script>

<style scoped>
.mb16 {
  margin-bottom: 16px;
}

.doc-actions {
  display: flex;
  align-items: center;
}

.flex-1 {
  flex: 1;
}
</style>
