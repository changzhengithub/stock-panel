import httpx
import pytest
from app.providers.tushare import PermissionDenied, ProviderError, Tushare


def test_missing_token():
    with pytest.raises(PermissionDenied):
        Tushare(credential="")


def test_permission_redacts_token():
    def respond(request):
        return httpx.Response(200, json={"code": -2001, "msg": "token secret 无权限"})

    provider = Tushare("secret", httpx.Client(transport=httpx.MockTransport(respond)), interval=0)
    with pytest.raises(PermissionDenied) as error:
        provider.query("daily")
    assert "secret" not in str(error.value)


def test_pagination_and_truncation():
    provider = Tushare("secret", interval=0)
    provider.query = lambda *args, **kwargs: [
        {"id": n} for n in range(kwargs["offset"], min(kwargs["offset"] + 2, 5))
    ]
    assert len(provider.all("daily", page_size=2)) == 5
    provider.query = lambda *args, **kwargs: [{"id": 1}, {"id": 2}]
    with pytest.raises(ProviderError, match="分页重复"):
        provider.all("daily", page_size=2)


def test_transient_network_retry(monkeypatch):
    monkeypatch.setattr("app.providers.tushare.time.sleep", lambda _: None)
    calls = []

    def respond(request):
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectError("test")
        return httpx.Response(200, json={"code": 0, "data": {"fields": ["id"], "items": [[1]]}})

    provider = Tushare("secret", httpx.Client(transport=httpx.MockTransport(respond)), interval=0)
    assert provider.query("daily") == [{"id": 1}] and len(calls) == 3


def test_rate_limit_retry(monkeypatch):
    monkeypatch.setattr("app.providers.tushare.time.sleep", lambda _: None)
    calls = []

    def respond(request):
        calls.append(1)
        return httpx.Response(
            200,
            json={"code": -1, "msg": "每分钟最多访问"}
            if len(calls) == 1
            else {"code": 0, "data": {"fields": [], "items": []}},
        )

    provider = Tushare("secret", httpx.Client(transport=httpx.MockTransport(respond)), interval=0)
    assert provider.query("daily") == [] and len(calls) == 2
