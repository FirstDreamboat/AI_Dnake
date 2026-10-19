<template>
  <div>
    <el-tabs v-model="activeTab">
    <el-tab-pane label="知识检索" name="search">
    <el-card shadow="never" class="mb16">
      <div class="toolbar">
        <el-input v-model="query" placeholder="输入需求描述，语义检索相似历史用例" class="search" @keyup.enter="handleSearch" />
        <el-select v-model="mode" style="width: 130px">
        <el-option label="混合检索" value="hybrid" />
        <el-option label="向量检索" value="vector" />
        <el-option label="关键词检索" value="keyword" />
      </el-select>
      <el-button type="primary" @click="handleSearch">
        <el-icon><Search /></el-icon>检索
      </el-button>
      <div class="flex-1"></div>
      <el-select v-model="selectedType" placeholder="全部分类" clearable style="width: 130px" @change="loadData">
        <el-option v-for="(label, key) in typeMap" :key="key" :label="label" :value="key" />
      </el-select>
        <div class="flex-1"></div>
        <el-button type="warning" plain @click="handleVectorizeAll">
          <el-icon><MagicStick /></el-icon>全部向量化
        </el-button>
        <el-select v-model="uploadType" style="width: 130px">
          <el-option v-for="(label, key) in typeMap" :key="key" :label="label" :value="key" />
        </el-select>
        <el-upload :show-file-list="false" :before-upload="handleUpload">
          <el-button type="primary">
            <el-icon><Upload /></el-icon>上传知识文档
          </el-button>
        </el-upload>
      </div>
    </el-card>

    <!-- 检索结果 -->
    <el-card v-if="hits.length" shadow="never" class="mb16">
      <template #header>检索结果（{{ hits.length }} 条）</template>
      <div v-for="h in hits" :key="h.doc_id + '-' + h.chunk_index" class="hit-item">
        <div class="hit-header">
          <el-tag size="small" type="success">相似度 {{ h.score }}</el-tag>
          <span class="hit-title">{{ h.title }}</span>
          <span class="hit-index">#{{ h.chunk_index }}</span>
        </div>
        <div class="hit-content">{{ h.content }}</div>
      </div>
    </el-card>

    <!-- 知识库列表 -->
    <el-card shadow="never">
      <template #header>知识库文档</template>
      <el-table :data="list" v-loading="loading" border stripe>
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            <el-tag size="small">{{ typeMap[row.doc_type] }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="版本" width="80">
          <template #default="{ row }">
            <el-tag size="small" :type="row.version > 1 ? 'warning' : 'info'">v{{ row.version }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="chunk_count" label="分块数" width="90" />
        <el-table-column label="向量状态" width="110">
          <template #default="{ row }">
            <el-tooltip v-if="row.vector_status === 'failed' && row.vector_error" :content="row.vector_error" placement="top">
              <el-tag type="danger" size="small">失败</el-tag>
            </el-tooltip>
            <el-tag v-else-if="row.vector_status === 'indexing'" type="warning" size="small">
              <el-icon class="is-loading"><Loading /></el-icon>入库中
            </el-tag>
            <el-tag v-else :type="row.vector_status === 'indexed' ? 'success' : 'info'" size="small">
              {{ row.vector_status === 'indexed' ? '已入库' : '待入库' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="handleView(row)">查看</el-button>
            <el-button link type="primary" @click="handleVersions(row)">版本</el-button>
            <el-button v-if="row.vector_status === 'failed'" link type="danger" @click="handleVectorize(row)">重试</el-button>
            <el-button v-else-if="row.vector_status !== 'indexed'" link type="warning" @click="handleVectorize(row)">向量化</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        class="pagination"
        v-model:current-page="page"
        :page-size="pageSize"
        :total="total"
        layout="total, prev, pager, next"
        @current-change="loadData"
      />
    </el-card>

    <!-- 文档内容预览 -->
    <el-dialog v-model="viewVisible" :title="viewDoc?.title" width="760px" top="6vh">
      <div class="doc-meta" v-if="viewDoc">
        <el-tag size="small">{{ typeMap[viewDoc.doc_type] }}</el-tag>
        <el-tag size="small" type="info">v{{ viewDoc.version }}</el-tag>
        <span class="doc-time">上传时间：{{ viewDoc.created_at }}</span>
      </div>
      <pre class="doc-content">{{ viewDoc?.content || '（暂无内容）' }}</pre>
    </el-dialog>

    <!-- 版本历史 -->
    <el-dialog v-model="versionVisible" :title="`版本历史 - ${versionDoc?.title || ''}`" width="720px">
      <el-table :data="versions" v-loading="versionLoading" border size="small" max-height="420">
        <el-table-column prop="version" label="版本" width="70">
          <template #default="{ row }">
            <el-tag size="small">{{ row.version === versionDoc?.version ? '当前 v' + row.version : 'v' + row.version }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="change_log" label="变更说明" min-width="180" />
        <el-table-column prop="created_at" label="时间" width="170" />
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewVersionContent(row)">查看内容</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!versionLoading && !versions.length" description="暂无历史版本（当前为 v1 初始版本）" :image-size="80" />
    </el-dialog>
    </el-tab-pane>

    <!-- ============ 知识问答（对话形式） ============ -->
    <el-tab-pane label="知识问答" name="chat">
      <el-card shadow="never">
        <div class="chat-panel">
          <div ref="chatBody" class="chat-messages">
            <el-empty v-if="!messages.length" description="基于知识库提问，AI 将检索相关文档后回答（附引用来源）" :image-size="90" />
            <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role">
              <div class="msg-avatar" :class="m.role">{{ m.role === 'user' ? '我' : 'AI' }}</div>
              <div class="msg-bubble">
                <div class="msg-text">{{ m.content }}</div>
                <div v-if="m.role === 'assistant'" class="msg-export">
                  <span class="export-label">导出：</span>
                  <el-button link type="primary" size="small" :loading="exporting === 'word'" @click="exportChat('word', m.content)">Word</el-button>
                  <el-button link type="success" size="small" :loading="exporting === 'ppt'" @click="exportChat('ppt', m.content)">PPT</el-button>
                  <el-button link type="warning" size="small" :loading="exporting === 'pdf'" @click="exportChat('pdf', m.content)">PDF</el-button>
                </div>
                <div v-if="m.sources?.length" class="msg-sources">
                  <el-collapse>
                    <el-collapse-item :title="`引用来源（${m.sources.length}）`">
                      <div v-for="(s, j) in m.sources" :key="j" class="source-item">
                        <div class="source-head">
                          <el-tag size="small" type="success">相似度 {{ s.score?.toFixed ? s.score.toFixed(2) : s.score }}</el-tag>
                          <span class="source-title">{{ s.title }}</span>
                          <span class="source-idx">#{{ s.chunk_index }}</span>
                        </div>
                        <div class="source-content">{{ s.content }}</div>
                      </div>
                    </el-collapse-item>
                  </el-collapse>
                </div>
              </div>
            </div>
            <div v-if="sending" class="msg-row assistant">
              <div class="msg-avatar assistant">AI</div>
              <div class="msg-bubble">
                <div class="msg-typing">
                  <el-icon class="is-loading"><Loading /></el-icon> 正在检索知识库并生成回答…
                </div>
              </div>
            </div>
          </div>
          <div class="chat-input">
            <el-input
              v-model="question"
              type="textarea"
              :rows="2"
              resize="none"
              placeholder="请输入问题，如：离线开锁功能的测试要点有哪些？"
              @keydown.enter.exact.prevent="handleSend"
            />
            <div class="chat-input-bar">
              <el-select v-model="chatMode" style="width: 130px">
                <el-option label="混合检索" value="hybrid" />
                <el-option label="向量检索" value="vector" />
                <el-option label="关键词检索" value="keyword" />
              </el-select>
              <el-select v-model="chatLine" placeholder="全部产品线" clearable style="width: 140px">
                <el-option v-for="(label, key) in productLineMap" :key="key" :label="label" :value="key" />
              </el-select>
              <div class="flex-1"></div>
              <el-button plain @click="handleNewChat">新对话</el-button>
              <el-button type="primary" :loading="sending" @click="handleSend">发送</el-button>
            </div>
          </div>
        </div>
      </el-card>
    </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { knowledgeApi } from '@/api'

const list = ref<any[]>([])
const hits = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = ref(10)
const total = ref(0)
const query = ref('')
const mode = ref('hybrid')
const uploadType = ref('test_case')
const selectedType = ref('')
// 产品线（业务域）过滤：intercom 楼宇对讲 / smart_home 智能家居 / hospital 智慧病房；空=通用/全部
const selectedLine = ref('')
const uploadLine = ref('')
const chatLine = ref('')

const productLineMap: Record<string, string> = {
  intercom: '楼宇对讲', smart_home: '智能家居', hospital: '智慧病房',
}

const viewVisible = ref(false)
const viewDoc = ref<any>(null)
const versionVisible = ref(false)
const versionDoc = ref<any>(null)
const versions = ref<any[]>([])
const versionLoading = ref(false)

const typeMap: Record<string, string> = {
  test_case: '历史用例', prd: '需求文档', tech_spec: '技术规格', defect: '缺陷报告', best_practice: '最佳实践', prototype: '原型图',
}

const loadData = async () => {
  loading.value = true
  try {
    const params: any = { page: page.value, page_size: pageSize.value }
    if (selectedType.value) params.doc_type = selectedType.value
    if (selectedLine.value) params.product_line = selectedLine.value
    const data = await knowledgeApi.list(params)
    list.value = data.list
    total.value = data.total
  } finally {
    loading.value = false
  }
}

const handleUpload = async (file: File) => {
  const res = await knowledgeApi.upload(uploadType.value, file, uploadLine.value)
  ElMessage.success(res?.version > 1 ? `已更新为 v${res.version}，正在后台向量化…` : '上传成功，正在后台向量化…')
  loadData()
  // 轮询刷新向量化状态（最长 20 秒）
  let n = 0
  const timer = setInterval(async () => {
    n++
    await loadData()
    if (n >= 7) clearInterval(timer)
  }, 3000)
  return false
}

const handleVectorizeAll = async () => {
  const res: any = await knowledgeApi.vectorizeAll()
  ElMessage.success(res?.message || '已提交后台向量化')
  loadData()
  let n = 0
  const timer = setInterval(async () => {
    n++
    await loadData()
    if (n >= 10) clearInterval(timer)
  }, 3000)
}

const handleView = async (row: any) => {
  viewDoc.value = await knowledgeApi.detail(row.id)
  viewVisible.value = true
}

const handleVersions = async (row: any) => {
  versionDoc.value = row
  versionVisible.value = true
  versionLoading.value = true
  try {
    const data = await knowledgeApi.versions(row.id)
    versions.value = data.list
  } finally {
    versionLoading.value = false
  }
}

const viewVersionContent = (row: any) => {
  viewDoc.value = { ...row, doc_type: versionDoc.value.doc_type, created_at: row.created_at }
  viewVisible.value = true
}

const handleVectorize = async (row: any) => {
  const res: any = await knowledgeApi.vectorize(row.id)
  if (res?.message && res.message.includes('向量化失败')) {
    ElMessage.error(res.message)
  } else {
    ElMessage.success(`向量化完成，共 ${res.chunk_count} 个分块`)
  }
  loadData()
}

const handleDelete = async (row: any) => {
  await ElMessageBox.confirm(`确认删除「${row.title}」？`, '提示', { type: 'warning' })
  await knowledgeApi.remove(row.id)
  ElMessage.success('删除成功')
  loadData()
}

const handleSearch = async () => {
  if (!query.value) return ElMessage.warning('请输入检索内容')
  const res = await knowledgeApi.search(query.value, 5, mode.value)
  hits.value = res.hits
}

// ============ 知识问答（对话形式） ============
const activeTab = ref('search')
const messages = ref<any[]>([])
const question = ref('')
const chatMode = ref('hybrid')
const sending = ref(false)
const chatBody = ref<HTMLElement | null>(null)

const scrollToBottom = () => {
  nextTick(() => {
    chatBody.value?.scrollTo({ top: chatBody.value.scrollHeight, behavior: 'smooth' })
  })
}

const handleSend = async () => {
  const q = question.value.trim()
  if (!q) return ElMessage.warning('请输入问题')
  if (sending.value) return
  messages.value.push({ role: 'user', content: q })
  question.value = ''
  sending.value = true
  scrollToBottom()
  try {
    const history = messages.value.slice(0, -1).map((m) => ({ role: m.role, content: m.content }))
    const res = await knowledgeApi.chat(q, history, 5, chatMode.value, chatLine.value)
    messages.value.push({ role: 'assistant', content: res.answer, sources: res.sources || [] })
  } catch {
    messages.value.push({ role: 'assistant', content: '回答生成失败，请稍后重试。', sources: [] })
  } finally {
    sending.value = false
    scrollToBottom()
  }
}

const exporting = ref('')

const exportChat = async (format: 'word' | 'ppt' | 'pdf', answer: string) => {
  if (!answer?.trim()) {
    ElMessage.warning('当前没有可导出的内容')
    return
  }
  exporting.value = format
  try {
    const blob = await knowledgeApi.chatExport(answer, '知识库总结', format)
    const url = window.URL.createObjectURL(blob as any)
    const a = document.createElement('a')
    a.href = url
    a.download = `知识库总结.${format === 'word' ? 'docx' : format}`
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e: any) {
    ElMessage.error(e?.message || '导出失败')
  } finally {
    exporting.value = ''
  }
}

const handleNewChat = () => {
  messages.value = []
}

onMounted(loadData)
</script>

<style scoped>
.mb16 {
  margin-bottom: 16px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.search {
  width: 400px;
}

.flex-1 {
  flex: 1;
}

.hit-item {
  padding: 12px;
  border-bottom: 1px solid #f0f2f5;
}

.hit-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.hit-title {
  font-weight: 600;
}

.hit-index {
  color: #c0c4cc;
  font-size: 12px;
}

.hit-content {
  color: #606266;
  font-size: 13px;
  line-height: 1.6;
  background: #f9fafb;
  padding: 8px 12px;
  border-radius: 4px;
}

.pagination {
  margin-top: 16px;
  justify-content: flex-end;
}

.doc-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.doc-time {
  color: #909399;
  font-size: 12px;
}

.doc-content {
  background: #f9fafb;
  border-radius: 6px;
  padding: 14px;
  max-height: 60vh;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.7;
  font-family: inherit;
}

/* ============ 知识问答（对话形式） ============ */
.chat-panel {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 280px);
  min-height: 420px;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 8px 4px;
}

.msg-row {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
}

.msg-row.user {
  flex-direction: row-reverse;
}

.msg-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: #fff;
}

.msg-avatar.user {
  background: #409eff;
}

.msg-avatar.assistant {
  background: #67c23a;
}

.msg-bubble {
  max-width: 78%;
  background: #f4f4f5;
  border-radius: 10px;
  padding: 10px 14px;
  font-size: 14px;
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.msg-row.user .msg-bubble {
  background: #ecf5ff;
}

.msg-typing {
  color: #909399;
  display: flex;
  align-items: center;
  gap: 6px;
}

.msg-sources {
  margin-top: 10px;
  border-top: 1px dashed #e4e7ed;
  padding-top: 8px;
}

.source-item {
  margin-bottom: 10px;
}

.source-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.source-title {
  font-weight: 600;
  font-size: 13px;
}

.source-idx {
  color: #c0c4cc;
  font-size: 12px;
}

.source-content {
  color: #606266;
  font-size: 12px;
  line-height: 1.6;
  background: #f9fafb;
  padding: 6px 10px;
  border-radius: 4px;
  max-height: 90px;
  overflow: auto;
}

.msg-export {
  margin-top: 8px;
  padding-top: 6px;
  border-top: 1px dashed #e4e7ed;
  display: flex;
  align-items: center;
  gap: 2px;
}

.export-label {
  font-size: 12px;
  color: #909399;
}

.chat-input {
  border-top: 1px solid #ebeef5;
  padding-top: 12px;
}

.chat-input-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 10px;
}
</style>
