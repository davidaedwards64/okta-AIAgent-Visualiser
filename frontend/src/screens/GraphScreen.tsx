import { useEffect, useState } from "react";
import { logout } from "../api/auth";
import { getGraph } from "../api/graph";
import DetailPanel from "../components/DetailPanel";
import Header from "../components/Header";
import CytoscapeCanvas from "../graph/CytoscapeCanvas";
import type { GraphResponse, NodeData } from "../types/graph";

interface GraphScreenProps {
  orgDomain: string;
  onDisconnected: () => void;
}

export default function GraphScreen({ orgDomain, onDisconnected }: GraphScreenProps) {
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [selectedNode, setSelectedNode] = useState<NodeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function loadGraph() {
    setLoading(true);
    setError(null);
    getGraph()
      .then((g) => setGraph(g))
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load graph"))
      .finally(() => setLoading(false));
  }

  useEffect(loadGraph, []);

  async function handleDisconnect() {
    await logout();
    onDisconnected();
  }

  return (
    <div className="graph-screen">
      <Header orgDomain={orgDomain} onRefresh={loadGraph} onDisconnect={handleDisconnect} refreshing={loading} />
      <div className="graph-body">
        {error && <div className="error-banner">{error}</div>}
        {!error && loading && !graph && <div className="centered">Loading graph...</div>}
        {!error && graph && graph.nodes.length === 0 && (
          <div className="centered">No AI Agents found in this org.</div>
        )}
        {graph && graph.nodes.length > 0 && (
          <CytoscapeCanvas graph={graph} onNodeSelect={setSelectedNode} />
        )}
        <DetailPanel node={selectedNode} onClose={() => setSelectedNode(null)} />
      </div>
      {graph && graph.warnings.length > 0 && (
        <details className="warnings-banner">
          <summary>{graph.warnings.length} warning(s) while building the graph</summary>
          <ul>
            {graph.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
