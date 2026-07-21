// Mirrors backend/app/graph/contract.py by hand — keep in sync.

export type NodeType =
  | "agent"
  | "user"
  | "group"
  | "application"
  | "authorizationServer"
  | "resourceServer"
  | "mcpServer"
  | "secret"
  | "serviceAccount"
  | "provider";

export type EdgeType = "owner" | "linkedApp" | "connection" | "delegation" | "importedFrom";

export interface NodeData {
  id: string;
  type: NodeType;
  label: string;
  status?: string | null;
  sub_label?: string | null;
  okta_id: string;
  admin_url?: string | null;
  raw: Record<string, unknown>;
}

export interface GraphNode {
  data: NodeData;
}

export interface EdgeData {
  id: string;
  source: string;
  target: string;
  type: EdgeType;
  label?: string | null;
  connection_type?: string | null;
  status?: string | null;
  scope_condition?: string | null;
  scopes: string[];
  raw: Record<string, unknown>;
}

export interface GraphEdge {
  data: EdgeData;
}

export interface GraphResponse {
  generated_at: string;
  org_domain: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  warnings: string[];
}
