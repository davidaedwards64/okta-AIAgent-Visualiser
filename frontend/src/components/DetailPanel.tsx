import type { EdgeData, NodeData, Selection } from "../types/graph";

interface DetailPanelProps {
  selection: Selection | null;
  nodeLabelById: Record<string, string>;
  edges: EdgeData[];
  onClose: () => void;
}

export default function DetailPanel({ selection, nodeLabelById, edges, onClose }: DetailPanelProps) {
  if (!selection) return null;

  return (
    <aside className="detail-panel">
      <button className="close-button" onClick={onClose} aria-label="Close">
        ×
      </button>
      {selection.kind === "node" ? (
        <NodeDetails node={selection.data} edges={edges} nodeLabelById={nodeLabelById} />
      ) : (
        <EdgeDetails edge={selection.data} nodeLabelById={nodeLabelById} />
      )}
    </aside>
  );
}

function NodeDetails({
  node,
  edges,
  nodeLabelById,
}: {
  node: NodeData;
  edges: EdgeData[];
  nodeLabelById: Record<string, string>;
}) {
  const secretDescription = node.type === "secret" ? (node.raw?.secret as { description?: string } | undefined)?.description : undefined;
  // Owners aren't a field on the agent node itself — they're separate
  // user/group nodes joined by "owner" edges, so look those up here rather
  // than duplicating the data on NodeData.
  const owners = node.type === "agent" ? edges.filter((e) => e.type === "owner" && e.target === node.id) : [];

  return (
    <>
      <h2>{node.label}</h2>
      <p className="node-type">
        {node.type}
        {node.imported && " (imported)"}
      </p>
      {node.status && <p>Status: {node.status}</p>}
      {node.description && <p>{node.description}</p>}
      {node.sub_label && <p>{node.sub_label}</p>}
      {secretDescription && <p>{secretDescription}</p>}
      <p className="okta-id">{node.okta_id}</p>

      {owners.length > 0 && (
        <div className="owners-section">
          <p className="owners-heading">Owners</p>
          <ul className="owners-list">
            {owners.map((e) => (
              <li key={e.id}>
                {nodeLabelById[e.source] ?? e.source}
                {e.source.startsWith("group:") && " (group)"}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Accessible equivalent of the right-click "Open in Okta" item —
          right-click alone isn't reachable via keyboard/touch. */}
      {node.admin_url ? (
        <a className="view-in-okta" href={node.admin_url} target="_blank" rel="noopener noreferrer">
          View in Okta ↗
        </a>
      ) : (
        <p className="view-in-okta-disabled" title="Admin Console link not yet available for this object type">
          View in Okta (not available yet)
        </p>
      )}

      <details>
        <summary>Raw data</summary>
        <pre>{JSON.stringify(node.raw, null, 2)}</pre>
      </details>
    </>
  );
}

function EdgeDetails({ edge, nodeLabelById }: { edge: EdgeData; nodeLabelById: Record<string, string> }) {
  return (
    <>
      <h2>{edge.label || edge.type}</h2>
      <p className="node-type">{edge.type}</p>
      <p>
        {nodeLabelById[edge.source] ?? edge.source} → {nodeLabelById[edge.target] ?? edge.target}
      </p>
      {edge.connection_type && <p>Connection type: {edge.connection_type}</p>}
      {edge.status && <p>Status: {edge.status}</p>}
      {edge.scope_condition && <p>Scope condition: {edge.scope_condition}</p>}
      {edge.scopes.length > 0 && <p>Scopes: {edge.scopes.join(", ")}</p>}
      {edge.rule_summaries.length > 0 && (
        <ul className="rule-summaries">
          {edge.rule_summaries.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ul>
      )}

      <details>
        <summary>Raw data</summary>
        <pre>{JSON.stringify(edge.raw, null, 2)}</pre>
      </details>
    </>
  );
}
