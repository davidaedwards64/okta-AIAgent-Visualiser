from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.errors import OktaApiError

MAX_PAGES = 50  # safety valve; a normal org's AI-agent roster should be far smaller


class OktaClient:
    """Thin async HTTP client for one connected org session.

    Every wrapper module (ai_agents.py, directory.py, ...) is built on top of
    this rather than calling httpx directly, so pagination/error-mapping stays
    in one place.
    """

    def __init__(self, org_domain: str, access_token: str) -> None:
        self._base_url = f"https://{org_domain}"
        self._access_token = access_token

    async def get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{self._base_url}{path}",
                params=params,
                headers={"Authorization": f"Bearer {self._access_token}"},
            )
        if resp.status_code >= 400:
            self._raise_for_error(resp)
        return resp

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self.get(path, params)
        return resp.json()

    async def paginate(
        self, path: str, params: dict[str, Any] | None = None
    ) -> AsyncIterator[dict]:
        """Follows the `Link: <url>; rel="next"` response header (Okta's actual
        pagination mechanism), not a nextPageToken body field."""
        next_url: str | None = f"{self._base_url}{path}"
        next_params = dict(params or {})
        pages = 0

        while next_url and pages < MAX_PAGES:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    next_url,
                    params=next_params if pages == 0 else None,
                    headers={"Authorization": f"Bearer {self._access_token}"},
                )
            if resp.status_code >= 400:
                self._raise_for_error(resp)

            for item in resp.json():
                yield item

            next_url = self._extract_next_link(resp)
            next_params = {}
            pages += 1

    @staticmethod
    def _extract_next_link(resp: httpx.Response) -> str | None:
        for link in resp.headers.get("link", "").split(","):
            parts = link.split(";")
            if len(parts) >= 2 and 'rel="next"' in parts[1]:
                return parts[0].strip().strip("<>")
        return None

    @staticmethod
    def _raise_for_error(resp: httpx.Response) -> None:
        try:
            body = resp.json()
        except ValueError:
            body = {}
        raise OktaApiError(
            resp.status_code,
            error_code=body.get("errorCode"),
            error_summary=body.get("errorSummary", resp.text[:200]),
            error_causes=[c.get("errorSummary", "") for c in body.get("errorCauses", [])],
        )
