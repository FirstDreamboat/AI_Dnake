<template>
  <div class="settings-page">
    <el-card shadow="never" class="mb16">
      <template #header>
        <div class="card-header">
          <span>模型配置</span>
          <el-button type="primary" size="small" :loading="loading" @click="loadHealth">重新检测</el-button>
        </div>
      </template>
      <el-descriptions :column="2" border>
        <el-descriptions-item label="LLM 服务商">{{ configured.provider === 'deepseek' ? 'DeepSeek API' : '本地 Ollama' }}</el-descriptions-item>
        <el-descriptions-item label="对话模型">{{ configured.llm_model || '-' }}</el-descriptions-item>
        <el-descriptions-item label="向量模型 (Embedding)">
          {{ configured.embedding_model || '-' }}
          <el-tag :type="embeddingTagType" size="small" class="ml8">{{ embeddingProviderText }}</el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="Ollama 地址">{{ configured.ollama_base_url || '-' }}</el-descriptions-item>
        <el-descriptions-item label="DeepSeek API Key">
          <el-tag :type="configured.deepseek_api_key_configured ? 'success' : 'danger'" size="small">
            {{ configured.deepseek_api_key_configured ? '已配置' : '未配置' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="视觉模型（原型图解析）">
          <el-tag :type="configured.vision_enabled ? 'success' : 'info'" size="small">
            {{ configured.vision_enabled ? (configured.vision_provider === 'siliconflow' ? configured.vision_model || '云端视觉' : configured.vision_model || '已启用') : '未启用' }}
          </el-tag>
          <el-tag v-if="configured.vision_enabled" :type="visionConfiguredType" size="small" class="ml8">
            {{ visionProviderText }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="服务状态">
          <el-tag :type="healthOk ? 'success' : 'danger'" size="small">{{ healthOk ? '运行正常' : '存在异常' }}</el-tag>
        </el-descriptions-item>
      </el-descriptions>
      <el-alert
        class="mt16"
        type="info"
        :closable="false"
        title="对话模型可在线切换，保存后即时生效并持久化"
        description="在下方「模型切换」卡片可随时在 DeepSeek API 与本地 Ollama（如 qwen2.5:3b / qwen2.5:7b）之间切换，无需重启。向量生成与视觉解析默认走硅基流动云端（免费额度、秒级响应），未配置云端 Key 时自动回退本地 Ollama；相关 API Key、Ollama 地址等参数在 backend/.env 中配置。"
      />
    </el-card>

    <el-card shadow="never" class="mb16">
      <template #header>
        <div class="card-header">
          <span>模型切换（即时生效）</span>
          <el-button type="primary" size="small" :loading="saving" @click="saveLlmConfig">保存并应用</el-button>
        </div>
      </template>
      <el-form label-width="120px" class="llm-form">
        <el-form-item label="LLM 服务商">
          <el-radio-group v-model="llmForm.provider">
            <el-radio value="deepseek">DeepSeek API（云端）</el-radio>
            <el-radio value="ollama">本地 Ollama（Qwen）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="llmForm.provider === 'deepseek' ? 'DeepSeek 模型' : 'Ollama 模型'">
          <el-select
            v-model="currentModel"
            filterable
            allow-create
            default-first-option
            style="width: 360px"
            placeholder="选择或输入模型名称"
          >
            <el-option v-for="m in modelOptions" :key="m" :label="m" :value="m" />
          </el-select>
          <div class="tip">
            <template v-if="llmForm.provider === 'deepseek'">DeepSeek 推荐：deepseek-chat（通用）、deepseek-reasoner（推理）</template>
            <template v-else>需先在 Ollama 中 pull 对应模型（如 qwen2.5:3b / qwen2.5:7b）</template>
          </div>
        </el-form-item>
        <el-form-item label="当前生效">
          <el-tag type="success">{{ currentModel || '-' }}</el-tag>
          <span class="tip" style="margin-left: 8px">保存后立即生效，下次启动自动恢复</span>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 云服务余额 -->
    <el-card shadow="never" class="mb16">
      <template #header>
        <div class="card-header">
          <span>云服务余额</span>
          <el-button type="primary" size="small" :loading="balanceLoading" @click="loadBalance">刷新</el-button>
        </div>
      </template>
      <template v-if="balance.deepseek || balance.siliconflow">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="DeepSeek（文本生成）">
            <template v-if="balance.deepseek?.configured === false">
              <el-tag type="info">未配置 Key</el-tag>
            </template>
            <template v-else-if="balance.deepseek?.error">
              <el-tag type="danger">查询失败</el-tag>
              <span class="bal-err">{{ balance.deepseek.error }}</span>
            </template>
            <template v-else>
              <span :class="balClass(balance.deepseek)">
                ¥{{ (balance.deepseek?.balance ?? 0).toFixed(2) }}
              </span>
              <el-tag v-if="balance.deepseek?.available === false" type="danger" class="ml8">已不可用</el-tag>
              <el-tag v-else-if="lowBalance(balance.deepseek)" type="warning" class="ml8">余额偏低</el-tag>
            </template>
          </el-descriptions-item>
          <el-descriptions-item label="硅基流动（向量化/视觉）">
            <template v-if="balance.siliconflow?.configured === false">
              <el-tag type="info">未配置 Key</el-tag>
            </template>
            <template v-else-if="balance.siliconflow?.query_unavailable">
              <el-tag type="info">平台不支持查询</el-tag>
              <span class="bal-err">请登录 siliconflow.cn 控制台查看余额</span>
            </template>
            <template v-else-if="balance.siliconflow?.error">
              <el-tag type="danger">查询失败</el-tag>
              <span class="bal-err">{{ balance.siliconflow.error }}</span>
            </template>
            <template v-else>
              <span :class="balClass(balance.siliconflow)">
                ¥{{ (balance.siliconflow?.balance ?? 0).toFixed(2) }}
              </span>
              <el-tag v-if="balance.siliconflow?.available === false" type="danger" class="ml8">已不可用</el-tag>
              <el-tag v-else-if="lowBalance(balance.siliconflow)" type="warning" class="ml8">余额偏低</el-tag>
            </template>
          </el-descriptions-item>
        </el-descriptions>
        <div class="bal-tip">余额 &lt; ¥10 标黄提醒；生成/解析/向量化均消耗云服务额度，答辩演示前请确认余量充足。</div>
      </template>
      <el-skeleton v-else-if="balanceLoading" :rows="2" animated />
    </el-card>

    <el-card shadow="never" class="mb16">
      <template #header>
        <div class="card-header">
          <span>效率基线标定（AI vs 人工对比依据）</span>
          <el-button type="primary" size="small" :loading="savingBaseline" @click="saveBaseline">保存基线</el-button>
        </div>
      </template>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="人工编写耗时平台无法自动统计，此处由测试部按同一需求实测标定；AI 侧耗时为生成任务真实计时。工作台与统计页的效率对比基于这两组数据计算。"
        style="margin-bottom: 12px"
      />
      <el-form inline>
        <el-form-item label="人工人均每日编写用例数">
          <el-input-number v-model="baseline.avg_cases_per_day" :min="1" :max="10000" />
          <span class="tip" style="margin-left: 8px">条/人/天</span>
        </el-form-item>
        <el-form-item label="人工编写一批用例平均耗时">
          <el-input-number v-model="baseline.avg_time_minutes" :min="1" :max="100000" />
          <span class="tip" style="margin-left: 8px">分钟</span>
        </el-form-item>
      </el-form>
    </el-card>

    <el-row :gutter="16">
      <el-col :span="12">
        <el-card shadow="never" class="mb16">
          <template #header><span>健康检查</span></template>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="数据库">
              <el-tag :type="tagType(health.database)" size="small">{{ tagText(health.database) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="LLM 服务">
              <el-tag :type="tagType(health.llm)" size="small">{{ tagText(health.llm) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="DeepSeek">
              <el-tag :type="tagType(health.deepseek)" size="small">{{ tagText(health.deepseek) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="Embedding 服务">
              <el-tag :type="tagType(health.embedding)" size="small">{{ tagText(health.embedding) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="Ollama (兜底)">
              <el-tag :type="tagType(health.ollama)" size="small">{{ tagText(health.ollama) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="视觉模型 (原型图)">
              <el-tag :type="visionTagType" size="small">{{ visionTagText }}</el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never" class="mb16">
          <template #header><span>已安装模型</span></template>
          <el-empty v-if="!installed.length" description="暂无模型信息" :image-size="60" />
          <el-tag v-for="m in installed" :key="m" class="mr8 mb8" type="primary">{{ m }}</el-tag>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never">
      <template #header><span>智能体配置</span></template>
      <el-table :data="agents" border stripe>
        <el-table-column prop="name" label="智能体名称" min-width="160" />
        <el-table-column prop="key" label="标识" min-width="200" />
        <el-table-column prop="model" label="使用的模型" min-width="140" />
        <el-table-column label="说明">
          <template #default="{ row }">
            {{ agentDesc[row.key] || '由平台内置 Prompt 驱动' }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { systemApi } from '@/api'

const loading = ref(false)
const saving = ref(false)
const health = ref<any>({ database: '-', llm: '-', deepseek: '-', embedding: '-', ollama: '-', vision: {} })
const configured = ref<any>({})
const installed = ref<string[]>([])
const agents = ref<any[]>([])
const llmForm = ref<{ provider: string; llm_model: string; deepseek_model: string }>({
  provider: 'ollama',
  llm_model: 'qwen2.5:3b',
  deepseek_model: 'deepseek-chat',
})
const ollamaInstalled = ref<string[]>([])

// 模型候选：Ollama 预置 qwen2.5 3b/7b + 已安装模型；DeepSeek 预置 chat/reasoner
const modelOptions = computed<string[]>(() => {
  if (llmForm.value.provider === 'deepseek') {
    return Array.from(new Set([llmForm.value.deepseek_model, 'deepseek-chat', 'deepseek-reasoner'].filter(Boolean)))
  }
  const presets = ['qwen2.5:3b', 'qwen2.5:7b']
  return Array.from(new Set([llmForm.value.llm_model, ...presets, ...ollamaInstalled.value].filter(Boolean)))
})

const currentModel = computed({
  get: () => (llmForm.value.provider === 'deepseek' ? llmForm.value.deepseek_model : llmForm.value.llm_model),
  set: (v: string) => {
    if (llmForm.value.provider === 'deepseek') llmForm.value.deepseek_model = v
    else llmForm.value.llm_model = v
  },
})

const visionTagType = computed(() => {
  const v = health.value?.vision
  if (!v?.enabled) return 'info'
  return v.available ? 'success' : 'warning'
})
const visionTagText = computed(() => {
  const v = health.value?.vision
  if (!v?.enabled) return '未启用'
  if (v.available) return '可用'
  return v.provider === 'siliconflow' ? '云端 Key 无效' : '模型未安装'
})

// Embedding 服务商展示（云端优先）
const embeddingTagType = computed(() => (configured.value.embedding_provider === 'siliconflow' ? 'success' : 'info'))
const embeddingProviderText = computed(() => {
  if (configured.value.embedding_provider === 'siliconflow') {
    return configured.value.embedding_api_key_configured ? '硅基流动' : '硅基流动(未配Key)'
  }
  return 'Ollama'
})

// 视觉模型服务商展示
const visionConfiguredType = computed(() => (configured.value.vision_api_key_configured ? 'success' : 'warning'))
const visionProviderText = computed(() => {
  if (configured.value.vision_provider === 'ollama') return 'Ollama'
  return configured.value.vision_api_key_configured ? '硅基流动云端' : '云端(未配Key)'
})

const agentDesc: Record<string, string> = {
  requirement_parser: '解析需求文档，输出结构化需求条目',
  test_point_extractor: '从需求中提取功能/边界/异常/性能/安全/隐式测试点',
  test_case_generator: '基于测试点生成规范化测试用例',
  test_case_reviewer: '对用例进行评审并给出优化建议',
}

const tagMap: Record<string, { type: string; text: string }> = {
  ok: { type: 'success', text: '正常' },
  error: { type: 'danger', text: '异常' },
  unavailable: { type: 'warning', text: '不可用' },
  not_used: { type: 'info', text: '未使用' },
}

const tagType = (s: string) => (tagMap[s] || { type: 'info' }).type
const tagText = (s: string) => (tagMap[s] || { type: 'info', text: s || '-' }).text

const healthOk = computed(
  () => health.value.database === 'ok' && health.value.llm === 'ok' && health.value.embedding === 'ok',
)

const loadHealth = async () => {
  loading.value = true
  try {
    const [h, m, a] = await Promise.all([systemApi.health(), systemApi.models(), systemApi.agents()])
    health.value = h?.data ?? h
    // request.ts 已把后端包装响应解包为 data，这里兼容包装和未包装两种形态
    configured.value = m?.data?.configured ?? m?.configured ?? {}
    installed.value = m?.data?.installed ?? m?.installed ?? []
    agents.value = a?.data?.agents ?? a?.agents ?? []
  } catch (e: any) {
    ElMessage.error(e?.message || '获取系统信息失败')
  } finally {
    loading.value = false
  }
}

// ===== 云服务余额 =====
const balance = ref<any>({})
const balanceLoading = ref(false)
const loadBalance = async () => {
  balanceLoading.value = true
  try {
    const res: any = await systemApi.llmBalance()
    balance.value = res?.data ?? res ?? {}
  } catch {
    /* 静默：卡片保持上次状态 */
  } finally {
    balanceLoading.value = false
  }
}
const lowBalance = (d: any) => d && typeof d.balance === 'number' && d.balance < 10
const balClass = (d: any) => ['bal-value', d && lowBalance(d) ? 'bal-low' : '']

const loadLlmConfig = async () => {
  try {
    const cfg = await systemApi.llmConfig()
    const d = cfg?.data ?? cfg ?? {}
    llmForm.value.provider = d.provider || 'ollama'
    llmForm.value.llm_model = d.llm_model || 'qwen2.5:3b'
    llmForm.value.deepseek_model = d.deepseek_model || 'deepseek-chat'
    ollamaInstalled.value = d.ollama_installed || []
  } catch (e: any) {
    ElMessage.error(e?.message || '获取模型配置失败')
  }
}

const saveLlmConfig = async () => {
  if (!llmForm.value.provider) return
  saving.value = true
  try {
    await systemApi.saveLlmConfig({
      provider: llmForm.value.provider,
      llm_model: llmForm.value.llm_model,
      deepseek_model: llmForm.value.deepseek_model,
    })
    ElMessage.success('模型配置已保存并即时生效')
    await Promise.all([loadHealth(), loadLlmConfig()])
  } catch (e: any) {
    ElMessage.error(e?.message || '保存模型配置失败')
  } finally {
    saving.value = false
  }
}

// ===== 效率基线标定 =====
const baseline = ref({ avg_cases_per_day: 20, avg_time_minutes: 180 })
const savingBaseline = ref(false)

const loadBaseline = async () => {
  try {
    const data = await systemApi.manualBaseline()
    baseline.value.avg_cases_per_day = data?.avg_cases_per_day ?? 20
    baseline.value.avg_time_minutes = data?.avg_time_minutes ?? 180
  } catch {
    // 保持默认值
  }
}

const saveBaseline = async () => {
  savingBaseline.value = true
  try {
    await systemApi.saveManualBaseline({
      avg_cases_per_day: baseline.value.avg_cases_per_day,
      avg_time_minutes: baseline.value.avg_time_minutes,
    })
    ElMessage.success('人工效率基线已保存')
  } catch (e: any) {
    ElMessage.error(e?.message || '保存基线失败')
  } finally {
    savingBaseline.value = false
  }
}

onMounted(() => {
  loadHealth()
  loadLlmConfig()
  loadBalance()
  loadBaseline()
})
</script>

<style scoped>
.bal-value {
  font-weight: bold;
  font-size: 16px;
}
.bal-low {
  color: #e6a23c;
}
.bal-err {
  color: #909399;
  font-size: 12px;
  margin-left: 8px;
}
.bal-tip {
  margin-top: 10px;
  font-size: 12px;
  color: #909399;
}
.settings-page {
  padding: 4px;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.mb16 {
  margin-bottom: 16px;
}
.mt16 {
  margin-top: 16px;
}
.mr8 {
  margin-right: 8px;
}
.mb8 {
  margin-bottom: 8px;
}
.ml8 {
  margin-left: 8px;
}
.llm-form {
  max-width: 720px;
}
.tip {
  color: var(--el-text-color-secondary);
  font-size: 12px;
  line-height: 1.6;
  margin-top: 4px;
}
</style>
