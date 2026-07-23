import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.errors import OktaApiError

MAX_PAGES = 50  # safety valve; a normal org's AI-agent roster should be far smaller

# The graph build fans out dozens of concurrent requests per load (see
# CONCURRENCY in graph/router.py); a couple of reloads in quick succession is
# enough to trip Okta's short per-org rate-limit window, especially on a
# preview tenant. Rather than surface that as a hard failure, retry a bounded
# number of times using the delay Okta itself tells us to wait.
MAX_RETRY_ATTEMPTS = 3
MAX_RETRY_DELAY_SECONDS = 30.0


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
            resp = await self._get_with_retry(client, f"{self._base_url}{path}", params)
        if resp.status_code >= 400:
            self._raise_for_error(resp)
        return resp

    async def _get_with_retry(
        self, client: httpx.AsyncClient, url: str, params: dict[str, Any] | None
    ) -> httpx.Response:
        attempt = 0
        while True:
            resp = await client.get(url, params=params, headers={"Authorization": f"Bearer {self._access_token}"})
            if resp.status_code != 429 or attempt >= MAX_RETRY_ATTEMPTS:
                return resp
            attempt += 1
            await asyncio.sleep(self._retry_delay_seconds(resp))

    @staticmethod
    def _retry_delay_seconds(resp: httpx.Response) -> float:
        # Okta sends both headers on a 429; prefer Retry-After (already a
        # relative second count) and fall back to computing one from
        # X-Rate-Limit-Reset (an absolute Unix timestamp for when the org's
        # rate-limit window rolls over).
        retry_after = resp.headers.get("retry-after")
        if retry_after is not None:
            try:
                return min(float(retry_after), MAX_RETRY_DELAY_SECONDS)
            except ValueError:
                pass
        reset_at = resp.headers.get("x-rate-limit-reset")
        if reset_at is not None:
            try:
                return max(0.0, min(float(reset_at) - time.time(), MAX_RETRY_DELAY_SECONDS))
            except ValueError:
                pass
        return 1.0  # neither header present — short fallback rather than retrying instantly

    async def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self.get(path, params)
        return resp.json()

    async def paginate(
        self, path: str, params: dict[str, Any] | None = None
    ) -> AsyncIterator[dict]:
        """Follows the `Link: <url>; rel="next"` response header (Okta's actual
        pagination mechanism), not a nextPageToken body field.

        Response bodies come in two shapes depending on the API family: the
        classic core APIs (/api/v1/...) return a bare JSON array, while the
        newer Workload Principals API (/workload-principals/api/v1/...) wraps
        results in `{"data": [...]}`. Handle both."""
        next_url: str | None = f"{self._base_url}{path}"
        next_params = dict(params or {})
        pages = 0

        while next_url and pages < MAX_PAGES:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await self._get_with_retry(client, next_url, next_params if pages == 0 else None)
            if resp.status_code >= 400:
                self._raise_for_error(resp)

            body = resp.json()
            items = body if isinstance(body, list) else body.get("data", [])

            for item in items:
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
