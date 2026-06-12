import dagre from '@dagrejs/dagre'

const NODE_W = 250
const NODE_H = 104

// 用 dagre 自动布局（从左到右：源头在左、目标在右）
export function layoutGraph(nodes, edges) {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'LR', ranksep: 110, nodesep: 46 })
  g.setDefaultEdgeLabel(() => ({}))
  nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }))
  edges.forEach((e) => g.setEdge(e.source, e.target))
  dagre.layout(g)
  return nodes.map((n) => {
    const p = g.node(n.id)
    return { ...n, position: { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 } }
  })
}

// 计算血缘节点编号：离目标表最远的节点编号为 1，依次递增，目标表编号最大。
// 这与 AI「从最源头开始转换」的处理顺序一致。
export function assignOrder(nodes, edges, targetId) {
  const rev = {}
  edges.forEach((e) => {
    ;(rev[e.target] ||= []).push(e.source)
  })
  const dist = { [targetId]: 0 }
  const queue = [targetId]
  while (queue.length) {
    const cur = queue.shift()
    for (const parent of rev[cur] || []) {
      const d = dist[cur] + 1
      if (dist[parent] === undefined || d > dist[parent]) {
        dist[parent] = d
        queue.push(parent)
      }
    }
  }
  const ordered = [...nodes].sort((a, b) => (dist[b.id] ?? 0) - (dist[a.id] ?? 0))
  const orderById = {}
  ordered.forEach((n, i) => {
    orderById[n.id] = i + 1
  })
  return orderById
}
