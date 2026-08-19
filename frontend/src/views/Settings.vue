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

onMounted(() => {
  loadHealth()
  loadLlmConfig()
})
</script>

<style scoped>
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
