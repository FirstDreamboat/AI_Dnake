<template>
  <div class="report-view">
    <el-row :gutter="20">
      <el-col :span="6">
        <div class="score-box" :class="scoreClass">
          <div class="score-num">{{ report.score }}</div>
          <div class="score-label">{{ scoreLabel }}</div>
        </div>
      </el-col>
      <el-col :span="18">
        <div class="summary">{{ report.summary }}</div>
        <div class="metrics">
          <el-tag size="small">需求 {{ report.metrics?.requirement_count ?? 0 }} 条</el-tag>
          <el-tag size="small" type="success">测试点 {{ report.metrics?.test_point_count ?? 0 }} 个</el-tag>
          <el-tag size="small" type="warning">隐式场景 {{ report.metrics?.implicit_count ?? 0 }} 个</el-tag>
        </div>
        <div v-if="report.metrics?.technique_distribution" class="tech-dist">
          <span class="dist-label">设计技术分布：</span>
          <el-tag
            v-for="(c, k) in report.metrics.technique_distribution"
            :key="k"
            size="small"
            effect="plain"
          >
            {{ techLabel(String(k)) }} {{ c }}
          </el-tag>
        </div>
      </el-col>
    </el-row>

    <el-divider />

    <h4>问题清单（{{ report.issues?.length ?? 0 }} 项）</h4>
    <el-table v-if="report.issues?.length" :data="report.issues" border stripe size="small">
      <el-table-column label="类型" width="120">
        <template #default="{ row }">
          <el-tag size="small" :type="issueTag(row.type)">{{ row.type }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="requirement" label="关联需求" width="140" show-overflow-tooltip />
      <el-table-column label="严重度" width="80">
        <template #default="{ row }">
          <el-tag size="small" :type="sevTag(row.severity)" effect="dark">{{ row.severity }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="问题描述" min-width="260" show-overflow-tooltip />
      <el-table-column prop="suggestion" label="修改建议" min-width="240" show-overflow-tooltip />
    </el-table>
    <el-empty v-else description="未发现需求质量问题" />

    <el-divider />
    <h4>亮点</h4>
    <ul v-if="report.highlights?.length" class="highlights">
      <li v-for="(h, i) in report.highlights" :key="i">{{ h }}</li>
    </ul>
    <el-empty v-else description="无" :image-size="60" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{ report: any }>()
const report = computed(() => props.report || {})

const scoreClass = computed(() => {
  const s = report.value.score ?? 0
  if (s >= 85) return 'good'
  if (s >= 70) return 'mid'
  return 'bad'
})
const scoreLabel = computed(() => {
  const s = report.value.score ?? 0
  if (s >= 85) return '优秀'
  if (s >= 70) return '良好'
  if (s >= 60) return '及格'
  return '不及格'
})

const techMap: Record<string, string> = {
  equivalence: '等价类',
  boundary: '边界值',
  decision_table: '判定表',
  state_transition: '状态迁移',
  scenario: '场景法',
  orthogonal: '正交表',
  error_guessing: '错误推测',
  none: '常规',
}
const techLabel = (k: string) => techMap[k] || k

const issueTagMap: Record<string, string> = {
  歧义表述: 'warning',
  缺失边界: 'danger',
  流程断点: 'warning',
  异常未定义: 'danger',
  隐式场景过多: 'info',
  优先级不当: 'info',
}
const issueTag = (t: string) => issueTagMap[t] || 'primary'
const sevTag = (s: string) => ({ 高: 'danger', 中: 'warning', 低: 'info' }[s] || 'info')
</script>

<style scoped>
.score-box {
  text-align: center;
  padding: 20px;
  border-radius: 8px;
}
.score-box.good { background: #f0f9eb; }
.score-box.mid { background: #fdf6ec; }
.score-box.bad { background: #fef0f0; }
.score-num { font-size: 48px; font-weight: 700; line-height: 1.1; }
.score-box.good .score-num { color: #67c23a; }
.score-box.mid .score-num { color: #e6a23c; }
.score-box.bad .score-num { color: #f56c6c; }
.score-label { font-size: 14px; color: #606266; margin-top: 4px; }
.summary { font-size: 14px; color: #303133; line-height: 1.7; }
.metrics { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 8px; }
.tech-dist { margin-top: 12px; display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.dist-label { font-size: 13px; color: #606266; }
h4 { margin: 8px 0 12px; color: #303133; }
.highlights { margin: 0; padding-left: 20px; color: #606266; line-height: 2; }
</style>
