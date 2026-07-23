import type { NodeSingular } from "cytoscape";

// Style-only palette; not the final brand palette. If revisiting for polish,
// prefer the project's dataviz skill for an accessible, consistent scheme
// rather than more ad hoc colors. Exported for reuse by the Legend component.
// Imported agents (provider_id set — see backend/app/graph/assemble.py) get
// the same round-rectangle shape as manually-created ones, just a distinct
// dark slate instead of blue, kept different from the provider triangle's
// #5B6472 so the two greys aren't confusable.
export const IMPORTED_AGENT_COLOR = "#3B4252";

export const NODE_COLORS: Record<string, string> = {
  agent: "#4C6FFF",
  user: "#2E9E5B",
  group: "#1F7A46",
  application: "#E08E24",
  authorizationServer: "#B23FD1",
  resourceServer: "#8A4FD1",
  mcpServer: "#D14F7A",
  secret: "#C4392B",
  serviceAccount: "#9C4A2B",
  provider: "#5B6472",
};

export const NODE_SHAPES: Record<string, string> = {
  agent: "round-rectangle",
  user: "ellipse",
  group: "ellipse",
  application: "round-rectangle",
  authorizationServer: "hexagon",
  resourceServer: "hexagon",
  mcpServer: "hexagon",
  secret: "diamond",
  serviceAccount: "diamond",
  provider: "triangle",
};

export const NODE_TYPE_LABELS: Record<string, string> = {
  agent: "AI Agent",
  user: "User",
  group: "Group",
  application: "Application",
  authorizationServer: "Authorization Server",
  resourceServer: "Resource Server",
  mcpServer: "MCP Server",
  secret: "Secret",
  serviceAccount: "Service Account",
  provider: "Provider (import source)",
};

// Declaration order here is the legend's display order.
export const LEGEND_NODE_TYPES = Object.keys(NODE_TYPE_LABELS);

const DEFAULT_EDGE_COLOR = "#aab";
const DEFAULT_EDGE_WIDTH = 2;

// Single source of truth for edge-type-specific styling — both the
// cytoscape stylesheet below and the Legend component read from this, so
// they can't drift apart. `connection` and `linkedApp` deliberately have no
// entry here: they use the plain default edge style (solid, DEFAULT_EDGE_COLOR).
export const EDGE_STYLES: Record<string, { color: string; lineStyle: "solid" | "dashed" | "dotted"; width?: number }> = {
  owner: { color: "#2E9E5B", lineStyle: "dashed" },
  delegation: { color: "#4C6FFF", lineStyle: "solid", width: 3 },
  importedFrom: { color: "#5B6472", lineStyle: "dotted" },
  groupAssignment: { color: "#1F7A46", lineStyle: "dashed" },
  accessPolicy: { color: "#B23FD1", lineStyle: "dashed" },
  groupMember: { color: "#2E9E5B", lineStyle: "dotted" },
};

export function edgeLegendStyle(edgeType: string): { color: string; lineStyle: "solid" | "dashed" | "dotted"; width: number } {
  const s = EDGE_STYLES[edgeType];
  return { color: s?.color ?? DEFAULT_EDGE_COLOR, lineStyle: s?.lineStyle ?? "solid", width: s?.width ?? DEFAULT_EDGE_WIDTH };
}

export const EDGE_TYPE_LABELS: Record<string, string> = {
  connection: "Resource connection",
  linkedApp: "Linked app (user sign-on)",
  delegation: "Delegates to (agent-to-agent)",
  owner: "Owner",
  groupAssignment: "Group assigned to app",
  accessPolicy: "Granted via access policy",
  groupMember: "Group member",
  importedFrom: "Imported from provider",
};

// Declaration order here is the legend's display order.
export const LEGEND_EDGE_TYPES = Object.keys(EDGE_TYPE_LABELS);

const edgeTypeStyleRules = Object.entries(EDGE_STYLES).map(([type, s]) => ({
  selector: `edge[type = '${type}']`,
  style: {
    "line-style": s.lineStyle,
    "line-color": s.color,
    "target-arrow-color": s.color,
    ...(s.width ? { width: s.width } : {}),
  },
}));

// Not annotated as cytoscape.Stylesheet[] — that named type isn't resolvable
// through this package's ambient namespace export in this TS/module setup.
// Structural typing against cytoscape()'s `style` option (Stylesheet[]) is
// checked at the call site in CytoscapeCanvas.tsx instead.
export const cytoscapeStyle = [
  {
    selector: "node",
    style: {
      "background-color": (ele: NodeSingular) =>
        ele.data("type") === "agent" && ele.data("imported")
          ? IMPORTED_AGENT_COLOR
          : NODE_COLORS[ele.data("type")] ?? "#888",
      shape: (ele: NodeSingular) => (NODE_SHAPES[ele.data("type")] ?? "ellipse") as never,
      label: "data(label)",
      color: "#1a1a1a",
      "font-size": 11,
      "text-valign": "bottom",
      "text-margin-y": 6,
      "text-background-color": "#fff",
      "text-background-opacity": 0.85,
      "text-background-padding": 2,
      width: 36,
      height: 36,
      "border-width": 2,
      "border-color": "#fff",
    },
  },
  {
    selector: "node[status = 'INACTIVE']",
    style: { "background-opacity": 0.4, "border-style": "dashed" },
  },
  {
    selector: "node:selected",
    style: { "border-color": "#111", "border-width": 3 },
  },
  {
    selector: "edge",
    style: {
      width: DEFAULT_EDGE_WIDTH,
      "line-color": DEFAULT_EDGE_COLOR,
      "target-arrow-color": DEFAULT_EDGE_COLOR,
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      "font-size": 9,
      color: "#556",
      label: "data(label)",
      "text-rotation": "autorotate",
    },
  },
  ...edgeTypeStyleRules,
  // Click-to-highlight-neighborhood (fed by CytoscapeCanvas's tap handlers).
  // Placed last so highlighted color always wins over the type-specific edge
  // rules above without erasing their line-style (dashed/dotted stays as-is
  // — only color/width change).
  {
    selector: "node.faded, edge.faded",
    style: { opacity: 0.15 },
  },
  {
    selector: "node.highlighted",
    style: { "border-color": "#000", "border-width": 4 },
  },
  {
    selector: "edge.highlighted",
    style: { "line-color": "#000", "target-arrow-color": "#000", width: 4 },
  },
];
