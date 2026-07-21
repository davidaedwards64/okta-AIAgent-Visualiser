import type { Core } from "cytoscape";

const OPEN_IN_OKTA_ID = "open-in-okta";

/**
 * Wires the right-click "Open in Okta" item. `cytoscape-context-menus` only
 * supports a static `disabled` flag per item at registration time, so
 * per-node enable/disable is done dynamically on `cxttapstart` (fired right
 * before the menu opens) via the plugin's imperative
 * enableMenuItem/disableMenuItem API, keyed on whether this node's
 * `admin_url` is set (it's null for the still-unconfirmed beta object types
 * — see backend/app/graph/deeplinks.py).
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
