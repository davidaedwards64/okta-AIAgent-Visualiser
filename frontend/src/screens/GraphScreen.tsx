import { useEffect, useMemo, useRef, useState } from "react";
import { logout } from "../api/auth";
import { streamGraph } from "../api/graph";
import DetailPanel from "../components/DetailPanel";
import Header from "../components/Header";
import Legend from "../components/Legend";
import SearchBox from "../components/SearchBox";
import CytoscapeCanvas, { type CytoscapeCanvasHandle } from "../graph/CytoscapeCanvas";
import type { GraphResponse, Selection } from "../types/graph";
import type { RiskReportResponse } from "../types/risk";

interface GraphScreenProps {
  orgDomain: string;
  onDisconnected: () => void;
}

const INITIAL_LOADING_MESSAGE = "Loading graph...";

export default function GraphScreen({ orgDomain, onDisconnected }: GraphScreenProps) {
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMessage, setLoadingMessage] = useState(INITIAL_LOADING_MESSAGE);
  const [error, setError] = useState<string | null>(null);
  const [showGroupMembers, setShowGroupMembers] = useState(false);
  const [togglingGroupMembers, setTogglingGroupMembers] = useState(false);
  const canvasRef = useRef<CytoscapeCanvasHandle>(null);
  const focusedFromUrlRef = useRef(false);
  // Keeps the most recently generated risk report for this graph tab, so a
  // Risk Report tab that closes itself (see RiskReportScreen::focusAgentInGraph)
  // can reopen instantly from cache instead of re-running the slow analysis
  // every time. Lives only as long as this tab does — a reload/disconnect
  // naturally invalidates it.
  const riskReportCacheRef = useRef<RiskReportResponse | null>(null);

  function loadGraph() {
    setLoading(true);
    setLoadingMessage(INITIAL_LOADING_MESSAGE);
    setError(null);
    streamGraph(setLoadingMessage)
      .then((g) => {
        setGraph(g);
        // A freshly (re)built cytoscape instance won't have any on-demand
        // member nodes/edges added, and the previous selection may no
        // longer exist — both need resetting alongside a new graph.
        setSelection(null);
        setShowGroupMembers(false);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load graph"))
      .finally(() => setLoading(false));
  }

  useEffect(loadGraph, []);

  // Deep link from the Risk Report tab (?focus=<agentId>) — used only as a
  // fallback for when that tab's window.opener is gone (see
  // RiskReportScreen::focusAgentInGraph). Highlights the offending agent
  // once the graph is ready; only ever done once per page load, so a later
  // Refresh doesn't keep re-focusing the same node. Node ids in the graph
  // are prefixed by type (see assemble.py::_node_id) — agents are always
  // "agent:<oktaId>".
  useEffect(() => {
    if (!graph || focusedFromUrlRef.current) return;
    const focusId = new URLSearchParams(window.location.search).get("focus");
    if (focusId) {
      canvasRef.current?.focusOnNode(`agent:${focusId}`);
      focusedFromUrlRef.current = true;
    }
  }, [graph]);

  // Same-tab counterpart of the above: the Risk Report tab is normally still
  // open (it was opened from here via window.open), so "View in graph" there
  // posts back to us instead of navigating/opening another tab. Also serves
  // as the read/write side of the risk-report cache handoff described above.
  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      if (event.origin !== window.location.origin) return;
      const data = event.data;
      if (data?.type === "risk-report:focus-agent" && typeof data.agentId === "string") {
        canvasRef.current?.focusOnNode(`agent:${data.agentId}`);
      } else if (data?.type === "risk-report:request-cache") {
        (event.source as Window | null)?.postMessage(
          { type: "risk-report:cache", report: riskReportCacheRef.current },
          window.location.origin,
        );
      } else if (data?.type === "risk-report:store-cache") {
        riskReportCacheRef.current = data.report ?? null;
      }
    }
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, []);

  const nodeLabelById = useMemo(() => {
    const map: Record<string, string> = {};
    for (const n of graph?.nodes ?? []) map[n.data.id] = n.data.label;
    return map;
  }, [graph]);

  const edges = useMemo(() => graph?.edges.map((e) => e.data) ?? [], [graph]);

  async function handleDisconnect() {
    await logout();
    onDisconnected();
  }

  async function handleToggleGroupMembers(checked: boolean) {
    setTogglingGroupMembers(true);
    try {
      await canvasRef.current?.setShowGroupMembers(checked);
      setShowGroupMembers(checked);
    } finally {
      setTogglingGroupMembers(false);
    }
  }

  function handleSearchSelect(nodeId: string) {
    canvasRef.current?.focusOnNode(nodeId);
  }

  function handleExportPng() {
    canvasRef.current?.exportPng();
  }

  function handleOpenRiskReport() {
    window.open("/?view=risk-report", "_blank");
  }

  return (
    <div className="graph-screen">
      <Header
        orgDomain={orgDomain}
        onRefresh={loadGraph}
        onDisconnect={handleDisconnect}
        onExportPng={handleExportPng}
        onOpenRiskReport={handleOpenRiskReport}
        refreshing={loading}
        showGroupMembers={showGroupMembers}
        onToggleGroupMembers={handleToggleGroupMembers}
        togglingGroupMembers={togglingGroupMembers}
      />
      <div className="graph-body">
        {error && <div className="error-banner">{error}</div>}
        {!error && loading && !graph && <div className="centered">{loadingMessage}</div>}
        {/* Refresh reuses the existing graph until the new one is ready, so
            the initial-load banner above never shows — without this, a
            refresh gives no feedback at all until it silently swaps in. */}
        {!error && loading && graph && <div className="refresh-banner">{loadingMessage}</div>}
        {!error && graph && graph.nodes.length === 0 && (
          <div className="centered">No AI Agents found in this org.</div>
        )}
        {graph && graph.nodes.length > 0 && (
          <>
            <CytoscapeCanvas ref={canvasRef} graph={graph} onSelect={setSelection} />
            <SearchBox graph={graph} onSelectResult={handleSearchSelect} />
            <Legend />
          </>
        )}
        <DetailPanel selection={selection} nodeLabelById={nodeLabelById} edges={edges} onClose={() => setSelection(null)} />
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
