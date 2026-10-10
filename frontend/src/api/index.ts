import request from './request'

// ===== 认证 =====
export const authApi = {
  login: (data: { username: string; password: string; captcha_id?: string; captcha_code?: string }) =>
    request.post('/auth/login', data),
  me: () => request.get('/auth/me'),
  logout: () => request.post('/auth/logout'),
  changePassword: (data: { old_password: string; new_password: string }) =>
    request.post('/auth/change-password', data),
  captcha: () => request.get('/auth/captcha'),
}

// ===== 项目 =====
export const projectApi = {
  list: (params?: any) => request.get('/projects', { params }),
  detail: (id: number) => request.get(`/projects/${id}`),
  create: (data: any) => request.post('/projects', data),
  update: (id: number, data: any) => request.put(`/projects/${id}`, data),
  remove: (id: number) => request.delete(`/projects/${id}`),
  archive: (id: number) => request.put(`/projects/${id}/archive`),
}

// ===== 文档 =====
export const documentApi = {
  upload: (projectId: number, file: File) => {
    const form = new FormData()
    form.append('project_id', String(projectId))
    form.append('file', file)
    return request.post('/documents/upload', form)
  },
  list: (params?: any) => request.get('/documents', { params }),
  detail: (id: number) => request.get(`/documents/${id}`),
  // 解析可能包含图片视觉识别（硅基流动单张 30~60s，多张并行最坏 ~85s），
  // 单独放宽超时到 3 分钟，避免被全局 30s 掐断
  parse: (id: number) => request.post(`/documents/${id}/parse`, undefined, { timeout: 180000 }),
  remove: (id: number) => request.delete(`/documents/${id}`),
  parseUrl: (data: { project_id: number; url: string; title?: string }) =>
    request.post('/documents/parse-url', data, { timeout: 180000 }),
}

// ===== 测试点 =====
export const testPointApi = {
  list: (params?: any) => request.get('/test-points', { params }),
  create: (data: any) => request.post('/test-points', data),
  update: (id: number, data: any) => request.put(`/test-points/${id}`, data),
  remove: (id: number) => request.delete(`/test-points/${id}`),
}

// ===== 测试用例 =====
export const testCaseApi = {
  list: (params?: any) => request.get('/test-cases', { params }),
  // 跨页全选：返回当前查询条件下全部用例的 id + source（ids_only=true 不分页）
  listIds: (params?: any) => request.get('/test-cases', { params: { ...params, ids_only: true } }),
  // 项目下已有用例的去重模块列表
  modules: (projectId?: number) => request.get('/test-cases/modules', { params: { project_id: projectId } }),
  // 生成批次列表（第N次生成 + 用例数/自查进度），用于按批次过滤
  tasks: (projectId?: number) => request.get('/test-cases/tasks', { params: { project_id: projectId } }),
  detail: (id: number) => request.get(`/test-cases/${id}`),
  create: (data: any) => request.post('/test-cases', data),
  update: (id: number, data: any) => request.put(`/test-cases/${id}`, data),
  review: (id: number, action: string, comment?: string) =>
    request.put(`/test-cases/${id}/review`, { action, comment }),
  autoComplete: (id: number) => request.post(`/test-cases/${id}/auto-complete`),
  versions: (id: number) => request.get(`/test-cases/${id}/versions`),
  batch: (data: any) => request.post('/test-cases/batch', data),
  feedback: (caseId: number, feedback: 'good' | 'bad' | 'clear') =>
    request.post(`/test-cases/feedback`, null, { params: { case_id: caseId, feedback } }),
  batchRegenerate: (caseIds: number[]) => request.post('/test-cases/batch-regenerate', { case_ids: caseIds }),
  // AI 自查（逐条比对需求原文，标注存疑/不符，不改动用例内容）
  selfCheck: (data: { case_ids?: number[]; task_id?: number }) =>
    request.post('/test-cases/self-check', data, { timeout: 300000 }),
  // 重复扫描（识别同义重复组并标注【疑似重复·组N】，不改动用例内容）
  dedupScan: (data: { case_ids?: number[]; task_id?: number }) =>
    request.post('/test-cases/dedup-check', data, { timeout: 600000 }),
  // 一键清理重复：先 dry_run=true 预览，确认后 dry_run=false 执行（每组保留代表用例）
  dedupCleanup: (data: { case_ids?: number[]; task_id?: number; dry_run?: boolean }) =>
    request.post('/test-cases/dedup-cleanup', data, { timeout: 120000 }),
  export: (caseIds: number[], format: 'excel' | 'markdown' | 'json' | 'xmind' = 'excel') =>
    request.post('/test-cases/export', { case_ids: caseIds, format }, { responseType: 'blob' }),
}

// ===== 生成任务 =====
export const generateApi = {
  create: (data: any) => request.post('/generate/task', data),
  preview: (data: any) => request.post('/generate/preview', data),
  detail: (id: number) => request.get(`/generate/task/${id}`),
  cancel: (id: number) => request.post(`/generate/task/${id}/cancel`),
  retry: (id: number) => request.post(`/generate/task/${id}/retry`),
  list: (params?: any) => request.get('/generate/tasks', { params }),
  summary: (id: number) => request.get(`/generate/task/${id}/summary`),
  coverage: (id: number) => request.get(`/generate/task/${id}/coverage`),
  streamUrl: (id: number) => `/api/v1/generate/task/${id}/stream`,
}

