<template>
  <div class="req-review-page">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>需求质量体检</span>
          <span class="sub">上传 PRD / 需求文档，AI 在提测前给出需求质量评分与问题清单；报告留存，可随时查看与下载 PDF</span>
        </div>
      </template>

      <el-upload
        drag
        :auto-upload="false"
        :limit="1"
        :on-exceed="onExceed"
        :on-change="onChange"
        :on-remove="onRemove"
        v-model:file-list="fileList"
        accept=".md,.txt,.docx,.doc,.pdf,.png,.jpg,.jpeg,.webp,.gif"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">将需求文档拖到此处，或<em>点击上传</em></div>
        <template #tip>
          <div class="upload-tip">支持 md / txt / docx / pdf / 图片；体检约 1-2 分钟，报告自动留存</div>
        </template>
      </el-upload>

      <div class="actions">
        <el-button type="primary" :loading="loading" :disabled="!file" @click="startReview">
          <el-icon><Aim /></el-icon>开始体检
        </el-button>
      </div>
    </el-card>

    <!-- 当前体检结果 -->
    <el-card v-if="report" shadow="never" class="result-card">
      <template #header>
        <div class="card-header">
          <span>体检报告</span>
          <el-button type="primary" size="small" @click="download(report.id)">
            <el-icon><Download /></el-icon>下载 PDF
          </el-button>
        </div>
      </template>
      <ReportView :report="report" />
    </el-card>

    <!-- 历史报告 -->
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span>历史体检报告</span>
          <el-button size="small" @click="loadHistory">
            <el-icon><Refresh /></el-icon>刷新
          </el-button>
        </div>
      </template>
      <el-table :data="history" border stripe v-loading="histLoading" size="small">
        <el-table-column prop="filename" label="文件名" min-width="220" show-overflow-tooltip />
        <el-table-column label="评分" width="90">
          <template #default="{ row }">
            <span :class="['score-cell', scoreClass(row.score)]">{{ row.score }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="summary" label="总体评价" min-width="280" show-overflow-tooltip />
        <el-table-column label="体检时间" width="160">
          <template #default="{ row }">{{ fmtTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewDetail(row.id)">查看</el-button>
            <el-button link type="success" @click="download(row.id)">下载 PDF</el-button>
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
          @current-change="loadHistory"
          @size-change="loadHistory"
        />
      </div>
    </el-card>

    <!-- 历史详情弹窗 -->
    <el-dialog v-model="detailVisible" title="体检报告详情" width="900px" top="5vh">
      <ReportView v-if="detail" :report="detail" />
      <div v-else style="text-align: center; padding: 40px">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Aim, Download, Loading, Refresh, UploadFilled } from '@element-plus/icons-vue'
import { reqReviewApi } from '@/api'
import ReportView from '@/components/ReportView.vue'

const fileList = ref<any[]>([])
const file = ref<File | null>(null)
const loading = ref(false)
const report = ref<any>(null)

// 历史列表
const history = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const histLoading = ref(false)

// 详情
const detailVisible = ref(false)
const detail = ref<any>(null)

const onChange = (uploadFile: any) => {
  if (uploadFile.raw) file.value = uploadFile.raw
}
const onRemove = () => {
  file.value = null
}
const onExceed = () => {
  ElMessage.warning('一次只能体检一个文档')
}

const startReview = async () => {
  if (!file.value) {
    ElMessage.warning('请先上传需求文档')
    return
  }
  loading.value = true
  report.value = null
  try {
    const data = await reqReviewApi.analyze(file.value)
    report.value = data
    ElMessage.success('体检完成，报告已留存')
    loadHistory()
  } catch (e: any) {
    ElMessage.error(e?.message || '体检失败')
  } finally {
    loading.value = false
  }
}

const loadHistory = async () => {
  histLoading.value = true
  try {
    const data = await reqReviewApi.list({ page: page.value, page_size: pageSize.value })
    history.value = data?.list ?? []
    total.value = data?.total ?? 0
  } catch (e: any) {
    ElMessage.error(e?.message || '加载历史报告失败')
  } finally {
    histLoading.value = false
  }
}

const viewDetail = async (id: number) => {
  detail.value = null
  detailVisible.value = true
  try {
    detail.value = await reqReviewApi.detail(id)
  } catch (e: any) {
    ElMessage.error(e?.message || '加载详情失败')
  }
}

const download = async (id: number) => {
  if (!id) return
  try {
    const blob = await reqReviewApi.download(id)
    const url = window.URL.createObjectURL(blob as any)
    const a = document.createElement('a')
    a.href = url
    a.download = '需求体检报告.pdf'
    a.click()
    window.URL.revokeObjectURL(url)
  } catch (e: any) {
    ElMessage.error(e?.message || '下载失败')
  }
}

const fmtTime = (t?: string) => (t ? String(t).replace('T', ' ').slice(0, 19) : '-')
const scoreClass = (s: number) => (s >= 85 ? 'good' : s >= 70 ? 'mid' : 'bad')

onMounted(loadHistory)
</script>

<style scoped>
.req-review-page {
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.card-header .sub {
  font-size: 12px;
  color: #909399;
  font-weight: normal;
}
.actions {
  margin-top: 16px;
}
.upload-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 6px;
}
.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
.score-cell {
  font-weight: 700;
  font-size: 16px;
}
.score-cell.good {
  color: #67c23a;
}
.score-cell.mid {
  color: #e6a23c;
}
.score-cell.bad {
  color: #f56c6c;
}
</style>
