<template>
  <div>
    <el-row :gutter="20">
      <el-col :span="6" v-for="card in cards" :key="card.label">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value" :style="{ color: card.color }">{{ card.value }}</div>
          <div class="stat-label">{{ card.label }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" class="mt20">
      <el-col :span="12">
        <el-card shadow="hover" header="AI 与人工效率对比">
          <el-empty v-if="!efficiencyData" description="暂无生成任务数据，去「AI 用例生成」创建任务" />
          <div v-else>
            <div class="eff-row">
              <div class="eff-item">
                <div class="eff-num">{{ efficiencyData.ai_seconds_per_case ?? '-' }}<span class="eff-unit"> 秒</span></div>
                <div class="eff-label">AI 每条用例耗时（真实计时）</div>
              </div>
              <div class="eff-item">
                <div class="eff-num">{{ efficiencyData.manual_baseline?.minutes_per_case ?? '-' }}<span class="eff-unit"> 分钟</span></div>
                <div class="eff-label">人工每条用例耗时（实测标定）</div>
              </div>
              <div class="eff-item">
                <div class="eff-num speedup">{{ efficiencyData.speedup ? efficiencyData.speedup + ' 倍' : '-' }}</div>
                <div class="eff-label">效率提升</div>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover" header="系统状态">
          <div class="sys-row" v-if="health">
            <el-tag :type="health.ollama === 'ok' ? 'success' : 'danger'">
              Ollama 模型服务: {{ health.ollama === 'ok' ? '正常' : '不可用' }}
            </el-tag>
            <el-tag :type="health.database === 'ok' ? 'success' : 'danger'">
              数据库: {{ health.database === 'ok' ? '正常' : '异常' }}
            </el-tag>
            <div class="model-info">
              <p>LLM 模型: <code>{{ health.llm_model }}</code></p>
              <p>向量模型: <code>{{ health.embedding_model }}</code></p>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { statsApi, systemApi } from '@/api'

const cards = ref([
  { label: '项目数', value: 0, color: '#409EFF' },
  { label: '用例总数', value: 0, color: '#67C23A' },
  { label: '生成任务', value: 0, color: '#E6A23C' },
  { label: '需求文档', value: 0, color: '#F56C6C' },
])
const health = ref<any>(null)
const efficiencyData = ref<any>(null)

onMounted(async () => {
  try {
    const overview = await statsApi.overview()
    cards.value[0].value = overview.project_count
    cards.value[1].value = overview.case_count
    cards.value[2].value = overview.task_count
    cards.value[3].value = overview.doc_count

    health.value = await systemApi.health()
    efficiencyData.value = await statsApi.efficiency()
  } catch {
    // 已由拦截器提示
  }
})
</script>

<style scoped>
.stat-card {
  text-align: center;
}

.stat-value {
  font-size: 32px;
  font-weight: 700;
}

.stat-label {
  margin-top: 8px;
  color: #909399;
  font-size: 14px;
}

.mt20 {
  margin-top: 20px;
}

.eff-row {
  display: flex;
  justify-content: space-around;
  padding: 20px 0;
}

.eff-item {
  text-align: center;
}

.eff-num {
  font-size: 26px;
  font-weight: 700;
  color: #409eff;
}

.eff-label {
  margin-top: 6px;
  color: #909399;
  font-size: 13px;
}

.sys-row {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}

.model-info p {
  margin: 6px 0;
  color: #606266;
}

.model-info code {
  background: #f0f2f5;
  padding: 2px 8px;
  border-radius: 4px;
}
.eff-unit {
  font-size: 16px;
  font-weight: normal;
  color: #909399;
}
.eff-num.speedup {
  color: #67c23a;
}
</style>
