import type { TodoItem } from '../../api/events'

/**
 * agent 自己维护的那张任务清单。
 *
 * **报的是进度，不是一次工具调用** —— 所以它不走消息列表里的工具卡片，
 * `write_todos` 那张卡片在 reducer 里已经被收编掉了，否则同一件事显示两遍：
 * 一遍中文清单，一遍正文是英文 `Updated todo list to [...]` 的工具卡。
 *
 * 只有主图有清单，因此这里不分 `path`。
 */
interface TodoListProps {
  todos: TodoItem[]
}

const MARK: Record<TodoItem['status'], string> = {
  pending: '○',
  in_progress: '◐',
  completed: '●',
}

const TONE: Record<TodoItem['status'], string> = {
  pending: 'var(--text-muted)',
  in_progress: 'var(--action)',
  completed: 'var(--status-done)',
}

export function TodoList({ todos }: TodoListProps) {
  if (todos.length === 0) return null
  const done = todos.filter(one => one.status === 'completed').length
  return <section
    aria-label="任务清单"
    data-testid="todo-list"
    style={{ margin: '0 0 12px 44px', padding: '11px 14px', border: '1px solid var(--border-light)', borderRadius: 8, background: 'var(--surface)' }}
  >
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 8 }}>
      <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>任务清单</span>
      <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>已完成 {done}/{todos.length}</span>
    </div>
    <ol style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 5 }}>
      {todos.map((todo, index) => <li
        key={`${index}-${todo.content}`}
        data-status={todo.status}
        style={{ display: 'flex', gap: 8, fontSize: 12.5, lineHeight: 1.6, color: todo.status === 'completed' ? 'var(--text-muted)' : 'var(--text-primary)' }}
      >
        <span aria-hidden style={{ color: TONE[todo.status] }}>{MARK[todo.status]}</span>
        <span style={{ textDecoration: todo.status === 'completed' ? 'line-through' : 'none' }}>{todo.content}</span>
      </li>)}
    </ol>
  </section>
}
