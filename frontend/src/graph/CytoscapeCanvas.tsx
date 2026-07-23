import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
// @ts-expect-error no bundled types for this plugin
import contextMenus from "cytoscape-context-menus";
import "cytoscape-context-menus/cytoscape-context-menus.css";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import type { EdgeData, GraphResponse, NodeData, Selection } from "../types/graph";
import { attachContextMenu } from "./contextMenu";
import { setShowMembersForAllGroups } from "./groupMembers";
import { columnLayout, computeColumnPositions } from "./layouts";
import { cytoscapeStyle } from "./cytoscapeStyle";

cytoscape.use(contextMenus);

export interface CytoscapeCanvasHandle {
  /** Same effect as clicking the node directly — select, highlight its neighborhood, center/zoom. */
  focusOnNode(nodeId: string): void;
  setShowGroupMembers(show: boolean): Promise<void>;
  /** Downloads the current graph (whole extent, not just the visible viewport) as a PNG. */
  exportPng(): void;
}

interface CytoscapeCanvasProps {
  graph: GraphResponse;
  onSelect: (selection: Selection | null) => void;
}

function toElements(graph: GraphResponse): ElementDefinition[] {
  const nodes: ElementDefinition[] = graph.nodes.map((n) => ({ data: n.data as never, group: "nodes" }));
  const edges: ElementDefinition[] = graph.edges.map((e) => ({ data: e.data as never, group: "edges" }));
  return [...nodes, ...edges];
}

interface ArrivedVia {
  type: string;
  asTarget: boolean; // was this node reached as the edge's target (true) or source (false)?
}

// Multi-hop, but not a plain undirected BFS: several relationship types here
// are many-to-one (several groups can share one app via `groupAssignment`,
// several agents can share one resource via `connection`, etc.). A plain BFS
// would treat that shared app/resource as a bridge back out to every other
// group/agent that also touches it — those peers have no *direct* connection
// to the origin, so they shouldn't light up.
//
// Rule: once a node is reached via edge type T in a given role (source or
// target), don't re-expand *other* edges of that same type in that same role
// from it — that's exactly the "other groups also assigned to this app"
// edge. Edges of a different type/role continue the chain normally (e.g. the
// app's `linkedApp` edge to its agent, then that agent's `connection` edges
// to downstream resources). The origin itself has no arrival edge, so
// everything directly touching it is always shown.
function connectedSubgraph(cy: Core, origins: cytoscape.NodeCollection): cytoscape.Collection {
  const arrivedViaByNodeId = new Map<string, ArrivedVia | null>();
  const queue: string[] = [];
  let result = cy.collection();

  origins.forEach((n) => {
    arrivedViaByNodeId.set(n.id(), null);
    queue.push(n.id());
    result = result.union(n);
  });

  while (queue.length > 0) {
    const nodeId = queue.shift() as string;
    const node = cy.getElementById(nodeId);
    const arrivedVia = arrivedViaByNodeId.get(nodeId) ?? null;

    node.connectedEdges().forEach((edge) => {
      const edgeType = edge.data("type") as string;
      const isTarget = edge.target().id() === nodeId;
      if (arrivedVia && edgeType === arrivedVia.type && isTarget === arrivedVia.asTarget) {
        return; // sibling edge of the same relationship — don't fan out through it
      }

      result = result.union(edge);
      const other = isTarget ? edge.source() : edge.target();
      if (!arrivedViaByNodeId.has(other.id())) {
        arrivedViaByNodeId.set(other.id(), { type: edgeType, asTarget: !isTarget });
        queue.push(other.id());
        result = result.union(other);
      }
    });
  }

  return result;
}

// Shared by node/edge tap and by search-driven focus.
function applyHighlight(cy: Core, target: cytoscape.Collection) {
  cy.elements().removeClass("highlighted faded");
  const roots = target.nodes().length > 0 ? target.nodes() : target.edges().connectedNodes();
  const connected = connectedSubgraph(cy, roots).union(target);
  connected.addClass("highlighted");
  cy.elements().not(connected).addClass("faded");
}

const CytoscapeCanvas = forwardRef<CytoscapeCanvasHandle, CytoscapeCanvasProps>(function CytoscapeCanvas(
  { graph, onSelect },
  ref,
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);

  // (Re)build the graph whenever a fresh GraphResponse arrives (e.g. after Refresh).
  useEffect(() => {
    if (!containerRef.current) return;

    const positions = computeColumnPositions(graph);
    const cy = cytoscape({
      container: containerRef.current,
      elements: toElements(graph),
      // cytoscape's own Stylesheet type checking is overly strict about
      // literal-vs-widened string properties (and the named `Stylesheet`
      // type isn't cleanly importable in this module setup either — see
      // cytoscapeStyle.ts) — this cast is a scoped, known escape hatch for
      // that specific library friction, not a general "give up on types" move.
      style: cytoscapeStyle as cytoscape.CytoscapeOptions["style"],
      layout: columnLayout(positions),
    });
    cyRef.current = cy;

    attachContextMenu(cy);

    cy.on("tap", "node", (evt) => {
      const node = evt.target;
      onSelect({ kind: "node", data: node.data() as NodeData });
      applyHighlight(cy, node);
      // Pan/zoom to the clicked node without touching anyone else's
      // position — the layout is a fixed preset, not something to re-run.
      cy.stop();
      cy.animate({ center: { eles: node }, zoom: Math.max(cy.zoom(), 1.2) }, { duration: 300 });
    });

    cy.on("tap", "edge", (evt) => {
      const edge = evt.target;
      onSelect({ kind: "edge", data: edge.data() as EdgeData });
      applyHighlight(cy, edge);
    });

    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        onSelect(null);
        cy.elements().removeClass("highlighted faded");
      }
    });

    // The detail panel appearing/disappearing resizes this container (it's a
    // flex sibling), but cytoscape doesn't repaint its internal canvas layers
    // at the new size on its own — it needs an explicit resize() call.
    const resizeObserver = new ResizeObserver(() => cy.resize());
    resizeObserver.observe(containerRef.current);

    return () => {
      resizeObserver.disconnect();
      cy.destroy();
      cyRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph]);

  useImperativeHandle(
    ref,
    () => ({
      focusOnNode(nodeId: string) {
        const cy = cyRef.current;
        if (!cy) return;
        const node = cy.getElementById(nodeId);
        if (node.empty()) return;
        onSelect({ kind: "node", data: node.data() as NodeData });
        applyHighlight(cy, node);
        cy.stop();
        cy.animate({ center: { eles: node }, zoom: Math.max(cy.zoom(), 1.2) }, { duration: 300 });
      },
      async setShowGroupMembers(show: boolean) {
        const cy = cyRef.current;
        if (!cy) return;
        await setShowMembersForAllGroups(cy, show);
      },
      exportPng() {
        const cy = cyRef.current;
        if (!cy) return;
        const dataUrl = cy.png({ full: true, scale: 2, bg: "#ffffff" });
        const link = document.createElement("a");
        link.href = dataUrl;
        link.download = `okta-aiagent-graph-${new Date().toISOString().slice(0, 10)}.png`;
        link.click();
      },
    }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  return <div ref={containerRef} className="cytoscape-canvas" />;
});

export default CytoscapeCanvas;
