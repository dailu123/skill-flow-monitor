import { BaseEdge, getBezierPath } from '@xyflow/react'

// Dataflow / Cloud Composer style edges:
//   done = solid green, flowing = blue dashed + travelling dot, idle = grey.
const COLORS = {
  idle: '#dadce0',
  flowing: '#1a73e8',
  done: '#1e8e3e',
}

export default function FlowingEdge(props) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, markerEnd } = props
  const [path] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition })
  const state = data?.state || 'idle'

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd}
        style={{
          stroke: state === 'flowing' ? 'rgba(26, 115, 232, 0.2)' : COLORS[state],
          strokeWidth: state === 'idle' ? 1.5 : 2,
        }}
      />
      {state === 'flowing' && (
        <>
          <path d={path} fill="none" className="edge-flow" />
          <circle r="3" className="edge-dot">
            <animateMotion dur="1.8s" repeatCount="indefinite" path={path} />
          </circle>
        </>
      )}
    </>
  )
}
