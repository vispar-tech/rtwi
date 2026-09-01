from __future__ import annotations

import httpx

from rtwi import auth
from rtwi.models import AuthState, Config


class FakeResponse:
    def __init__(
        self,
        url: str,
        status_code: int = 200,
        payload: object | None = None,
        text: str = "",
    ) -> None:
        self.url = url
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self) -> object:
        if callable(self._payload):
            return self._payload()
        return self._payload


class FakeClient:
    """Minimal httpx-client stub routing by (method, url-prefix)."""

    def __init__(
        self,
        routes: dict[tuple[str, str], FakeResponse | Exception],
    ) -> None:
        self.routes = routes
        self.requests: list[tuple[str, str, dict[str, object]]] = []

    def _match(self, method: str, url: str) -> FakeResponse | Exception:
        for key, value in self.routes.items():
            if key[0] == method and key[1] in url:
                return value
        raise AssertionError(f"no route for {method} {url}")

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append(("GET", url, kwargs))
        result = self._match("GET", url)
        if isinstance(result, Exception):
            raise result
        return result

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.requests.append(("POST", url, kwargs))
        result = self._match("POST", url)
        if isinstance(result, Exception):
            raise result
        return result


def _client(routes: dict[tuple[str, str], FakeResponse | Exception]) -> FakeClient:
    return FakeClient(routes)


def _config(**overrides: object) -> Config:
    return Config(**overrides)


def test_make_client() -> None:
    config = _config(user_agent="rtwi-test/1.0", request_timeout=7)
    client = auth.make_client(config)
    assert client.base_url == "https://auth.wifi.rt.ru"
    assert client.headers["User-Agent"] == "rtwi-test/1.0"
    assert client.timeout == httpx.Timeout(7)
    assert client.follow_redirects is True


def test_portal_status_success() -> None:
    client = _client({("GET", "/"): FakeResponse("https://spb.rt.ru/x")})
    assert auth.portal_status(client) == AuthState.SUCCESS


def test_portal_status_forbidden() -> None:
    client = _client({("GET", "/"): FakeResponse("https://a.wifi.rt.ru/forbidden")})
    assert auth.portal_status(client) == AuthState.FORBIDDEN


def test_portal_status_wait_sms() -> None:
    client = _client({("GET", "/"): FakeResponse("https://a.wifi.rt.ru/sms/confirm")})
    assert auth.portal_status(client) == AuthState.WAIT_SMS


def test_portal_status_wait_call() -> None:
    client = _client({("GET", "/"): FakeResponse("https://a.wifi.rt.ru/call/wait")})
    assert auth.portal_status(client) == AuthState.WAIT_CALL


def test_portal_status_need_auth() -> None:
    client = _client({("GET", "/"): FakeResponse("https://a.wifi.rt.ru/auth/index")})
    assert auth.portal_status(client) == AuthState.NEED_AUTH


def test_portal_status_default_success() -> None:
    client = _client({("GET", "/"): FakeResponse("https://a.wifi.rt.ru/other")})
    assert auth.portal_status(client) == AuthState.SUCCESS


def test_portal_status_network_error() -> None:
    client = _client({("GET", "/"): httpx.ConnectError("boom")})
    assert auth.portal_status(client) == AuthState.FAILED


def test_authenticate_missing_phone() -> None:
    client = _client({})
    result = auth.authenticate(client, None, "call")
    assert result.state == AuthState.FAILED
    assert "no phone" in result.message


def test_authenticate_bad_phone() -> None:
    client = _client({})
    result = auth.authenticate(client, "+7-911", "call")
    assert result.state == AuthState.FAILED


def test_authenticate_already_authorized() -> None:
    client = _client({("GET", "/"): FakeResponse("https://spb.rt.ru/")})
    result = auth.authenticate(client, "+79110000000", "call")
    assert result.state == AuthState.SUCCESS


def test_authenticate_forbidden() -> None:
    client = _client({("GET", "/"): FakeResponse("https://a.wifi.rt.ru/forbidden")})
    result = auth.authenticate(client, "+79110000000", "call")
    assert result.state == AuthState.FORBIDDEN


def test_authenticate_enter_redirect_to_wait_call() -> None:
    client = _client(
        {
            ("GET", "/"): FakeResponse("https://a.wifi.rt.ru/auth/index"),
            ("POST", "/auth/index"): FakeResponse("https://a.wifi.rt.ru/call/wait"),
        }
    )
    result = auth.authenticate(client, "+79110000000", "call")
    assert result.state == AuthState.WAIT_CALL
    assert client.requests[1][2]["data"] == {"enter": "1"}


def test_authenticate_id_index_call() -> None:
    client = _client(
        {
            ("GET", "/"): FakeResponse("https://a.wifi.rt.ru/id/index"),
            ("POST", "/id/index"): FakeResponse("https://a.wifi.rt.ru/some"),
            ("POST", "/call/index"): FakeResponse("https://a.wifi.rt.ru/call/wait"),
        }
    )
    result = auth.authenticate(client, "+79110000000", "call")
    assert result.state == AuthState.WAIT_CALL
    agree = next(
        r for r in client.requests if r[0] == "POST" and r[1].endswith("/id/index")
    )
    assert agree[2]["data"] == {
        "IdentificationsForm[agree]": "1",
        "IdentificationsForm[type]": "call",
    }
    post = next(r for r in client.requests if r[0] == "POST" and r[1] == "/call/index")
    assert post[2]["data"] == {"PhoneForm[phone]": "+79110000000", "type": "1"}


