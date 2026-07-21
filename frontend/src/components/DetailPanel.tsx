import type { NodeData } from "../types/graph";

interface DetailPanelProps {
  node: NodeData | null;
  onClose: () => void;
}

export default function DetailPanel({ node, onClose }: DetailPanelProps) {
  if (!node) return null;

  return (
    <aside className="detail-panel">
      <button className="close-button" onClick={onClose} aria-label="Close">
        ×
      </button>
      <h2>{node.label}</h2>
      <p className="node-type">{node.type}</p>
      {node.status && <p>Status: {node.status}</p>}
      {node.sub_label && <p>{node.sub_label}</p>}
      <p className="okta-id">{node.okta_id}</p>

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
    </aside>
  );
}
