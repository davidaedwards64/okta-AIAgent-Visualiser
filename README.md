# Okta AIAgent Visualiser

An interactive entity-relationship diagram of the "AI Agents" (Okta for AI Agents / O4AA) object
graph in an Okta org: AI Agents, their owners, linked applications, resource connections
(Authorization Servers, MCP Servers, Applications, Secrets, Service Accounts), and agent-to-agent
delegations.

- Pan/zoom the graph.
- Click a node to re-center the diagram on it.
- Right-click a node (or use the "View in Okta" button in the detail panel) to open that object's
  page in the real Admin Console, in a new tab.
- Connect to any Okta org you're a super admin on — no fixed org or API token baked into the app.

## Architecture

- **Backend**: Python + FastAPI. Handles login (Authorization Code + PKCE against the org you
  connect to) and aggregates several Okta Management API calls into one graph payload.
- **Frontend**: React + Vite (TypeScript) + Cytoscape.js.
- The backend never gives the browser a raw Okta token: it holds the access/refresh token
  server-side in a session, keyed by an httpOnly cookie. The React app only ever talks to this
  backend's own `/api/*` and `/auth/*` routes.
- Vite's dev server proxies `/api`, `/auth`, and `/callback` to the backend, so the browser only
  ever sees one origin (`http://localhost:5173`) — this is what avoids CORS/Trusted-Origin
  headaches, not a permissive CORS config.

## Prerequisites

- Python 3.11+
- Node 18+
- An Okta org with the **Okta for AI Agents** entitlement enabled (this is currently a Beta/EA
  feature — not present in every org) and at least one AI Agent configured, to have something to
  look at.
- An OIDC app **pre-registered in that org** for this tool (Okta doesn't support fully dynamic
  arbitrary-org OAuth — the org's admin has to register a client first). See below.

## Register the OIDC app in your org

In the Admin Console of the org you want to visualize:

1. **Applications > Create App Integration**.
2. Sign-in method: **OIDC - OpenID Connect**. Application type: **Web Application** (simplest —
   lets you optionally use a client secret) or **Single-Page Application** (PKCE-only, no secret;
   also supported).
3. Grant type: **Authorization Code** (+ **Refresh Token**, so the app can silently refresh
   instead of forcing you to log in again every hour).
4. Sign-in redirect URI: `http://localhost:5173/callback`.
5. Assign the app to your own (super admin) user.
6. On the app's **Okta API Scopes** tab, grant: `okta.users.read`, `okta.groups.read`,
   `okta.apps.read`, `okta.authorizationServers.read`, `okta.aiAgents.read`.
7. Copy the **Client ID** (and **Client Secret**, if you chose Web Application).

## Running locally

Two terminals:

```bash
# Terminal 1 — backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`, enter your org domain and the Client ID (and secret, if any) from
above, and connect.

## Running the backend tests

```bash
cd backend
source .venv/bin/activate
python -m pytest
```

The graph-assembly logic (`app/graph/assemble.py`) is a pure function tested against fixture data
in `tests/test_assemble.py` — no live org needed for that suite.

## What v1 deliberately does not do

- **No OPA integration.** Secrets and Service Accounts render as nodes using only the fields
  already present on the AI Agent's resource connection (name/indicator, status) — there's no
  separate login to Okta Privileged Access to browse the actual vaulted-secret inventory. This
  can be added later as its own phase.
- **No org-wide user/group browsing.** The backend only ever resolves the specific
  users/groups/apps/servers that an agent's owners/connections/delegations actually reference —
  never the org-wide `/api/v1/users` or `/api/v1/groups` list endpoints. This keeps the graph fast
  regardless of total org size, but means this is not a general-purpose directory browser.
- **No hosting-specific code.** This runs on localhost only for now. The backend is a plain
  FastAPI app and the frontend is a static Vite build, so it should containerize/deploy to any
  generic host later without a rewrite — but no deployment config exists yet.

## Verify-live checklist

A few things could not be confirmed without a live tenant during development and are handled
defensively (the app degrades gracefully — omits the edge/link, logs a warning — rather than
guessing and asserting something false). Once you have this running against your test org, it's
worth confirming/fixing these:

1. **Owner field shape** on the AI Agent object (`app/okta_client/ai_agents.py::_extract_owners`).
   If your org's agents have owners but they don't show up as edges in the graph, check the
   `warnings` list returned by `/api/graph` and adjust the parsing there.
2. **Resource Server / MCP Server API paths and scopes**
   (`app/okta_client/resource_servers.py`, `app/okta_client/mcp_servers.py`). These currently guess
   `/api/v1/resource-servers/{id}` and `/api/v1/mcp-servers/{id}` and fail soft if wrong — check
   the `warnings` list, and update the base path/required scope once you've confirmed the real one
   (e.g. via your org's actual OpenAPI reference or by watching network requests in the Admin
   Console).
3. **Admin Console URL patterns** for AI Agents, Resource Servers, and MCP Servers
   (`app/graph/deeplinks.py::build_admin_url`). These three intentionally return `None` today (the
   "Open in Okta" item shows disabled for these node types) because there's no confirmed URL
   pattern for this new beta UI. Navigate to one of each in your Admin Console, copy the URL
   pattern from the address bar, and fill these in.
4. **Application deep link's app-type key** — the link builder assumes `GET /api/v1/apps/{id}`'s
   `name` field supplies the catalog key the Admin Console URL needs (e.g. `oidc_client`). Confirm
   this holds for both OIN app instances and any custom app types in your org.
5. **Custom-domain orgs** — the admin-console-host derivation
   (`app/graph/deeplinks.py::_admin_host`) assumes the org domain you enter is its native
   `*.okta.com`/`*.oktapreview.com` domain. If your org uses a vanity custom domain, that
   derivation needs a different approach.

## Repo

Private repo. Code here talks to live Okta admin APIs for whichever org you connect it to — don't
commit org domains, client secrets, or tokens; the `.gitignore` excludes `.env` files, but always
double-check `git status`/`git diff` before committing regardless.
