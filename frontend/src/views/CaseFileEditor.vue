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
      提示：编辑后请点「保存」写回服务器；页面关闭后编辑锁自动释放。保存保留文本与常用格式（字体/颜色/边框/对齐/列宽行高/合并单元格），复杂样式可能略有偏差。
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
import { excelCellToXsStyle, xsStyleToExcelStyle, colWidthToPx, colPxToWidth, rowPtToPx, rowPxToPt } from '@/utils/xlsxStyle'

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
// 映射样式: 字体/颜色/对齐/边框/底色 + 列宽 + 行高 + 合并单元格
async function loadWorkbook(buf: ArrayBuffer) {
  const wb = new ExcelJS.Workbook()
  await wb.xlsx.load(buf)
  return wb.worksheets.map((ws) => {
    const styleIdx = new Map<string, number>()
    const styles: any[] = []
    const addStyle = (st: any) => {
      const key = JSON.stringify(st)
      if (!styleIdx.has(key)) {
        styleIdx.set(key, styles.length)
        styles.push(st)
      }
      return styleIdx.get(key)!
    }
    const rows: any = {}
    ws.eachRow({ includeEmpty: false }, (row, rowNum) => {
      const cells: any = {}
      row.eachCell({ includeEmpty: false }, (cell, colNum) => {
        const text = cellText(cell.value)
        const st = excelCellToXsStyle(cell)
        const item: any = { text }
        if (st) item.style = addStyle(st)
        cells[colNum - 1] = item
      })
      if (Object.keys(cells).length) {
        const r: any = { cells }
        if (row.height) r.height = rowPtToPx(row.height)
        rows[rowNum - 1] = r
      }
    })
    const cols: any = {}
    ws.columns.forEach((col, idx) => {
      if (col?.width) cols[idx] = { width: colWidthToPx(col.width) }
    })
    const merges: string[] = (ws.model?.merges as string[]) || []
    return { name: ws.name, styles, rows, cols, merges }
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
    // 默认取视口高度会把底部页签栏(40px)挤出容器被裁掉，必须传容器实际高度
    view: {
      height: () => el.clientHeight - 40,
      width: () => el.clientWidth,
    },
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
      // 解析合并区域: 非锚点单元格跳过写值，最后统一合并
      const covered = new Set<string>()
      const mergeRanges: string[] = []
      for (const m of s.merges || []) {
        const rng = parseRange(m)
        if (!rng) continue
        mergeRanges.push(m)
        for (let r = rng.r1; r <= rng.r2; r++) {
          for (let c = rng.c1; c <= rng.c2; c++) {
            if (r !== rng.r1 || c !== rng.c1) covered.add(`${r}:${c}`)
          }
        }
      }
      Object.entries(s.rows || {}).forEach(([r, rowDef]: [string, any]) => {
        const xr = ws.getRow(Number(r) + 1)
        if (rowDef?.height) xr.height = rowPxToPt(rowDef.height)
        Object.entries(rowDef?.cells || {}).forEach(([c, cellDef]: [string, any]) => {
          if (covered.has(`${r}:${c}`)) return
          const text = cellDef?.text ?? ''
          const xcell = xr.getCell(Number(c) + 1)
          const style = xsStyleToExcelStyle(s.styles?.[cellDef?.style])
          if (style) xcell.style = style
          if (text === '' || text === null) return
          if (typeof text === 'string' && /^-?\d+(\.\d+)?$/.test(text.trim()) && text.trim().length < 16) {
            xcell.value = Number(text.trim())
          } else {
            xcell.value = text
          }
        })
        xr.commit()
      })
      Object.entries(s.cols || {}).forEach(([c, colDef]: [string, any]) => {
        if (colDef?.width) ws.getColumn(Number(c) + 1).width = colPxToWidth(colDef.width)
      })
      mergeRanges.forEach((m) => {
        try { ws.mergeCells(m) } catch { /* 已合并/非法区域忽略 */ }
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

/** 'A1:B2' → {r1,c1,r2,c2}（0 基） */
function parseRange(m: string) {
  const mt = /^([A-Z]+)(\d+):([A-Z]+)(\d+)$/i.exec(m || '')
  if (!mt) return null
  const col = (s: string) => s.toUpperCase().split('').reduce((acc, ch) => acc * 26 + (ch.charCodeAt(0) - 64), 0) - 1
  return { r1: Number(mt[2]) - 1, c1: col(mt[1]), r2: Number(mt[4]) - 1, c2: col(mt[3]) }
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
