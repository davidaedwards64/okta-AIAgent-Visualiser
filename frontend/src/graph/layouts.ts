import type { LayoutOptions } from "cytoscape";

// No natural single root for the first render, so a force-directed layout.
export const initialLayout: LayoutOptions = {
  name: "cose",
  animate: false,
  padding: 50,
} as LayoutOptions;

// breadthfirst's `roots` option natively rings nodes by graph-distance-from-
// root, which *is* "recenter on this node" — prefer it over `concentric`
// (which would need a hand-written BFS-distance function to get the same
// effect).
export function recenterLayout(rootNodeId: string): LayoutOptions {
  return {
    name: "breadthfirst",
    roots: [rootNodeId],
    directed: false,
    animate: true,
    animationDuration: 400,
    spacingFactor: 1.2,
    padding: 50,
  } as LayoutOptions;
}