def test_authenticate_id_index_sms() -> None:
    client = _client(
        {
            ("GET", "/"): FakeResponse("https://a.wifi.rt.ru/id/index"),
            ("POST", "/id/index"): FakeResponse("https://a.wifi.rt.ru/some"),
            ("POST", "/sms/index"): FakeResponse("https://a.wifi.rt.ru/sms/confirm"),
        }
    )
    result = auth.authenticate(client, "+79110000000", "sms")
    assert result.state == AuthState.WAIT_SMS
    assert ("POST", "/sms/index") in [(r[0], r[1]) for r in client.requests]


def test_authenticate_network_error() -> None:
    client = _client({("GET", "/"): httpx.ConnectError("down")})
    result = auth.authenticate(client, "+79110000000", "call")
    assert result.state == AuthState.FAILED


def test_confirm_sms_success() -> None:
    client = _client(
        {
            ("POST", "/sms/confirm"): FakeResponse("https://a.wifi.rt.ru/some"),
            ("GET", "/"): FakeResponse("https://spb.rt.ru/"),
        }
    )
    result = auth.confirm_sms(client, "1234")
    assert result.state == AuthState.SUCCESS
    post = next(r for r in client.requests if r[0] == "POST" and r[1] == "/sms/confirm")
    assert post[2]["data"] == {"VerifySmsForm[smsCode]": "1234"}


def test_confirm_sms_rejected() -> None:
    client = _client(
        {
            ("POST", "/sms/confirm"): FakeResponse("https://a.wifi.rt.ru/some"),
            ("GET", "/"): FakeResponse("https://a.wifi.rt.ru/sms/confirm"),
        }
    )
    result = auth.confirm_sms(client, "0000")
    assert result.state == AuthState.WAIT_SMS
    assert "rejected" in result.message


def test_confirm_sms_network_error() -> None:
    client = _client({("POST", "/sms/confirm"): httpx.ConnectError("down")})
    result = auth.confirm_sms(client, "1234")
    assert result.state == AuthState.FAILED


def test_confirm_call_success() -> None:
    client = _client(
        {
            ("GET", "/call/check?"): FakeResponse(
                "https://a.wifi.rt.ru/call/wait",
                payload={"status": "success", "route": "/some/route"},
            ),
            ("GET", "/some/route"): FakeResponse("https://a.wifi.rt.ru/x"),
        }
    )
    result = auth.confirm_call(client)
    assert result.state == AuthState.SUCCESS
    check = client.requests[0]
    assert check[0] == "GET"
    assert check[1].startswith("/call/check?_=")
    assert check[2]["headers"] == {"X-Requested-With": "XMLHttpRequest"}
    assert ("GET", "/some/route") in [(r[0], r[1]) for r in client.requests]


def test_confirm_call_waiting() -> None:
    client = _client(
        {
            ("GET", "/call/check?"): FakeResponse(
                "https://a.wifi.rt.ru/call/wait", payload={"status": "pending"}
            )
        }
    )
    result = auth.confirm_call(client)
    assert result.state == AuthState.WAIT_CALL


def test_confirm_call_non_200() -> None:
    client = _client(
        {
            ("GET", "/call/check?"): FakeResponse(
                "https://a.wifi.rt.ru/call/wait", status_code=503
            )
        }
    )
    assert auth.confirm_call(client).state == AuthState.WAIT_CALL


def test_confirm_call_network_error() -> None:
    client = _client({("GET", "/call/check?"): httpx.ConnectError("down")})
    assert auth.confirm_call(client).state == AuthState.FAILED


def test_confirm_call_bad_json() -> None:
    client = _client(
        {
            ("GET", "/call/check?"): FakeResponse(
                "https://a.wifi.rt.ru/call/wait",
                payload={"status": "success", "route": "/x"},
            )
        }
    )
    route = client.routes[("GET", "/call/check?")]
    original_json = route.json
    route.json = lambda: (_ for _ in ()).throw(  # type: ignore[assignment]
        ValueError("not json")
    )
    assert auth.confirm_call(client).state == AuthState.FAILED
    route.json = original_json  # type: ignore[assignment]


# --- schedule detection ---


def test_portal_status_disabled_by_schedule() -> None:
    body = "<html><body>Сеть отключена по расписанию предприятия</body></html>"
    client = _client(
        {("GET", "/"): FakeResponse("https://a.wifi.rt.ru/forbidden", text=body)}
    )
    assert auth.portal_status(client) == AuthState.DISABLED_BY_SCHEDULE


def test_portal_status_forbidden_not_schedule() -> None:
    body = "<html><body>Forbidden: limit reached</body></html>"
    client = _client(
        {("GET", "/"): FakeResponse("https://a.wifi.rt.ru/forbidden", text=body)}
    )
    assert auth.portal_status(client) == AuthState.FORBIDDEN


def test_portal_status_schedule_english() -> None:
    body = "<html><body>Network disabled by schedule</body></html>"
    client = _client(
        {("GET", "/"): FakeResponse("https://a.wifi.rt.ru/forbidden", text=body)}
    )
    assert auth.portal_status(client) == AuthState.DISABLED_BY_SCHEDULE


def test_authenticate_disabled_by_schedule() -> None:
    body = "Отключена по расписанию предприятия"
    client = _client(
        {("GET", "/"): FakeResponse("https://a.wifi.rt.ru/forbidden", text=body)}
    )
    result = auth.authenticate(client, "+79110000000", "call")
    assert result.state == AuthState.DISABLED_BY_SCHEDULE
    assert "schedule" in result.message
