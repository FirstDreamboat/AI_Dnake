<template>
  <div class="statistics-page">
    <!-- 顶部工具栏 -->
    <el-card shadow="never" class="toolbar">
      <div class="toolbar-inner">
        <div>
          <el-radio-group v-model="scope" @change="loadAll">
            <el-radio-button value="global">平台全局</el-radio-button>
            <el-radio-button value="project">按项目</el-radio-button>
          </el-radio-group>
          <el-select
            v-if="scope === 'project'"
            v-model="projectId"
            placeholder="选择项目"
            filterable
            style="width: 240px; margin-left: 12px"
            @change="loadAll"
          >
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
          <el-select v-model="days" style="width: 140px; margin-left: 12px" @change="loadTrend">
            <el-option label="近 7 天" :value="7" />
            <el-option label="近 30 天" :value="30" />
            <el-option label="近 90 天" :value="90" />
          </el-select>
        </div>
        <el-button @click="loadAll">
          <el-icon><Refresh /></el-icon>刷新
        </el-button>
      </div>
    </el-card>

    <!-- 总览卡片 -->
    <el-row :gutter="16" class="mt16">
      <el-col :span="4" v-for="card in cards" :key="card.label">
        <el-card shadow="hover" class="stat-card">
          <div class="stat-value" :style="{ color: card.color }">{{ card.value }}</div>
          <div class="stat-label">{{ card.label }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="mt16">
      <!-- 测试类型分布 -->
      <el-col :span="12">
        <el-card shadow="never" header="测试类型分布">
          <div v-if="!typeRows.length" class="empty">暂无数据</div>
          <div v-else class="hbar-group">
            <div v-for="row in typeRows" :key="row.test_type" class="hbar-row">
              <div class="hbar-label">{{ row.test_type }}</div>
              <div class="hbar-track">
                <div class="hbar-fill" :style="{ width: barWidth(row.count, maxTypeCount), background: palette[typeRows.indexOf(row) % palette.length] }"></div>
              </div>
              <div class="hbar-num">{{ row.count }}</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 优先级分布 -->
      <el-col :span="12">
        <el-card shadow="never" header="用例优先级分布">
          <div v-if="totalPriority === 0" class="empty">暂无数据</div>
          <div v-else class="hbar-group">
            <div v-for="p in priorityKeys" :key="p" class="hbar-row">
              <div class="hbar-label pri-label" :style="{ color: priorityColor[p] }">{{ p }}</div>
              <div class="hbar-track">
                <div
                  class="hbar-fill"
                  :style="{ width: barWidth(priorityData[p], totalPriority), background: priorityColor[p] }"
                ></div>
              </div>
              <div class="hbar-num">{{ priorityData[p] }}</div>
            </div>
          </div>
          <el-divider />
          <div class="donut-wrap">
            <div class="donut">
              <svg viewBox="0 0 42 42" class="donut-svg">
                <circle cx="21" cy="21" r="15.915" fill="none" class="donut-ring" />
                <circle
                  v-for="(seg, i) in donutSegments"
                  :key="i"
                  cx="21"
                  cy="21"
                  r="15.915"
                  fill="none"
                  class="donut-seg"
                  :stroke="seg.color"
                  :stroke-dasharray="`${seg.value} ${100 - seg.value}`"
                  :stroke-dashoffset="seg.offset"
                />
              </svg>
              <div class="donut-center">
                <div class="donut-total">{{ totalPriority }}</div>
                <div class="donut-total-label">用例</div>
              </div>
            </div>
            <div class="donut-legend">
              <div v-for="seg in donutSegments" :key="seg.key" class="legend-item">
                <span class="legend-dot" :style="{ background: seg.color }"></span>
                <span>{{ seg.key }}</span>
                <span class="legend-num">{{ seg.count }}</span>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="mt16">
      <!-- 生成趋势 -->
      <el-col :span="14">
        <el-card shadow="never" header="用例 / 脚本生成趋势">
          <div v-if="!trendDates.length" class="empty">暂无数据</div>
          <div v-else>
            <svg :viewBox="`0 0 ${chartW} ${chartH}`" class="trend-svg">
              <line
                v-for="(tick, i) in yTicks"
                :key="'g' + i"
                :x1="padL"
                :y1="tick.y"
                :x2="chartW - padR"
                :y2="tick.y"
                class="grid-line"
              />
              <text
                v-for="(tick, i) in yTicks"
                :key="'yl' + i"
                :x="padL - 8"
                :y="tick.y + 4"
                class="axis-text"
                text-anchor="end"
              >{{ tick.label }}</text>
              <polyline :points="casePoints" fill="none" class="line-case" />
              <polyline :points="scriptPoints" fill="none" class="line-script" />
              <circle v-for="(pt, i) in casePointList" :key="'c' + i" :cx="pt.x" :cy="pt.y" r="3" class="dot-case" />
              <circle v-for="(pt, i) in scriptPointList" :key="'s' + i" :cx="pt.x" :cy="pt.y" r="3" class="dot-script" />
              <text
                v-for="(d, i) in xLabels"
                :key="'xl' + i"
                :x="d.x"
                :y="chartH - 6"
                class="axis-text"
                text-anchor="middle"
              >{{ d.label }}</text>
              <!-- 每列热区：鼠标触碰/触屏点击该列数据点时显示 tooltip -->
              <rect
                v-for="(d, i) in trendDates"
                :key="'hot' + i"
                class="hot-zone"
                :x="xAt(i) - colW / 2"
                :y="padT"
                :width="colW"
                :height="chartH - padT - padB"
                @mouseenter="hoverIndex = i"
                @mouseleave="hoverIndex = -1"
                @touchstart.prevent.stop="hoverIndex = hoverIndex === i ? -1 : i"
              />
              <!-- 悬浮提示层 -->
              <g v-if="hoverIndex >= 0 && hoverIndex < trendDates.length" class="tip-layer">
                <line :x1="hoverX" :y1="padT" :x2="hoverX" :y2="chartH - padB" class="hover-line" />
                <g :transform="`translate(${tipX}, ${tipY})`">
                  <rect :width="tipW" :height="tipH" rx="4" class="tip-box" />
                  <text x="10" y="17" class="tip-title">{{ trendDates[hoverIndex] }}</text>
                  <text x="10" y="37" class="tip-text">
                    <tspan fill="#409EFF">●</tspan> 用例: {{ trendCases[hoverIndex] }}
                  </text>
                  <text x="10" y="55" class="tip-text">
                    <tspan fill="#67C23A">●</tspan> 脚本: {{ trendScripts[hoverIndex] }}
                  </text>
                </g>
              </g>
            </svg>
            <div class="trend-legend">
              <span class="lg-item"><span class="lg-dot lg-case"></span>用例</span>
              <span class="lg-item"><span class="lg-dot lg-script"></span>脚本</span>
            </div>
          </div>
        </el-card>
      </el-col>

      <!-- 来源与质量 + 效率 -->
      <el-col :span="10">
        <el-card shadow="never" header="用例来源与评审质量" class="mb16">
          <el-table :data="qualityRows" size="small" border>
            <el-table-column label="来源" width="100">
              <template #default="{ row }">
                <el-tag size="small" :type="sourceTag[row.source] || 'info'">{{ sourceLabel[row.source] }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="count" label="总数" width="70" />
            <el-table-column prop="reviewed" label="已评审" width="80" />
            <el-table-column label="评审率">
              <template #default="{ row }">{{ row.review_rate }}%</template>
            </el-table-column>
          </el-table>
        </el-card>
        <el-card shadow="never" header="AI 生成效率">
          <div v-if="!eff" class="empty">暂无任务数据</div>
          <div v-else class="eff-grid">
            <div class="eff-cell">
              <div class="eff-num">{{ eff.ai_total_cases }}</div>
              <div class="eff-label">AI 生成用例</div>
            </div>
            <div class="eff-cell">
              <div class="eff-num">{{ eff.avg_cases_per_task }}</div>
              <div class="eff-label">平均用例/任务</div>
            </div>
            <div class="eff-cell">
              <div class="eff-num">{{ eff.ai_avg_time_minutes }}<span class="unit">分钟</span></div>
              <div class="eff-label">AI 平均耗时</div>
            </div>
            <div class="eff-cell">
              <div class="eff-num">{{ manualMin }}<span class="unit">分钟</span></div>
              <div class="eff-label">人工基线</div>
            </div>
            <div class="eff-cell">
              <div class="eff-num eff-rate">{{ saveRate }}%</div>
              <div class="eff-label">时间节省估算</div>
            </div>
            <div class="eff-cell">
              <div class="eff-num">{{ eff.ai_tasks }}</div>
              <div class="eff-label">成功任务数</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { projectApi, statsApi } from '@/api'

const scope = ref('global')
const projectId = ref<number | undefined>(undefined)
const projects = ref<any[]>([])
const days = ref(30)

const cards = ref([
  { label: '项目数', value: 0, color: '#409EFF' },
  { label: '用例总数', value: 0, color: '#67C23A' },
  { label: '生成任务', value: 0, color: '#E6A23C' },
  { label: '需求文档', value: 0, color: '#F56C6C' },
  { label: '用户数', value: 0, color: '#909399' },
  { label: '脚本数', value: 0, color: '#722ED1' },
])

const typeRows = ref<any[]>([])
const priorityData = ref<Record<string, number>>({ P0: 0, P1: 0, P2: 0, P3: 0, P4: 0 })
const qualityRows = ref<any[]>([])
const eff = ref<any>(null)
const trendDates = ref<string[]>([])
const trendCases = ref<number[]>([])
const trendScripts = ref<number[]>([])

const palette = ['#409EFF', '#67C23A', '#E6A23C', '#F56C6C', '#722ED1', '#13C2C2']
const priorityColor: Record<string, string> = {
  P0: '#F56C6C', P1: '#E6A23C', P2: '#409EFF', P3: '#67C23A', P4: '#909399',
}
const sourceLabel: Record<string, string> = { ai: 'AI 生成', manual: '人工录入', ai_reviewed: 'AI 人工评审' }
const sourceTag: Record<string, string> = { ai: 'primary', manual: 'info', ai_reviewed: 'success' }
const priorityKeys = ['P0', 'P1', 'P2', 'P3', 'P4']

const maxTypeCount = computed(() => Math.max(...typeRows.value.map((r) => r.count), 1))
const totalPriority = computed(() => priorityKeys.reduce((s, k) => s + (priorityData.value[k] || 0), 0))
const manualMin = computed(() => eff.value?.manual_baseline?.avg_time_minutes ?? 180)
const saveRate = computed(() => {
  if (!eff.value) return 0
  const ai = eff.value.ai_avg_time_minutes || 10
  return Math.round(((manualMin.value - ai) / manualMin.value) * 100)
})

const barWidth = (v: number, max: number) => (max > 0 ? `${Math.max((v / max) * 100, v > 0 ? 4 : 0)}%` : '0%')

const donutSegments = computed(() => {
  const total = totalPriority.value
  if (!total) return []
  let acc = 0
  return priorityKeys
    .filter((k) => priorityData.value[k] > 0)
    .map((k) => {
      const v = (priorityData.value[k] / total) * 100
      const seg = { key: k, count: priorityData.value[k], value: v, offset: -acc * 3.6, color: priorityColor[k] }
      acc += v
      return seg
    })
})

// ===== SVG 趋势图 =====
const chartW = 640
const chartH = 260
const padL = 36
const padR = 16
const padT = 12
const padB = 30

const maxTrend = computed(() => Math.max(...trendCases.value, ...trendScripts.value, 1))
const yTicks = computed(() => {
  const max = maxTrend.value
  const step = max <= 4 ? 1 : Math.ceil(max / 4)
  const ticks: { y: number; label: string }[] = []
  for (let i = 0; i <= 4; i++) {
    const v = step * i
    const y = padT + (chartH - padT - padB) * (1 - v / (step * 4 || 1))
    ticks.push({ y, label: String(v) })
  }
  return ticks
})
const xLabels = computed(() => {
  const n = trendDates.value.length
  const step = Math.max(1, Math.ceil(n / 8))
  return trendDates.value
    .map((d, i) => ({ x: padL + ((chartW - padL - padR) * i) / Math.max(n - 1, 1), label: d.slice(5) }))
    .filter((_, i) => i % step === 0 || i === n - 1)
})
const toPoints = (arr: number[]) =>
  arr
    .map((v, i) => {
      const n = arr.length
      const x = padL + ((chartW - padL - padR) * i) / Math.max(n - 1, 1)
      const y = padT + (chartH - padT - padB) * (1 - v / (maxTrend.value || 1))
      return `${x},${y}`
    })
    .join(' ')
const pointList = (arr: number[]) =>
  arr.map((v, i) => {
    const n = arr.length
    const x = padL + ((chartW - padL - padR) * i) / Math.max(n - 1, 1)
    const y = padT + (chartH - padT - padB) * (1 - v / (maxTrend.value || 1))
    return { x, y }
  })
const casePoints = computed(() => toPoints(trendCases.value))
const scriptPoints = computed(() => toPoints(trendScripts.value))
const casePointList = computed(() => pointList(trendCases.value))
const scriptPointList = computed(() => pointList(trendScripts.value))

// ===== 悬浮提示（tooltip）=====
const hoverIndex = ref(-1)
const xAt = (i: number) => padL + ((chartW - padL - padR) * i) / Math.max(trendDates.value.length - 1, 1)
const colW = computed(() => (chartW - padL - padR) / Math.max(trendDates.value.length - 1, 1))
const hoverX = computed(() => (hoverIndex.value >= 0 ? xAt(hoverIndex.value) : 0))
const tipW = 126
const tipH = 64
const tipX = computed(() => Math.min(Math.max(hoverX.value - tipW / 2, padL), chartW - padR - tipW))
const tipY = computed(() => {
  const pt = casePointList.value[hoverIndex.value]
  const base = pt ? pt.y : padT + padB
  const y = base - tipH - 14
  return y >= padT ? y : base + 16
})

const params = () => {
  const p: any = {}
  if (scope.value === 'project' && projectId.value) p.project_id = projectId.value
  return p
}

const loadOverview = async () => {
  const o = await statsApi.overview()
  cards.value[0].value = o.project_count
  cards.value[1].value = o.case_count
  cards.value[2].value = o.task_count
  cards.value[3].value = o.doc_count
  cards.value[4].value = o.user_count
  const p = params()
  if (p.project_id) {
    const ps = await statsApi.project(p.project_id)
    cards.value[5].value = ps?.script_count ?? 0
  } else {
    cards.value[5].value = 0
  }
}

const loadDistributions = async () => {
  const p = params()
  const [tt, pri] = await Promise.all([statsApi.testTypes(p), statsApi.priorities(p)])
  typeRows.value = tt?.rows ?? []
  priorityData.value = { P0: 0, P1: 0, P2: 0, P3: 0, P4: 0, ...(pri || {}) }
}

const loadTrend = async () => {
  const p = { ...params(), days: days.value }
  const t = await statsApi.trend(p)
  hoverIndex.value = -1
  trendDates.value = t?.dates ?? []
  trendCases.value = t?.case_counts ?? []
  trendScripts.value = t?.script_counts ?? []
}

const loadQuality = async () => {
  const q = await statsApi.quality()
  qualityRows.value = q?.rows ?? []
}

const loadEfficiency = async () => {
  try {
    eff.value = await statsApi.efficiency()
  } catch {
    eff.value = null
  }
}

const loadProjects = async () => {
  try {
    // 后端接口 page_size 上限为 100，这里分页拉取全部项目
    let list: any[] = []
    let page = 1
    const size = 100
    for (;;) {
      const data = await projectApi.list({ page, page_size: size })
      const rows = data?.list ?? []
      list = list.concat(rows)
      if (rows.length < size || !data?.total || list.length >= data.total) break
      page += 1
    }
    projects.value = list
  } catch {
    projects.value = []
  }
}

const loadAll = async () => {
  try {
    await Promise.all([loadOverview(), loadDistributions(), loadTrend(), loadQuality(), loadEfficiency()])
  } catch {
    // 拦截器已提示
  }
}

onMounted(async () => {
  await loadProjects()
  await loadAll()
})
</script>

<style scoped>
.statistics-page {
  padding: 4px;
}
.toolbar-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.mt16 {
  margin-top: 16px;
}
.mb16 {
  margin-bottom: 16px;
}
.stat-card {
  text-align: center;
}
.stat-value {
  font-size: 28px;
  font-weight: 700;
}
.stat-label {
  margin-top: 6px;
  color: #909399;
  font-size: 13px;
}
.empty {
  color: #909399;
  text-align: center;
  padding: 30px 0;
}
.hbar-group {
  padding: 4px 0;
}
.hbar-row {
  display: flex;
  align-items: center;
  margin: 10px 0;
  gap: 8px;
}
.hbar-label {
  width: 110px;
  text-align: right;
  font-size: 13px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.pri-label {
  font-weight: 700;
  width: 40px;
}
.hbar-track {
  flex: 1;
  height: 16px;
  background: #f0f2f5;
  border-radius: 8px;
  overflow: hidden;
}
.hbar-fill {
  height: 100%;
  border-radius: 8px;
  transition: width 0.4s;
}
.hbar-num {
  width: 40px;
  font-size: 13px;
  color: #606266;
}
.donut-wrap {
  display: flex;
  align-items: center;
  gap: 24px;
  justify-content: center;
  padding: 8px 0;
}
.donut {
  position: relative;
  width: 120px;
  height: 120px;
}
.donut-svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
}
.donut-ring {
  stroke: #f0f2f5;
  stroke-width: 4;
}
.donut-seg {
  stroke-width: 4;
  stroke-linecap: butt;
  transition: stroke-dasharray 0.5s;
}
.donut-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}
.donut-total {
  font-size: 22px;
  font-weight: 700;
  color: #303133;
}
.donut-total-label {
  font-size: 12px;
  color: #909399;
}
.donut-legend {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #606266;
}
.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}
.legend-num {
  color: #303133;
  font-weight: 600;
  min-width: 24px;
  text-align: right;
}
.trend-svg {
  width: 100%;
  height: auto;
}
.grid-line {
  stroke: #e8eaed;
  stroke-width: 1;
}
.axis-text {
  font-size: 11px;
  fill: #909399;
}
.line-case {
  stroke: #409eff;
  stroke-width: 2;
  stroke-linejoin: round;
}
.line-script {
  stroke: #67c23a;
  stroke-width: 2;
  stroke-linejoin: round;
}
.dot-case {
  fill: #409eff;
}
.dot-script {
  fill: #67c23a;
}
.hot-zone {
  fill: transparent;
  pointer-events: all;
}
.tip-layer {
  pointer-events: none;
}
.hover-line {
  stroke: #c0c4cc;
  stroke-width: 1;
  stroke-dasharray: 4 3;
}
.tip-box {
  fill: rgba(48, 49, 51, 0.92);
}
.tip-title {
  fill: #fff;
  font-size: 12px;
  font-weight: 600;
}
.tip-text {
  fill: #fff;
  font-size: 12px;
}
.trend-legend {
  display: flex;
  justify-content: flex-end;
  gap: 16px;
  margin-top: 8px;
}
.lg-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #606266;
}
.lg-dot {
  width: 12px;
  height: 4px;
  border-radius: 2px;
}
.lg-case {
  background: #409eff;
}
.lg-script {
  background: #67c23a;
}
.eff-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.eff-cell {
  text-align: center;
  padding: 8px 0;
}
.eff-num {
  font-size: 20px;
  font-weight: 700;
  color: #409eff;
}
.eff-num .unit {
  font-size: 12px;
  color: #909399;
  font-weight: 400;
  margin-left: 2px;
}
.eff-rate {
  color: #67c23a;
}
.eff-label {
  margin-top: 4px;
  font-size: 12px;
  color: #909399;
}
</style>
