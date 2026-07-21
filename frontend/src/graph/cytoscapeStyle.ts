import type { NodeSingular } from "cytoscape";

// Style-only palette; not the final brand palette. If revisiting for polish,
// prefer the project's dataviz skill for an accessible, consistent scheme
// rather than more ad hoc colors.
const NODE_COLORS: Record<string, string> = {
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

const NODE_SHAPES: Record<string, string> = {
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

// Not annotated as cytoscape.Stylesheet[] — that named type isn't resolvable
// through this package's ambient namespace export in this TS/module setup.
// Structural typing against cytoscape()'s `style` option (Stylesheet[]) is
// checked at the call site in CytoscapeCanvas.tsx instead.
export const cytoscapeStyle = [
  {
    selector: "node",
    style: {
      "background-color": (ele: NodeSingular) => NODE_COLORS[ele.data("type")] ?? "#888",
      shape: (ele: NodeSingular) => (NODE_SHAPES[ele.data("type")] ?? "ellipse") as never,
      label: "data(label)",
      color: "#1a1a1a",
      "font-size": 11,
      "text-valign": "bottom",
      "text-margin-y": 6,
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
      width: 2,
      "line-color": "#aab",
      "target-arrow-color": "#aab",
      "target-arrow-shape": "triangle",
      "curve-style": "bezier",
      "font-size": 9,
      color: "#556",
      label: "data(label)",
      "text-rotation": "autorotate",
    },
  },
  {
    selector: "edge[type = 'owner']",
    style: { "line-style": "dashed", "line-color": "#2E9E5B", "target-arrow-color": "#2E9E5B" },
  },
  {
    selector: "edge[type = 'delegation']",
    style: { width: 3, "line-color": "#4C6FFF", "target-arrow-color": "#4C6FFF" },
  },
  {
    selector: "edge[type = 'importedFrom']",
    style: { "line-style": "dotted", "line-color": "#5B6472", "target-arrow-color": "#5B6472" },
  },
];
