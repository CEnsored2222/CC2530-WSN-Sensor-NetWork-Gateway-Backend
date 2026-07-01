/**
 * 纯前端 CSV 导出(通过 Blob 下载)
 * @param {Array<Object>} rows - 数据行
 * @param {Array<{key:string,label:string}>} columns - 列定义
 * @param {string} filename - 文件名(不含扩展名)
 */
export function exportCsv(rows, columns, filename = 'export') {
  if (!rows || !rows.length) return

  const header = columns.map((c) => escapeCsv(c.label)).join(',')
  const body = rows
    .map((row) => columns.map((c) => escapeCsv(formatValue(row[c.key]))).join(','))
    .join('\n')

  // BOM 让 Excel 正确识别 UTF-8
  const csv = '\uFEFF' + header + '\n' + body
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${filename}_${formatDate(new Date())}.csv`
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}

function escapeCsv(val) {
  const s = String(val ?? '')
  if (/[",\n]/.test(s)) {
    return '"' + s.replace(/"/g, '""') + '"'
  }
  return s
}

function formatValue(v) {
  if (v === null || v === undefined) return ''
  if (typeof v === 'object') return JSON.stringify(v)
  return v
}

function pad(n) { return String(n).padStart(2, '0') }
function formatDate(d) {
  return `${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}_${pad(d.getHours())}${pad(d.getMinutes())}`
}
