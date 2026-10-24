<template>
  <div class="editor-page">
    <div class="ed-topbar">
      <el-button :icon="Back" @click="goBack">返回列表</el-button>
      <span class="ed-fname">📄 {{ filename }}</span>
      <el-tag v-if="editable" type="success">● 你正在编辑（其他人为只读）</el-tag>
      <el-tag v-else type="warning">🔒 {{ lockHolder }} 正在编辑 · 你当前为只读</el-tag>
      <div class="flex-spacer"></div>
      <el-select v-if="sheetNames.length > 1" v-model="currentSheet" size="small" style="width:160px" @change="switchSheet">
        <el-option v-for="(name, i) in sheetNames" :key="i" :label="name" :value="i" />
      </el-select>
      <el-button :icon="Download" @click="download">下载</el-button>
      <el-button type="primary" :icon="Check" :disabled="!editable" :loading="saving" @click="save">保存</el-button>
    </div>
    <div v-if="!editable" class="ed-banner warn">
      ⚠ 该文件正被 {{ lockHolder }} 编辑，你的修改不会被保存。对方关闭后锁定自动释放，返回列表重新打开即可编辑。
    </div>
    <div v-else class="ed-banner ok">
      提示：编辑后请点「保存」写回服务器；页面关闭后编辑锁自动释放。保存仅保留单元格文本（样式/公式转为计算值）。
    </div>
    <div ref="gridRef" class="grid-container"></div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Back, Check, Download } from '@element-plus/icons-vue'
import ExcelJS from 'exceljs'
import Spreadsheet from 'x-data-spreadsheet'
import 'x-data-spreadsheet/dist/xspreadsheet.css'
import { caseFileApi } from '@/api'

const route = useRoute()
const router = useRouter()
const fileId = Number(route.params.fileId)

const filename = ref('')
const editable = ref(false)
const lockHolder = ref('')
const saving = ref(false)
const currentSheet = ref(0)
const sheetNames = ref<string[]>([])
const gridRef = ref<HTMLDivElement>()

let sheetsStore: { name: string; rows: any }[] = []
let sp: any = null
let heartbeatTimer: number | null = null
let dirty = false

function cellText(v: any): string {
  if (v === null || v === undefined) return ''
  if (typeof v === 'object') {
    if (v instanceof Date) {
      const p = (n: number) => String(n).padStart(2, '0')
      return `${v.getFullYear()}-${p(v.getMonth() + 1)}-${p(v.getDate())} ${p(v.getHours())}:${p(v.getMinutes())}:${p(v.getSeconds())}`
    }
    if (Array.isArray(v.richText)) return v.richText.map((t: any) => t.text).join('')
    if (v.result !== undefined) return String(v.result ?? '')
    if (v.text !== undefined) return String(v.text)
    if (v.hyperlink) return String(v.hyperlink)
    return String(v)
  }
  return String(v)
}

async function loadWorkbook(buf: ArrayBuffer) {
  const wb = new ExcelJS.Workbook()
  await wb.xlsx.load(buf)
  sheetsStore = wb.worksheets.map((ws) => {
    const rows: any = {}
    ws.eachRow({ includeEmpty: false }, (row, rowNum) => {
      const cells: any = {}
      row.eachCell({ includeEmpty: false }, (cell, colNum) => {
        const text = cellText(cell.value)
        if (text !== '') cells[colNum - 1] = { text }
      })
      if (Object.keys(cells).length) rows[rowNum - 1] = { cells }
    })
    return { name: ws.name, rows }
  })
  sheetNames.value = sheetsStore.map((s) => s.name)
  currentSheet.value = 0
}

function renderGrid() {
  const el = gridRef.value
  if (!el) return
  el.innerHTML = ''
  const store = sheetsStore[currentSheet.value]
  sp = new Spreadsheet(el, {
    mode: editable.value ? 'edit' : 'read',
    showToolbar: true,
    showGrid: true,
    showContextmenu: editable.value,
    row: { len: Math.max(100, Object.keys(store.rows || {}).length + 20), height: 25 },
    col: { len: 26, width: 120, minWidth: 60, indexWidth: 46 },
  })
  sp.loadData({ name: store.name, rows: JSON.parse(JSON.stringify(store.rows || {})) })
  sp.change(() => {
    dirty = true
    pullCurrentRows()
  })
}

