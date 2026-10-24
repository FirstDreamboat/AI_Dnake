/**
 * exceljs ↔ x-spreadsheet 样式映射
 * 单位换算: Excel列宽(字符)→px ≈ w*7+5；行高(pt)→px ≈ h*4/3；字号 pt→px ≈ s*4/3
 */
export function argbToHex(argb?: string | null): string | null {
  if (!argb) return null
  const s = String(argb).toUpperCase().replace('#', '')
  if (s.length === 8) return `#${s.slice(2)}`
  if (s.length === 6) return `#${s}`
  return null
}

export function hexToArgb(hex?: string | null): string | undefined {
  if (!hex) return undefined
  return `FF${hex.replace('#', '').toUpperCase()}`
}

const B_XS2XL: Record<string, string> = {
  thin: 'thin', medium: 'medium', thick: 'thick',
  dashed: 'dashed', dotted: 'dashed', double: 'double',
}
const B_XL2XS: Record<string, string> = {
  thin: 'thin', medium: 'medium', thick: 'thick', double: 'double',
  dashed: 'dashed', dashDot: 'dashed', dashDotDot: 'dashed',
  dotted: 'dashed', hair: 'thin', mediumDashed: 'dashed',
  mediumDashDot: 'dashed', slantDashDot: 'dashed',
}

/** exceljs 单元格 → x-spreadsheet 样式对象（无有效样式返回 null） */
export function excelCellToXsStyle(cell: any): any | null {
  const st: any = {}
  const f = cell?.font
  if (f) {
    const font: any = {}
    if (f.name) font.name = f.name
    if (f.size) font.size = Math.min(72, Math.max(6, Math.round(f.size)))
    if (f.bold) font.bold = true
    if (f.italic) font.italic = true
    if (f.underline) font.underline = true
    if (f.strike) font.strike = true
    const color = argbToHex(f.color?.argb)
    if (color && color !== '#000000') st.color = color
    if (Object.keys(font).length) st.font = font
  }
  const fillHex = argbToHex(cell?.fill?.fgColor?.argb)
  const isSolid = cell?.fill?.pattern === 'solid' || cell?.fill?.patternType === 'solid'
  if (isSolid && fillHex && fillHex !== '#ffffff') st.bgcolor = fillHex
  const a = cell?.alignment
  if (a?.horizontal && a.horizontal !== 'general') st.align = a.horizontal
  if (a?.vertical && a.vertical !== 'middle') st.valign = a.vertical
  if (a?.wrapText) st.textwrap = true
  const b = cell?.border
  if (b) {
    const border: any = {}
    for (const side of ['top', 'bottom', 'left', 'right'] as const) {
      const bs = b[side]
      if (bs?.style) border[side] = [B_XL2XS[bs.style] || 'thin', argbToHex(bs.color?.argb) || '#000000']
    }
    if (Object.keys(border).length) st.border = border
  }
  return Object.keys(st).length ? st : null
}

/** x-spreadsheet 样式对象 → exceljs 单元格样式（无有效样式返回 null） */
export function xsStyleToExcelStyle(st: any): any | null {
  if (!st) return null
  const out: any = {}
  const font: any = {}
  const f = st.font
  if (f) {
    if (f.bold) font.bold = true
    if (f.italic) font.italic = true
    if (f.underline) font.underline = { style: 'single' }
    if (f.strike) font.strike = true
    if (f.name) font.name = f.name
    if (f.size) font.size = Math.max(6, Math.round(f.size))
  }
  const color = hexToArgb(st.color)
  if (color) font.color = { argb: color }
  if (Object.keys(font).length) out.font = font
  if (st.bgcolor && st.bgcolor !== '#ffffff') {
    out.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: hexToArgb(st.bgcolor) } }
  }
  if (st.align && st.align !== 'left') (out.alignment = out.alignment || {}).horizontal = st.align
  if (st.valign && st.valign !== 'middle') (out.alignment = out.alignment || {}).vertical = st.valign
  if (st.textwrap) (out.alignment = out.alignment || {}).wrapText = true
  if (st.border) {
    const border: any = {}
    for (const side of ['top', 'bottom', 'left', 'right'] as const) {
      const bs = st.border[side]
      if (Array.isArray(bs)) border[side] = { style: B_XS2XL[bs[0]] || 'thin', color: { argb: hexToArgb(bs[1]) } }
    }
    if (Object.keys(border).length) out.border = border
  }
  return Object.keys(out).length ? out : null
}

export function colWidthToPx(w: number): number {
  return Math.max(30, Math.min(600, Math.round(w * 7 + 5)))
}

export function colPxToWidth(px: number): number {
  return Math.max(5, Math.min(80, Math.round(((px - 5) / 7) * 10) / 10))
}

export function rowPtToPx(h: number): number {
  return Math.max(15, Math.min(300, Math.round(h * 4 / 3)))
}

export function rowPxToPt(h: number): number {
  return Math.max(6, Math.round(h * 0.75 * 10) / 10)
}
