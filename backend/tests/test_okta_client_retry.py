import time

import httpx

from app.okta_client.base import MAX_RETRY_DELAY_SECONDS, OktaClient


def test_retry_delay_prefers_retry_after_header():
    resp = httpx.Response(429, headers={"retry-after": "5"})
    assert OktaClient._retry_delay_seconds(resp) == 5.0


def test_retry_delay_caps_retry_after_header():
    resp = httpx.Response(429, headers={"retry-after": "9999"})
    assert OktaClient._retry_delay_seconds(resp) == MAX_RETRY_DELAY_SECONDS


def test_retry_delay_falls_back_to_rate_limit_reset():
    reset_at = time.time() + 10
    resp = httpx.Response(429, headers={"x-rate-limit-reset": str(reset_at)})
    delay = OktaClient._retry_delay_seconds(resp)
    assert 8.0 < delay <= 10.0


def test_retry_delay_defaults_when_no_headers_present():
    resp = httpx.Response(429)
    assert OktaClient._retry_delay_seconds(resp) == 1.0
