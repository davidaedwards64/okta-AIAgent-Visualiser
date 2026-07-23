import type { Core, NodeSingular } from "cytoscape";
import { hideMembersForGroup, showMembersForGroup } from "./groupMembers";

const OPEN_IN_OKTA_ID = "open-in-okta";
const TOGGLE_MEMBERS_ID = "toggle-members";

/**
 * Wires the right-click menu. `cytoscape-context-menus` only supports a
 * static `disabled` flag per item at registration time, so per-node
 * enable/disable for "Open in Okta" is done dynamically on `cxttapstart`
 * (fired right before the menu opens) via the plugin's imperative
 * enableMenuItem/disableMenuItem API, keyed on whether this node's
 * `admin_url` is set (it's null for the still-unconfirmed beta object types
 * — see backend/app/graph/deeplinks.py). "Show/hide members" doesn't need
 * that treatment — its `selector` already restricts it to group nodes, so
 * it just never appears in the menu for anything else.
 */
export function attachContextMenu(cy: Core): void {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const menuApi = (cy as any).contextMenus({
    menuItems: [
      {
        id: OPEN_IN_OKTA_ID,
        content: "Open in Okta",
        selector: "node",
        onClickFunction: (event: { target: { data: (key: string) => unknown } }) => {
          const url = event.target.data("admin_url");
          if (typeof url === "string" && url) {
            window.open(url, "_blank", "noopener,noreferrer");
          }
        },
        hasTrailingDivider: false,
      },
      {
        id: TOGGLE_MEMBERS_ID,
        content: "Show/hide members",
        selector: 'node[type = "group"]',
        onClickFunction: (event: { target: NodeSingular }) => {
          const node = event.target;
          if (node.data("membersShown")) {
            hideMembersForGroup(cy, node);
          } else {
            void showMembersForGroup(cy, node);
          }
        },
        hasTrailingDivider: false,
      },
    ],
  });

  cy.on("cxttapstart", "node", (evt) => {
    const url = evt.target.data("admin_url");
    if (typeof url === "string" && url) {
      menuApi.enableMenuItem(OPEN_IN_OKTA_ID);
    } else {
      menuApi.disableMenuItem(OPEN_IN_OKTA_ID);
    }
  });
}
