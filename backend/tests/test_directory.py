import pytest

from app.errors import OktaApiError
from app.okta_client.base import OktaClient
from app.okta_client.directory import find_everyone_group


def make_client(get_json_result=None, get_json_error=None) -> OktaClient:
    client = OktaClient("example.okta.com", "token")

    async def fake_get_json(path, params=None):
        if get_json_error is not None:
            raise get_json_error
        return get_json_result

    client.get_json = fake_get_json  # type: ignore[method-assign]
    return client


async def test_find_everyone_group_parses_first_built_in_result():
    raw = {"id": "00g1", "profile": {"name": "Everyone", "description": "All org users"}}
    client = make_client(get_json_result=[raw])

    result = await find_everyone_group(client)

    assert result is not None
    assert result.id == "00g1"
    assert result.label == "Everyone"
    assert result.sub_label == "All org users"
    assert result.raw == raw


async def test_find_everyone_group_falls_back_to_everyone_label_when_name_missing():
    raw = {"id": "00g1", "profile": {}}
    client = make_client(get_json_result=[raw])

    result = await find_everyone_group(client)

    assert result is not None
    assert result.label == "Everyone"


async def test_find_everyone_group_returns_none_when_no_groups_found():
    client = make_client(get_json_result=[])

    assert await find_everyone_group(client) is None


async def test_find_everyone_group_returns_none_on_api_error():
    client = make_client(get_json_error=OktaApiError(500, error_code=None, error_summary="boom", error_causes=[]))

    assert await find_everyone_group(client) is None
