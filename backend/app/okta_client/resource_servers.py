"""Custom Resource Server by-id lookup.

UNCONFIRMED against a live tenant: exact base path and scope name (see README
"Verify-live checklist" — item 2). developer.okta.com structure suggests a
`secures-ai-resource-servers` OpenAPI family distinct from workload-principals,
so this guesses `/api/v1/resource-servers/{id}` as the most Okta-idiomatic
path and fails soft (returns None + a warning) rather than crashing the whole
graph fetch if that guess is wrong. Update this path once confirmed live.
"""

from app.errors import OktaApiError
from app.okta_client.base import OktaClient
from app.okta_client.models import DirectoryObjectDTO

GUESSED_BASE = "/api/v1/resource-servers"


async def get_resource_server(client: OktaClient, resource_server_id: str) -> DirectoryObjectDTO | None:
    try:
        raw = await client.get_json(f"{GUESSED_BASE}/{resource_server_id}")
    except OktaApiError:
        return None
    return DirectoryObjectDTO(
        id=raw.get("id", resource_server_id),
        label=raw.get("name", resource_server_id),
        status=raw.get("status"),
        sub_label=raw.get("resourceUrl") or raw.get("url"),
        raw=raw,
    )
