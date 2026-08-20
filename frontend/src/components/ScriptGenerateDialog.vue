<template>
  <el-dialog v-model="visible" title="生成自动化测试脚本" width="860px" top="6vh" destroy-on-close>
    <div v-if="!generated" class="gen-step">
      <el-form label-width="110px">
        <el-form-item label="所选用例">
          <span class="case-count">共 {{ caseCount }} 条用例</span>
        </el-form-item>
        <el-form-item label="脚本类型">
          <el-radio-group v-model="scriptType">
            <el-radio-button value="pytest">单元测试(pytest)</el-radio-button>
            <el-radio-button value="api">接口自动化</el-radio-button>
            <el-radio-button value="ui">UI自动化(playwright)</el-radio-button>
            <el-radio-button value="android">安卓APP自动化</el-radio-button>
            <el-radio-button value="ios">iOS APP自动化</el-radio-button>
            <el-radio-button value="custom">自定义</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="自定义模板">
          <el-select
            v-model="templateId"
            placeholder="不选用模板（默认提示词生成）"
            clearable
            filterable
            style="width: 100%"
            @change="onTemplateChange"
          >
            <el-option
              v-for="t in templates"
              :key="t.id"
              :label="`${t.name}${t.framework ? '（' + t.framework + '）' : ''}`"
              :value="t.id"
            />
          </el-select>
          <div class="template-tip">
            选择模板后，将依据模板代码骨架生成脚本，脚本类型自动切换为模板类型（FR-6.4）
          </div>
        </el-form-item>
        <el-form-item v-if="scriptType === 'custom'" label="自定义要求">
          <el-input
            v-model="customPrompt"
            type="textarea"
            :rows="4"
            placeholder="请输入脚本生成的自定义要求，例如：使用 requests 库、输出日志、超时时间 5s 等"
          />
        </el-form-item>
        <el-form-item>
          <div class="type-tip">{{ typeTip }}</div>
        </el-form-item>
      </el-form>
      <div class="dialog-footer">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="generating" @click="handleGenerate">
          {{ generating ? '正在生成...' : '生成脚本' }}
        </el-button>
      </div>
    </div>

    <div v-else class="result-step">
      <div class="result-head">
        <div class="result-title">
          <el-tag size="small" type="success">{{ typeLabel }}</el-tag>
          <el-input v-model="scriptName" size="small" class="name-input" />
        </div>
        <div class="result-actions">
          <el-button size="small" @click="handleRegenerate">重新生成</el-button>
          <el-button size="small" type="primary" :loading="saving" @click="handleSave">保存</el-button>
          <el-button size="small" :disabled="!savedId" @click="handleDownload">下载</el-button>
        </div>
      </div>
      <div class="editor-wrap">
        <el-input
          v-model="scriptContent"
          type="textarea"
          :rows="22"
          class="code-editor"
          spellcheck="false"
        />
      </div>
      <div class="dialog-footer mt8">
        <el-button @click="visible = false">关闭</el-button>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { scriptApi, scriptTemplateApi } from '@/api'

const visible = ref(false)
const scriptType = ref('pytest')
const customPrompt = ref('')
const generating = ref(false)
const saving = ref(false)
const generated = ref(false)
const scriptContent = ref('')
const scriptName = ref('')
const savedId = ref<number | null>(null)
const templates = ref<any[]>([])
const templateId = ref<number | undefined>(undefined)

const props = defineProps<{
  projectId: number
  caseIds: number[]
  caseCount: number
}>()

const typeTipMap: Record<string, string> = {
  pytest: '使用 pytest + pytest-mock，针对嵌入式场景模拟硬件交互，每个用例对应一个 test_ 函数',
  api: '使用 pytest + requests，将用例步骤映射为 HTTP 请求与响应断言',
  ui: '使用 pytest + playwright，将用例步骤映射为页面操作与元素断言',
  android: '使用 pytest + Appium(uiautomator2)，经 adb 连接安卓设备/模拟器，按 resource-id/text 定位控件执行操作与断言',
  ios: '使用 pytest + Appium(XCUITest)，连接 iOS 真机/模拟器，按 accessibility id/label 定位控件执行操作与断言',
  custom: '按自定义要求生成脚本，若未填写要求则默认按单元测试生成',
}
const typeLabelMap: Record<string, string> = {
  pytest: '单元测试脚本',
  api: '接口自动化脚本',
  ui: 'UI 自动化脚本',
  android: '安卓APP自动化脚本',
  ios: 'iOS APP自动化脚本',
  custom: '自定义脚本',
}

const typeTip = computed(() => typeTipMap[scriptType.value])
const typeLabel = computed(() => typeLabelMap[scriptType.value])

const open = () => {
  visible.value = true
  generated.value = false
  scriptContent.value = ''
  scriptName.value = ''
  savedId.value = null
  templateId.value = undefined
}

const onTemplateChange = (id?: number) => {
  const t = templates.value.find((x) => x.id === id)
  if (t) {
    scriptType.value = t.script_type || 'custom'
  }
}

const loadTemplates = async () => {
  try {
    const data = await scriptTemplateApi.all()
    templates.value = data ?? []
  } catch {
    templates.value = []
  }
}

const handleGenerate = async () => {
  generating.value = true
  try {
    const res = await scriptApi.generate({
      case_ids: props.caseIds,
      script_type: scriptType.value,
      custom_prompt: customPrompt.value || undefined,
      template_id: templateId.value,
    })
    scriptContent.value = res.content
    scriptName.value = res.suggest_name || 'test_script'
    generated.value = true
  } finally {
    generating.value = false
  }
}

const handleRegenerate = () => {
  generated.value = false
  savedId.value = null
  handleGenerate()
}

const handleSave = async () => {
  saving.value = true
  try {
    const res = await scriptApi.save({
      project_id: props.projectId,
      case_id: props.caseIds.length === 1 ? props.caseIds[0] : undefined,
      name: scriptName.value,
      script_type: scriptType.value,
      language: 'python',
      framework: typeLabelMap[scriptType.value],
      content: scriptContent.value,
      description: `由 ${props.caseCount} 条测试用例自动生成的${typeLabel.value}`,
    })
    savedId.value = res.id
    ElMessage.success('脚本已保存')
  } finally {
    saving.value = false
  }
}

const handleDownload = async () => {
  if (!savedId.value) return
  const blob = (await scriptApi.download(savedId.value)) as any
  const url = URL.createObjectURL(new Blob([blob]))
  const a = document.createElement('a')
  a.href = url
  a.download = `${scriptName.value || 'test_script'}.py`
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(loadTemplates)

onMounted(loadTemplates)

defineExpose({ open })
</script>

<style scoped>
.gen-step {
  min-height: 240px;
}

.case-count {
  color: #409eff;
  font-weight: 600;
}

.type-tip {
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
  border-left: 3px solid #e4e7ed;
  padding-left: 10px;
}

.template-tip {
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
  margin-top: 4px;
}

.dialog-footer {
  text-align: right;
}

.mt8 {
  margin-top: 8px;
}

.result-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
  gap: 12px;
}

.result-title {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
}

.name-input {
  max-width: 320px;
}

.result-actions {
  display: flex;
  gap: 8px;
}

.editor-wrap :deep(.el-textarea__inner) {
  font-family: 'JetBrains Mono', Consolas, 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  background: #1e1e1e;
  color: #d4d4d4;
  border-radius: 6px;
}
</style>
