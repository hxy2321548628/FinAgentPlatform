import { useEffect, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { Button } from '../../components/ui/Button'

interface PublishDialogProps {
  kindLabel: string
  initialName: string
  initialDescription: string
  existingNames: string[]
  onClose: () => void
  onSubmit: (name: string, description: string) => void
}

export function PublishDialog({ kindLabel, initialName, initialDescription, existingNames, onClose, onSubmit }: PublishDialogProps) {
  const [name, setName] = useState(initialName)
  const [description, setDescription] = useState(initialDescription)

  useEffect(() => {
    setName(initialName)
    setDescription(initialDescription)
  }, [initialDescription, initialName])

  const normalizedName = name.trim()
  const duplicate = existingNames.some(existing => existing.trim().toLocaleLowerCase('zh-CN') === normalizedName.toLocaleLowerCase('zh-CN'))
  const ready = Boolean(normalizedName && description.trim() && !duplicate)

  const submit = (event: React.FormEvent) => {
    event.preventDefault()
    if (!ready) return
    onSubmit(normalizedName, description.trim())
  }

  return (
    <Dialog.Root defaultOpen onOpenChange={open => {
      if (!open) onClose()
    }}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay" onClick={onClose} />
        <Dialog.Content className="dialog-content" style={{ width: 'min(520px, calc(100vw - 40px))' }} aria-describedby={undefined}>
          <Dialog.Title className="dialog-title" style={{ marginBottom: 4 }}>发布{kindLabel}</Dialog.Title>
          <Dialog.Description className="dialog-desc" style={{ marginBottom: 18 }}>公开名称在你名下不能重名，提交后进入审核，不会离开当前页面。</Dialog.Description>
          <Dialog.Close asChild>
            <button type="button" aria-label="关闭" className="dialog-close-x">×</button>
          </Dialog.Close>
          <form onSubmit={submit}>
            <div style={{ marginBottom: 16 }}>
              <label style={labelStyle}>公开名称 <span style={{ color: 'var(--danger)' }}>*</span></label>
              <input value={name} onChange={event => setName(event.target.value)} placeholder={`请输入${kindLabel}公开名称`} style={{ ...inputStyle, borderColor: duplicate ? 'var(--danger)' : 'var(--border)' }} />
              {duplicate && <div style={{ fontSize: 12, color: 'var(--danger)', marginTop: 6 }}>该名称已被使用，请换一个公开名称。</div>}
            </div>
            <div style={{ marginBottom: 20 }}>
              <label style={labelStyle}>公开描述 <span style={{ color: 'var(--danger)' }}>*</span></label>
              <textarea value={description} onChange={event => setDescription(event.target.value)} placeholder={`说明${kindLabel}解决的问题、适用范围和主要输出`} style={{ ...inputStyle, minHeight: 110, resize: 'vertical' }} />
            </div>
            <div className="dialog-actions">
              <Button variant="secondary" size="md" onClick={onClose}>取消</Button>
              <Button variant="primary" size="md" type="submit" disabled={!ready}>提交审核</Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

const labelStyle: React.CSSProperties = { display: 'block', fontSize: 13, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 6 }
const inputStyle: React.CSSProperties = { width: '100%', boxSizing: 'border-box', padding: '9px 12px', border: '1px solid var(--border)', borderRadius: 7, background: 'var(--surface)', color: 'var(--text-primary)', fontSize: 13, fontFamily: 'inherit' }
