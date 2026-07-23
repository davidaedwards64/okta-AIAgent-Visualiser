import type { Core, ElementDefinition, NodeSingular } from "cytoscape";
import { getGroupMembers } from "../api/graph";
import type { EdgeData, NodeData } from "../types/graph";
import { COLUMN_GAP, ROW_GAP } from "./layouts";

// Shared by the header's global toggle (CytoscapeCanvasHandle.setShowGroupMembers)
// and the per-group right-click item (contextMenu.ts) — both just need a `cy`
// and a group node, so this lives outside CytoscapeCanvas to avoid a
// CytoscapeCanvas <-> contextMenu import cycle.

export async function showMembersForGroup(cy: Core, groupNode: NodeSingular): Promise<void> {
  if (groupNode.data("membersShown")) return;
  const groupOktaId = groupNode.data("okta_id") as string;

  let response;
  try {
    response = await getGroupMembers(groupOktaId);
  } catch {
    return; // best-effort — e.g. a synthetic/unreadable group; leave the graph as-is
  }

  // cy.add() defaults un-positioned nodes to the same spot, so every newly
  // revealed member would stack exactly on top of each other — stack them
  // vertically to the left of their group instead (toward the users column).
  const groupPos = groupNode.position();
  const newMemberIds = response.members
    .map((m) => `user:${m.id}`)
    .filter((id) => cy.getElementById(id).empty());
  const startY = groupPos.y - ((newMemberIds.length - 1) * ROW_GAP) / 2;

  const elements: ElementDefinition[] = [];
  let newIndex = 0;
  for (const member of response.members) {
    const userNodeId = `user:${member.id}`;
    if (cy.getElementById(userNodeId).empty()) {
      const data: NodeData = {
        id: userNodeId,
        type: "user",
        label: member.label,
        status: member.status ?? null,
        sub_label: member.sub_label ?? null,
        okta_id: member.id,
        raw: {},
      };
      elements.push({
        group: "nodes",
        data: data as never,
        position: { x: groupPos.x - COLUMN_GAP, y: startY + newIndex * ROW_GAP },
      });
      newIndex += 1;
    }
    const edgeData: EdgeData = {
      id: `groupMember:${groupOktaId}:${member.id}`,
      source: userNodeId,
      target: groupNode.id(),
      type: "groupMember",
      label: "Member",
      scopes: [],
      rule_summaries: [],
      raw: {},
    };
    elements.push({ group: "edges", data: edgeData as never });
  }

  cy.add(elements).forEach((ele) => {
    ele.data("addedByGroupMembers", true);
  });
  groupNode.data("membersShown", true);
}

export function hideMembersForGroup(cy: Core, groupNode: NodeSingular): void {
  if (!groupNode.data("membersShown")) return;
  const edgesToRemove = groupNode.connectedEdges('[type = "groupMember"][?addedByGroupMembers]');
  const candidateNodes = edgesToRemove.sources();
  cy.remove(edgesToRemove);
  candidateNodes.forEach((n) => {
    if (n.data("addedByGroupMembers") && n.degree() === 0) cy.remove(n);
  });
  groupNode.data("membersShown", false);
}

export async function setShowMembersForAllGroups(cy: Core, show: boolean): Promise<void> {
  const groups = cy.nodes('[type = "group"]');
  if (show) {
    await Promise.all(groups.map((g) => showMembersForGroup(cy, g)));
  } else {
    groups.forEach((g) => hideMembersForGroup(cy, g));
  }
}
