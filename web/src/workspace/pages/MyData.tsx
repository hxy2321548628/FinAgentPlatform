import { useState, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

interface DataFile {
  id: string; name: string; size: string; uploadTime: string
  type: 'csv' | 'xlsx' | 'pdf' | 'txt'
}

const FILE_TYPE_STYLE: Record<DataFile['type'], { bg: string; color: string }> = {
  csv:  { bg: '#ECFDF5', color: '#059669' },
  xlsx: { bg: '#EFF6FF', color: '#2563EB' },
  pdf:  { bg: '#FEF2F2', color: '#DC2626' },
  txt:  { bg: '#F9FAFB', color: '#6B7280' },
}

const MOCK_FILES: DataFile[] = [
  { id: '1', name: 'portfolio_2026Q2.csv', size: '1.2 MB', uploadTime: '2026-08-06', type: 'csv' },
  { id: '2', name: 'fund_nav_history.xlsx', size: '4.8 MB', uploadTime: '2026-07-28', type: 'xlsx' },
  { id: '3', name: 'macro_indicators.csv', size: '0.9 MB', uploadTime: '2026-07-20', type: 'csv' },
  { id: '4', name: 'annual_report_2025.pdf', size: '12.3 MB', uploadTime: '2026-07-15', type: 'pdf' },
]

export function MyData() {
  const navigate = useNavigate()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [files, setFiles] = useState(MOCK_FILES)
  const [dragOver, setDragOver] = useState(false)

  const handleDelete = (id: string) => setFiles(prev => prev.filter(f => f.id !== id))
  const handleAnalyze = (file: DataFile) => navigate(`/workspace/chat?file=${encodeURIComponent(file.name)}`)

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: '32px 36px', background: 'var(--bg)' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28 }}>
        <div>
          <div style={{ fontSize: 10, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const, letterSpacing: '0.3em', color: 'var(--text-muted)', marginBottom: 6 }}>// MY DATA</div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 4 }}>我的数据</h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>管理上传的数据文件，点击「分析」直接进入对话</p>
        </div>
        <div>
          <input ref={fileInputRef} type="file" multiple accept=".csv,.xlsx,.xls,.pdf,.txt" style={{ display: 'none' }} />
          <button onClick={() => fileInputRef.current?.click()} style={{ padding: '9px 20px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 7, fontSize: 13, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>↑ 上传文件</button>
        </div>
      </div>

      {/* 拖拽上传区 */}
      <div
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => { e.preventDefault(); setDragOver(false) }}
        onClick={() => fileInputRef.current?.click()}
        style={{ border: '1.5px dashed ' + (dragOver ? 'var(--action)' : 'var(--border)'), borderRadius: 10, padding: 28, textAlign: 'center' as const, background: dragOver ? 'var(--action-light)' : 'var(--surface)', marginBottom: 20, cursor: 'pointer', transition: 'border-color 0.2s, background 0.2s' }}
      >
        <div style={{ fontSize: 24, marginBottom: 8 }}>📁</div>
        <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 4 }}>拖拽文件到此处，或点击上传</div>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>支持 CSV · XLSX · PDF · TXT，单文件最大 50 MB</div>
      </div>

      {/* 文件列表 */}
      <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '2fr 100px 120px 160px', padding: '10px 20px', borderBottom: '1px solid var(--border)', background: 'var(--bg)' }}>
          {['文件名', '大小', '上传时间', '操作'].map(h => <div key={h} style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase' as const, letterSpacing: '0.1em' }}>{h}</div>)}
        </div>
        {files.length === 0 ? (
          <div style={{ padding: '40px 20px', textAlign: 'center' as const, color: 'var(--text-muted)', fontSize: 13 }}>暂无文件，请上传数据文件</div>
        ) : files.map((file, i) => {
          const ts = FILE_TYPE_STYLE[file.type]
          return (
            <div key={file.id} style={{ display: 'grid', gridTemplateColumns: '2fr 100px 120px 160px', padding: '14px 20px', borderBottom: i < files.length - 1 ? '1px solid var(--border-light)' : 'none', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <span style={{ padding: '2px 7px', borderRadius: 4, fontSize: 11, fontWeight: 700, background: ts.bg, color: ts.color, fontFamily: "'JetBrains Mono', monospace", textTransform: 'uppercase' as const }}>{file.type}</span>
                <span style={{ fontSize: 13, color: 'var(--text-primary)', fontWeight: 500 }}>{file.name}</span>
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{file.size}</div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{file.uploadTime}</div>
              <div style={{ display: 'flex', gap: 6 }}>
                <button onClick={() => handleAnalyze(file)} style={{ padding: '5px 12px', background: 'var(--action)', color: '#fff', border: 'none', borderRadius: 5, fontSize: 12, fontWeight: 600, cursor: 'pointer', fontFamily: 'inherit' }}>分析</button>
                <button style={{ padding: '5px 12px', background: 'transparent', color: 'var(--text-secondary)', border: '1px solid var(--border)', borderRadius: 5, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>下载</button>
                <button onClick={() => handleDelete(file.id)} style={{ padding: '5px 12px', background: 'transparent', color: '#DC2626', border: '1px solid #FECACA', borderRadius: 5, fontSize: 12, cursor: 'pointer', fontFamily: 'inherit' }}>删除</button>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
