import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
// @ts-expect-error no bundled types for this plugin
import contextMenus from "cytoscape-context-menus";
import "cytoscape-context-menus/cytoscape-context-menus.css";
import { useEffect, useRef } from "react";
import type { GraphResponse, NodeData } from "../types/graph";
import { attachContextMenu } from "./contextMenu";
import { initialLayout, recenterLayout } from "./layouts";
import { cytoscapeStyle } from "./cytoscapeStyle";

cytoscape.use(contextMenus);

interface CytoscapeCanvasProps {
  graph: GraphResponse;
  onNodeSelect: (node: NodeData | null) => void;
}

function toElements(graph: GraphResponse): ElementDefinition[] {
  const nodes: ElementDefinition[] = graph.nodes.map((n) => ({ data: n.data as never, group: "nodes" }));
  const edges: ElementDefinition[] = graph.edges.map((e) => ({ data: e.data as never, group: "edges" }));
  return [...nodes, ...edges];
}

export default function CytoscapeCanvas({ graph, onNodeSelect }: CytoscapeCanvasProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  // (Re)build the graph whenever a fresh GraphResponse arrives (e.g. after Refresh).
  useEffect(() => {
    if (!containerRef.current) return;

    const cy = cytoscape({
      container: containerRef.current,
      elements: toElements(graph),
      // cytoscape's own Stylesheet type checking is overly strict about
      // literal-vs-widened string properties (and the named `Stylesheet`
      // type isn't cleanly importable in this module setup either — see
      // cytoscapeStyle.ts) — this cast is a scoped, known escape hatch for
      // that specific library friction, not a general "give up on types" move.
      style: cytoscapeStyle as cytoscape.CytoscapeOptions["style"],
      layout: initialLayout,
    });
    cyRef.current = cy;

    attachContextMenu(cy);

    cy.on("tap", "node", (evt) => {
      const node = evt.target;
      onNodeSelect(node.data() as NodeData);
      cy.layout(recenterLayout(node.id())).run();
    });

    cy.on("tap", (evt) => {
      if (evt.target === cy) onNodeSelect(null);
    });

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph]);

  return <div ref={containerRef} className="cytoscape-canvas" />;
}
