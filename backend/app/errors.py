class OktaApiError(Exception):
    """Raised when the Okta API returns a non-2xx response, mapped from
    Okta's error envelope: {errorCode, errorSummary, errorLink, errorId, errorCauses}."""

    def __init__(
        self,
        status_code: int,
        error_code: str | None = None,
        error_summary: str | None = None,
        error_causes: list[str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.error_summary = error_summary
        self.error_causes = error_causes or []
        super().__init__(f"Okta API error {status_code} ({error_code}): {error_summary}")


class NotAuthenticatedError(Exception):
    """Raised when a request needs an Okta session that doesn't exist or has expired
    with no refresh token available."""