// ===== 需求体检 =====
export const reqReviewApi = {
  analyze: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request.post('/req-review/analyze', form, { timeout: 300000 })
  },
  list: (params?: any) => request.get('/req-review/reports', { params }),
  detail: (id: number) => request.get(`/req-review/reports/${id}`),
  download: (id: number) => request.get(`/req-review/reports/${id}/download`, { responseType: 'blob' }),
}

// ===== 知识库 =====
export const knowledgeApi = {
  list: (params?: any) => request.get('/knowledge/docs', { params }),
  upload: (docType: string, file: File, productLine = '') => {
    const form = new FormData()
    form.append('doc_type', docType)
    if (productLine) form.append('product_line', productLine)
    form.append('file', file)
    return request.post('/knowledge/docs/upload', form)
  },
  detail: (id: number) => request.get(`/knowledge/docs/${id}`),
  vectorize: (id: number) => request.post(`/knowledge/docs/${id}/vectorize`),
  vectorizeAll: () => request.post('/knowledge/docs/vectorize-all'),
  // FR-4.3 检索模式: hybrid / vector / keyword
  search: (query: string, topK = 5, mode = 'hybrid', productLine = '') =>
    request.post('/knowledge/search', { query, top_k: topK, mode, product_line: productLine || null }),
  // 知识库对话问答（RAG）
  chat: (question: string, history: { role: string; content: string }[], topK = 5, mode = 'hybrid', productLine = '') =>
    request.post('/knowledge/chat', { question, history, top_k: topK, mode, product_line: productLine || null }),
  // FR-4.4 版本历史
  versions: (id: number) => request.get(`/knowledge/docs/${id}/versions`),
  remove: (id: number) => request.delete(`/knowledge/docs/${id}`),
}

// ===== 成员管理（需 user_manage 权限） =====
export const userApi = {
  list: (params?: any) => request.get('/users', { params }),
  create: (data: any) => request.post('/users', data),
  update: (id: number, data: any) => request.put(`/users/${id}`, data),
  resetPassword: (id: number, new_password: string) =>
    request.put(`/users/${id}/password`, { new_password }),
  setStatus: (id: number, is_active: boolean) =>
    request.put(`/users/${id}/status`, { is_active }),
  remove: (id: number) => request.delete(`/users/${id}`),
  permissions: (id: number) => request.get(`/users/${id}/permissions`),
  setPermissions: (id: number, permissions: string[]) =>
    request.put(`/users/${id}/permissions`, { permissions }),
}

// ===== 权限目录 =====
export const permApi = {
  catalog: () => request.get('/permissions/catalog'),
}

// ===== 统计 =====
export const statsApi = {
  overview: () => request.get('/stats/overview'),
  project: (id: number) => request.get(`/stats/projects/${id}`),
  efficiency: () => request.get('/stats/efficiency'),
  quality: () => request.get('/stats/quality'),
  testTypes: (params?: any) => request.get('/stats/test-types', { params }),
  priorities: (params?: any) => request.get('/stats/priorities', { params }),
  trend: (params?: any) => request.get('/stats/trend', { params }),
}

// ===== 测试脚本 =====
export const scriptApi = {
  generate: (data: { case_ids: number[]; script_type: string; custom_prompt?: string; template_id?: number }) =>
    request.post('/scripts/generate', data, { timeout: 300000 }),
  save: (data: any) => request.post('/scripts', data),
  list: (params?: any) => request.get('/scripts', { params }),
  detail: (id: number) => request.get(`/scripts/${id}`),
  update: (id: number, data: any) => request.put(`/scripts/${id}`, data),
  remove: (id: number) => request.delete(`/scripts/${id}`),
  download: (id: number) =>
    request.get(`/scripts/${id}/download`, { responseType: 'blob' }),
}

// ===== 脚本模板（FR-6.4） =====
export const scriptTemplateApi = {
  list: (params?: any) => request.get('/script-templates', { params }),
  all: () => request.get('/script-templates/all'),
  create: (data: any) => request.post('/script-templates', data),
  update: (id: number, data: any) => request.put(`/script-templates/${id}`, data),
  remove: (id: number) => request.delete(`/script-templates/${id}`),
}

// ===== 操作日志 =====
export const logApi = {
  list: (params?: any) => request.get('/logs', { params }),
  clear: () => request.delete('/logs'),
  export: (params?: any) =>
    request.get('/logs/export', { params, responseType: 'blob' }),
}

// ===== 消息通知 =====
export const notificationApi = {
  list: (params?: any) => request.get('/notifications', { params }),
  unreadCount: () => request.get('/notifications/unread-count'),
  read: (id: number) => request.put(`/notifications/${id}/read`),
  readAll: () => request.put('/notifications/read-all'),
}

// ===== 系统 =====
export const systemApi = {
  health: () => request.get('/system/health'),
  manualBaseline: () => request.get('/system/manual-baseline'),
  saveManualBaseline: (data: { avg_cases_per_day: number; avg_time_minutes: number }) =>
    request.put('/system/manual-baseline', data),
  models: () => request.get('/system/models'),
  agents: () => request.get('/system/agents'),
  llmConfig: () => request.get('/system/llm-config'),
  saveLlmConfig: (data: any) => request.put('/system/llm-config', data),
}
