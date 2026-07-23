"""The backend/frontend seam. Mirrored (by hand, keep in sync) at
frontend/src/types/graph.ts.
"""

from typing import Any, Literal

from pydantic import BaseModel

NodeType = Literal[
    "agent",
    "user",
    "group",
    "application",
    "authorizationServer",
    "resourceServer",
    "mcpServer",
    "secret",
    "serviceAccount",
    "provider",
]

EdgeType = Literal[
    "owner",
    "linkedApp",
    "connection",
    "delegation",
    "importedFrom",
    "groupAssignment",
    "accessPolicy",
    "groupMember",
]


class NodeData(BaseModel):
    id: str  # "{type}:{oktaId}" — stable, unique across the whole graph
    type: NodeType
    label: str
    status: str | None = None
    sub_label: str | None = None
    description: str | None = None
    okta_id: str
    admin_url: str | None = None  # null when the deep-link pattern isn't confirmed yet for this type
    imported: bool = False  # agent-only: true when it has a provider_id (imported, not created in Okta)
    raw: dict[str, Any] = {}


class GraphNode(BaseModel):
    data: NodeData


class EdgeData(BaseModel):
    id: str
    source: str
    target: str
    type: EdgeType
    label: str | None = None
    connection_type: str | None = None
    status: str | None = None
    scope_condition: str | None = None
    scopes: list[str] = []
    rule_summaries: list[str] = []  # accessPolicy-only: one line per matching Access Policy Rule
    raw: dict[str, Any] = {}


class GraphEdge(BaseModel):
    data: EdgeData


class GraphResponse(BaseModel):
    generated_at: str
    org_domain: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    warnings: list[str] = []