function pullCurrentRows() {
  if (!sp) return
  try {
    let data = sp.getData()
    if (Array.isArray(data)) data = data[0]
    if (data && data.rows) sheetsStore[currentSheet.value].rows = data.rows
  } catch {
    /* 取数异常时以最后一次成功数据为准 */
  }
}

function switchSheet() {
  pullCurrentRows()
  renderGrid()
}

async function save() {
  pullCurrentRows()
  saving.value = true
  try {
    const wb = new ExcelJS.Workbook()
    const used = new Set<string>()
    sheetsStore.forEach((s, i) => {
      let name = (s.name || `Sheet${i + 1}`).replace(/[/\\*?:[\]]/g, '_').slice(0, 31) || `Sheet${i + 1}`
      while (used.has(name)) name = `${name.slice(0, 28)}_${i}`
      used.add(name)
      const ws = wb.addWorksheet(name)
      Object.entries(s.rows || {}).forEach(([r, rowDef]: [string, any]) => {
        const xr = ws.getRow(Number(r) + 1)
        Object.entries(rowDef?.cells || {}).forEach(([c, cellDef]: [string, any]) => {
          const text = cellDef?.text ?? ''
          if (text === '' || text === null) return
          if (typeof text === 'string' && /^-?\d+(\.\d+)?$/.test(text.trim()) && text.trim().length < 16) {
            xr.getCell(Number(c) + 1).value = Number(text.trim())
          } else {
            xr.getCell(Number(c) + 1).value = text
          }
        })
        xr.commit()
      })
    })
    const buf = await wb.xlsx.writeBuffer()
    await caseFileApi.save(fileId, new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }))
    dirty = false
    ElMessage.success('保存成功')
  } finally {
    saving.value = false
  }
}

function download() {
  caseFileApi.download(fileId).then((blob: any) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename.value
    a.click()
    URL.revokeObjectURL(url)
  })
}

function goBack() {
  router.push(`/projects/${route.query.project_id}/case-files`)
}

function startHeartbeat() {
  heartbeatTimer = window.setInterval(async () => {
    try {
      await caseFileApi.heartbeat(fileId)
    } catch (e: any) {
      if (e?.response?.status === 409) {
        editable.value = false
        lockHolder.value = '他人'
        stopHeartbeat()
        renderGrid()
        ElMessage.warning('编辑锁已失效，已切换为只读模式')
      }
    }
  }, 30000)
}

function stopHeartbeat() {
  if (heartbeatTimer) {
    clearInterval(heartbeatTimer)
    heartbeatTimer = null
  }
}

function beforeUnloadHandler(e: BeforeUnloadEvent) {
  if (dirty) {
    e.preventDefault()
    e.returnValue = ''
  }
}

onMounted(async () => {
  const res: any = await caseFileApi.open(fileId)
  const payload = res?.data ?? res
  filename.value = payload?.file?.filename || '未命名'
  editable.value = !!payload?.lock?.acquired
  lockHolder.value = payload?.lock?.holder_name || ''

  const blob: any = await caseFileApi.download(fileId)
  await loadWorkbook(await blob.arrayBuffer())
  renderGrid()

  if (editable.value) {
    startHeartbeat()
    window.addEventListener('beforeunload', beforeUnloadHandler)
  }
})

onBeforeUnmount(() => {
  stopHeartbeat()
  window.removeEventListener('beforeunload', beforeUnloadHandler)
  if (editable.value) {
    caseFileApi.release(fileId).catch(() => {})
  }
})
</script>

<style scoped>
.editor-page { position: fixed; inset: 0; background: #fff; display: flex; flex-direction: column; z-index: 100; }
.ed-topbar { display: flex; align-items: center; gap: 12px; padding: 8px 16px; border-bottom: 1px solid #e4e7ed; background: #f8f9fb; }
.ed-fname { font-size: 14px; font-weight: bold; color: #303133; }
.flex-spacer { flex: 1; }
.ed-banner { padding: 7px 16px; font-size: 13px; }
.ed-banner.warn { background: #fdf6ec; color: #e6a23c; border-bottom: 1px solid #faecd8; }
.ed-banner.ok { background: #f0f9eb; color: #67c23a; border-bottom: 1px solid #e1f3d8; }
.grid-container { flex: 1; overflow: hidden; }
</style>
