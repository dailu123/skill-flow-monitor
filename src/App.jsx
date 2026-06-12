import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  MarkerType,
  useReactFlow,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import StatusNode from './StatusNode.jsx'
import FlowingEdge from './FlowingEdge.jsx'
import { layoutGraph, assignOrder } from './layout.js'

const nodeTypes = { status: StatusNode }
const edgeTypes = { flowing: FlowingEdge }

const EDGE_COLOR = { idle: '#dadce0', flowing: '#1a73e8', done: '#1e8e3e' }

// 每秒轮询一次 JSON 状态文件
function usePoll(url, ms = 1000) {
  const [data, setData] = useState(null)
  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const res = await fetch(`${url}?t=${Date.now()}`)
        if (res.ok) {
          const json = await res.json()
          if (alive) setData(json)
        }
      } catch {
        /* 文件暂不存在时静默重试 */
      }
    }
    tick()
    const id = setInterval(tick, ms)
    return () => {
      alive = false
      clearInterval(id)
    }
  }, [url, ms])
  return data
}

function edgeState(sourceStatus, targetStatus) {
  if (targetStatus === 'running') return 'flowing'
  if (sourceStatus === 'done' && targetStatus === 'done') return 'done'
  return 'idle'
}

function makeEdges(rawEdges, statusById) {
  return (rawEdges || []).map((e) => {
    const state = edgeState(statusById[e.from], statusById[e.to])
    return {
      id: `${e.from}->${e.to}`,
      source: e.from,
      target: e.to,
      type: 'flowing',
      data: { state },
      markerEnd: { type: MarkerType.ArrowClosed, width: 18, height: 18, color: EDGE_COLOR[state] },
    }
  })
}

function buildPipeline(pipeline) {
  if (!pipeline?.skills?.length) return { nodes: [], edges: [] }
  const statusById = Object.fromEntries(pipeline.skills.map((s) => [s.id, s.status]))
  const edges = makeEdges(pipeline.edges, statusById)
  const nodes = pipeline.skills.map((s) => ({
    id: s.id,
    type: 'status',
    data: { kind: 'skill', ...s },
    position: { x: 0, y: 0 },
  }))
  return { nodes: layoutGraph(nodes, edges), edges }
}

function buildLineage(lineage) {
  if (!lineage?.nodes?.length) return { nodes: [], edges: [] }
  const statusById = Object.fromEntries(lineage.nodes.map((n) => [n.id, n.status]))
  const edges = makeEdges(lineage.edges, statusById)
  const orderById = assignOrder(lineage.nodes, edges, lineage.target)
  const nodes = lineage.nodes.map((n) => ({
    id: n.id,
    type: 'status',
    data: { kind: 'node', ...n, order: orderById[n.id], isTarget: n.id === lineage.target },
    position: { x: 0, y: 0 },
  }))
  return { nodes: layoutGraph(nodes, edges), edges }
}

function countStatus(items = []) {
  const c = { done: 0, running: 0, error: 0, pending: 0 }
  items.forEach((it) => {
    c[it.status === 'skipped' ? 'pending' : it.status in c ? it.status : 'pending']++
  })
  return c
}

// 节点数量变化时自动重新适配视野（AI 边分析边加节点的场景）
function AutoFit({ count }) {
  const { fitView } = useReactFlow()
  useEffect(() => {
    const id = setTimeout(() => fitView({ padding: 0.15, duration: 500 }), 50)
    return () => clearTimeout(id)
  }, [count, fitView])
  return null
}

function FlowCanvas({ nodes, edges, emptyHint }) {
  if (!nodes.length) {
    return <div className="empty-hint">{emptyHint}</div>
  }
  return (
    <ReactFlowProvider>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        proOptions={{ hideAttribution: true }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
      >
        <AutoFit count={nodes.length} />
        <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#dadce0" />
        <Controls showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          maskColor="rgba(241, 243, 244, 0.7)"
          nodeColor={(n) =>
            ({ running: '#1a73e8', done: '#1e8e3e', error: '#d93025' }[n.data?.status] || '#bdc1c6')
          }
        />
      </ReactFlow>
    </ReactFlowProvider>
  )
}

export default function App() {
  const [tab, setTab] = useState('pipeline')
  const pipeline = usePoll('/status/pipeline.json')
  const lineage = usePoll('/status/lineage.json')

  const pipelineGraph = useMemo(() => buildPipeline(pipeline), [pipeline])
  const lineageGraph = useMemo(() => buildLineage(lineage), [lineage])

  const items = tab === 'pipeline' ? pipeline?.skills : lineage?.nodes
  const counts = countStatus(items)
  const total = items?.length || 0
  const overall = total
    ? Math.round(
        items.reduce((sum, it) => sum + (it.status === 'done' ? 100 : it.progress || 0), 0) / total,
      )
    : 0
  const updatedAt = (tab === 'pipeline' ? pipeline : lineage)?.updatedAt

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">M</span>
          <div>
            <h1>{pipeline?.title || 'AS/400 Migration Monitor'}</h1>
            <div className="subtitle">
              {updatedAt ? `Last updated ${updatedAt}` : 'Waiting for status files…'}
            </div>
          </div>
        </div>

        <nav className="tabs">
          <button className={tab === 'pipeline' ? 'active' : ''} onClick={() => setTab('pipeline')}>
            Skill Pipeline
          </button>
          <button className={tab === 'lineage' ? 'active' : ''} onClick={() => setTab('lineage')}>
            ETL Lineage
          </button>
        </nav>

        <div className="stats">
          <div className="legend">
            <span className="legend-item"><span className="legend-dot done" />{counts.done} Done</span>
            <span className="legend-item"><span className="legend-dot running" />{counts.running} Running</span>
            <span className="legend-item"><span className="legend-dot pending" />{counts.pending} Pending</span>
            {counts.error > 0 && (
              <span className="legend-item"><span className="legend-dot error" />{counts.error} Failed</span>
            )}
          </div>
          <div className="overall">
            <span className="overall-label">Overall</span>
            <div className="overall-bar">
              <div className="overall-fill" style={{ width: `${overall}%` }} />
            </div>
            <span>{overall}%</span>
          </div>
        </div>
      </header>

      <main className="canvas">
        {tab === 'pipeline' ? (
          <FlowCanvas
            nodes={pipelineGraph.nodes}
            edges={pipelineGraph.edges}
            emptyHint="No pipeline data yet — waiting for status/pipeline.json…"
          />
        ) : (
          <FlowCanvas
            nodes={lineageGraph.nodes}
            edges={lineageGraph.edges}
            emptyHint="No lineage data yet — waiting for status/lineage.json…"
          />
        )}
      </main>
    </div>
  )
}
