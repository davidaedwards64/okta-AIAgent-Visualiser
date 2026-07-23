import type { LayoutOptions, NodeSingular } from "cytoscape";
import type { GraphResponse, NodeType } from "../types/graph";

// Fixed left-to-right swimlanes by node type, rather than a force-directed
// layout — for a graph this small, predictability reads better than a
// physics simulation's idea of "fit". Downstream resources (AS/resource
// server/MCP server/secret/service account) all share the rightmost lane.
const COLUMN_ORDER: Record<NodeType, number> = {
  user: 0,
  group: 1,
  application: 2,
  provider: 3,
  agent: 4,
  authorizationServer: 5,
  resourceServer: 5,
  mcpServer: 5,
  secret: 5,
  serviceAccount: 5,
};

export const COLUMN_GAP = 300; // wide enough for long edge labels like "Only allow: sales:order, ..."
export const ROW_GAP = 90;

export function computeColumnPositions(graph: GraphResponse): Record<string, { x: number; y: number }> {
  const columns = new Map<number, { id: string; label: string; imported: boolean }[]>();
  for (const { data } of graph.nodes) {
    const col = COLUMN_ORDER[data.type] ?? 5;
    const bucket = columns.get(col) ?? [];
    bucket.push({ id: data.id, label: data.label, imported: Boolean(data.imported) });
    columns.set(col, bucket);
  }

  const maxRows = Math.max(...Array.from(columns.values(), (c) => c.length), 1);
  const positions: Record<string, { x: number; y: number }> = {};

  for (const [col, nodes] of columns) {
    // Imported agents sink to the bottom of the agent column (also
    // distinguished by color, but grouping them spatially too makes the
    // manual/imported split obvious at a glance).
    const sorted = [...nodes].sort(
      (a, b) => Number(a.imported) - Number(b.imported) || a.label.localeCompare(b.label),
    );
    const offsetY = ((maxRows - sorted.length) * ROW_GAP) / 2; // center shorter columns
    sorted.forEach((node, i) => {
      positions[node.id] = { x: col * COLUMN_GAP, y: offsetY + i * ROW_GAP };
    });
  }

  // A provider node only exists to explain where an agent was imported
  // from — anchor it to the average Y of the agent(s) it points at via
  // `importedFrom` edges instead of the alphabetical column-center position
  // above, so it reads as sitting next to its agent(s) rather than floating
  // in the middle of a mostly-empty column.
  const providerAgentIds = new Map<string, string[]>();
  for (const { data } of graph.edges) {
    if (data.type !== "importedFrom") continue;
    const agentIds = providerAgentIds.get(data.source) ?? [];
    agentIds.push(data.target);
    providerAgentIds.set(data.source, agentIds);
  }
  for (const [providerId, agentIds] of providerAgentIds) {
    if (!positions[providerId]) continue;
    const agentYs = agentIds.map((id) => positions[id]?.y).filter((y): y is number => y !== undefined);
    if (agentYs.length === 0) continue;
    const avgY = agentYs.reduce((sum, y) => sum + y, 0) / agentYs.length;
    positions[providerId] = { x: positions[providerId].x, y: avgY };
  }

  return positions;
}

export function columnLayout(positions: Record<string, { x: number; y: number }>): LayoutOptions {
  return {
    name: "preset",
    positions: (node: NodeSingular) => positions[node.id()] ?? { x: 0, y: 0 },
    fit: true,
    padding: 60,
  } as LayoutOptions;
}
