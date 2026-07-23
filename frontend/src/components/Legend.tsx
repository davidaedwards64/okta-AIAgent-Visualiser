import type { CSSProperties } from "react";
import {
  EDGE_TYPE_LABELS,
  IMPORTED_AGENT_COLOR,
  LEGEND_EDGE_TYPES,
  LEGEND_NODE_TYPES,
  NODE_COLORS,
  NODE_SHAPES,
  NODE_TYPE_LABELS,
  edgeLegendStyle,
} from "../graph/cytoscapeStyle";

// "AI Agent (imported)" isn't a real NodeType (see backend/app/graph/contract.py
// — imported is a boolean flag on agent nodes, not a separate type), so it
// can't come from LEGEND_NODE_TYPES like everything else; splice it in right
// after the regular "agent" row instead of giving it a fake type of its own.
const NODE_LEGEND_ROWS = LEGEND_NODE_TYPES.flatMap((type) => {
  const row = { key: type, color: NODE_COLORS[type], shape: NODE_SHAPES[type], label: NODE_TYPE_LABELS[type] };
  if (type !== "agent") return [row];
  return [
    row,
    { key: "agent-imported", color: IMPORTED_AGENT_COLOR, shape: NODE_SHAPES.agent, label: "AI Agent (imported)" },
  ];
});

// Approximates the cytoscape node shapes with CSS so the legend swatches
// visually match what's on the canvas without needing to render cytoscape
// itself just for a key.
function shapeStyle(shape: string): CSSProperties {
  switch (shape) {
    case "ellipse":
      return { borderRadius: "50%" };
    case "hexagon":
      return { clipPath: "polygon(25% 0%, 75% 0%, 100% 50%, 75% 100%, 25% 100%, 0% 50%)" };
    case "diamond":
      return { clipPath: "polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)" };
    case "triangle":
      return { clipPath: "polygon(50% 0%, 0% 100%, 100% 100%)" };
    default: // round-rectangle
      return { borderRadius: 4 };
  }
}

export default function Legend() {
  return (
    <div className="legend">
      <div className="legend-title">Nodes</div>
      {NODE_LEGEND_ROWS.map((row) => (
        <div className="legend-row" key={row.key}>
          <span className="legend-swatch" style={{ backgroundColor: row.color, ...shapeStyle(row.shape) }} />
          <span>{row.label}</span>
        </div>
      ))}

      <div className="legend-title legend-title-edges">Edges</div>
      {LEGEND_EDGE_TYPES.map((type) => {
        const { color, lineStyle, width } = edgeLegendStyle(type);
        return (
          <div className="legend-row" key={type}>
            <span
              className="legend-edge-swatch"
              style={{ borderTopColor: color, borderTopStyle: lineStyle, borderTopWidth: width }}
            />
            <span>{EDGE_TYPE_LABELS[type]}</span>
          </div>
        );
      })}
    </div>
  );
}
