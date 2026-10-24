<template>
  <div class="editor-page">
    <div class="ed-topbar">
      <el-button :icon="Back" @click="goBack">返回列表</el-button>
      <span class="ed-fname">📄 {{ filename }}</span>
      <el-tag v-if="preview" type="info">预览模式</el-tag>
      <el-tag v-else-if="editable" type="success">● 你正在编辑（其他人为只读）</el-tag>
      <el-tag v-else type="warning">🔒 {{ lockHolder }} 正在编辑 · 只读</el-tag>
      <div class="flex-spacer"></div>
      <el-button :icon="Download" @click="download">下载</el-button>
      <el-button type="primary" :icon="Check" :disabled="!editable" :loading="saving" @click="save">保存</el-button>
    </div>
    <div v-if="preview" class="ed-banner ok">
      当前为预览模式（只读，不占用编辑锁）。需要修改请返回列表点击「打开编辑」。底部页签可切换工作表。
    </div>
    <div v-else-if="!editable" class="ed-banner warn">
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
const preview = ref(false)
const gridRef = ref<HTMLDivElement>()

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

// 解析 xlsx → x-spreadsheet 多 sheet 数组（底部页签由组件原生渲染与切换）
async function loadWorkbook(buf: ArrayBuffer) {
  const wb = new ExcelJS.Workbook()
  await wb.xlsx.load(buf)
  return wb.worksheets.map((ws) => {
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
}

function renderGrid(sheets: any[]) {
  const el = gridRef.value
  if (!el) return
  el.innerHTML = ''
  const maxRow = Math.max(100, ...sheets.map((s) => Object.keys(s.rows || {}).length + 20))
  sp = new Spreadsheet(el, {
    mode: editable.value ? 'edit' : 'read',
    showToolbar: true,
    showGrid: true,
    showContextmenu: editable.value,
    row: { len: maxRow, height: 25 },
    col: { len: 26, width: 120, minWidth: 60, indexWidth: 46 },
  })
  sp.loadData(JSON.parse(JSON.stringify(sheets)))
  sp.change(() => {
    dirty = true
  })
}

// 保存：直接从组件取回全部 sheet 数据重建 xlsx
async function save() {
  saving.value = true
  try {
    let all: any[] = sp.getData()
    if (!Array.isArray(all)) all = [all]
    const wb = new ExcelJS.Workbook()
    const used = new Set<string>()
    all.forEach((s, i) => {
      let name = (s?.name || `Sheet${i + 1}`).replace(/[/\\*?:[\]]/g, '_').slice(0, 31) || `Sheet${i + 1}`
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
  preview.value = route.query.preview === '1'
  if (!preview.value) {
    const res: any = await caseFileApi.open(fileId)
    const payload = res?.data ?? res
    filename.value = payload?.file?.filename || (route.query.name as string) || '未命名'
    editable.value = !!payload?.lock?.acquired
    lockHolder.value = payload?.lock?.holder_name || ''
  } else {
    filename.value = (route.query.name as string) || '未命名'
  }

  const blob: any = await caseFileApi.download(fileId)
  const sheets = await loadWorkbook(await blob.arrayBuffer())
  renderGrid(sheets)

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
