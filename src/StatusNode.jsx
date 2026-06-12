import { Handle, Position } from '@xyflow/react'

// BigQuery-style type chips: short uppercase label + category color.
const TYPES = {
  rpg: { label: 'RPG', color: '#5e35b1' },
  cl: { label: 'CL', color: '#00838f' },
  cobol: { label: 'CBL', color: '#00695c' },
  sql: { label: 'SQL', color: '#1a73e8' },
  python: { label: 'PY', color: '#1e8e3e' },
  view: { label: 'VIEW', color: '#5f6368' },
  file: { label: 'FILE', color: '#5f6368' },
  table: { label: 'TBL', color: '#5f6368' },
  skill: { label: 'TASK', color: '#1a73e8' },
}

const STATUS_TEXT = {
  pending: 'Pending',
  running: 'Running',
  done: 'Done',
  error: 'Failed',
  skipped: 'Skipped',
}

export default function StatusNode({ data }) {
  const status = data.status || 'pending'
  const progress = status === 'done' ? 100 : data.progress || 0
  const type = TYPES[data.type] || (data.kind === 'skill' ? TYPES.skill : TYPES.table)

  return (
    <div className={`node-card ${status} ${data.isTarget ? 'target' : ''}`}>
      {data.order != null && <div className="order-badge">{data.order}</div>}
      {data.isTarget && <div className="target-badge">TARGET</div>}

      <div className="node-head">
        <span className="type-badge" style={{ background: type.color }}>
          {type.label}
        </span>
        <span className="node-title" title={data.name || data.label || data.id}>
          {data.name || data.label || data.id}
        </span>
      </div>

      <div className="node-detail">{data.detail || ' '}</div>

      <div className="bar-wrap">
        <div className={`bar ${status}`}>
          <div className={`bar-fill ${status}`} style={{ width: `${progress}%` }} />
        </div>
        <span className="bar-label">{progress}%</span>
      </div>

      <div style={{ display: 'flex', marginTop: 8 }}>
        <span className={`status-pill ${status}`}>
          {status === 'running' ? (
            <span className="spinner" />
          ) : (
            <span className={`status-dot ${status}`} />
          )}
          {STATUS_TEXT[status]}
        </span>
      </div>

      <Handle type="target" position={Position.Left} />
      <Handle type="source" position={Position.Right} />
    </div>
  )
}
