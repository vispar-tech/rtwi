from __future__ import annotations

import re
import time
from typing import cast

import httpx

from rtwi.log import get_logger
from rtwi.models import PHONE_RE, AuthResult, AuthState, Config

logger = get_logger(__name__)

_BASE_URL = "https://auth.wifi.rt.ru"
_OK_HOSTS = ("https://spb.rt.ru/",)


class PortalError(RuntimeError):
    """Raised when the portal answers with an unexpected result."""


def make_client(config: Config) -> httpx.Client:
    """Build an HTTPX client pre-configured for the portal."""
    return httpx.Client(
        base_url=_BASE_URL,
        headers={"User-Agent": config.user_agent},
        timeout=config.request_timeout,
        follow_redirects=True,
    )


_SCHEDULE_KEYWORDS = (
    "отключена по расписанию",
    "отключена по расписанию предприятия",
    "disabled by schedule",
    "network disabled",
    "по расписанию предприятия",
)


def _is_schedule_page(body: str) -> bool:
    """Return True when the forbidden page indicates a scheduled shutdown."""
    lower = body.lower()
    return any(kw in lower for kw in _SCHEDULE_KEYWORDS)


def _state_from_url(url: str) -> AuthState:
    """Map a portal URL to a coarse AuthState."""
    if url.startswith(_OK_HOSTS):
        return AuthState.SUCCESS
    if "forbidden" in url:
        return AuthState.FORBIDDEN
    if "sms/confirm" in url:
        return AuthState.WAIT_SMS
    if "call/wait" in url:
        return AuthState.WAIT_CALL
    if "auth/index" in url or "id/index" in url:
        return AuthState.NEED_AUTH
    return AuthState.SUCCESS


def portal_status(client: httpx.Client) -> AuthState:
    """Ask the portal whether this device is authorized."""
    try:
        resp = client.get("/")
        url = str(resp.url)
        if "forbidden" in url and _is_schedule_page(resp.text):
            return AuthState.DISABLED_BY_SCHEDULE
        return _state_from_url(url)
    except httpx.HTTPError as exc:
        logger.warning("portal status check failed: %s", exc)
        return AuthState.FAILED


def _validate_phone(phone: str | None) -> str | None:
    if not phone:
        return "no phone configured"
    if re.match(PHONE_RE, phone) is None:
        return "invalid phone, expected +7XXXXXXXXXX"
    return None


def _pending_state(url: str) -> AuthResult:
    """Map a mid-flow portal URL to WAIT_* or the fallback success."""
    if "sms/confirm" in url:
        return AuthResult(AuthState.WAIT_SMS, "awaiting sms code")
    if "call/wait" in url:
        return AuthResult(AuthState.WAIT_CALL, "awaiting call confirmation")
    logger.warning("unexpected portal URL %r, assuming one-time auth", url)
    return AuthResult(AuthState.SUCCESS, "already authorized")


def _submit_phone(
    client: httpx.Client, url: str, phone: str, method: str
) -> AuthResult:
    """Post the agreement + phone number, returning the waiting state."""
    client.post(
        url,
        data={
            "IdentificationsForm[agree]": "1",
            "IdentificationsForm[type]": method,
        },
    )
    endpoint = "/call/index" if method == "call" else "/sms/index"
    client.post(
        endpoint,
        data={"PhoneForm[phone]": phone, "type": "1"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if method == "call":
        return AuthResult(AuthState.WAIT_CALL, "awaiting call confirmation")
    return AuthResult(AuthState.WAIT_SMS, "awaiting sms code")


def authenticate(client: httpx.Client, phone: str | None, method: str) -> AuthResult:
    """Start the auth flow; returns WAIT_SMS/WAIT_CALL or a failure."""
    if (problem := _validate_phone(phone)) is not None:
        return AuthResult(AuthState.FAILED, problem)
    phone_str = cast(str, phone)

    try:
        resp = client.get("/")
        url = str(resp.url)

        if url.startswith(_OK_HOSTS):
            return AuthResult(AuthState.SUCCESS, "already authorized")
        if "forbidden" in url:
            if _is_schedule_page(resp.text):
                msg = "network disabled by schedule"
                return AuthResult(AuthState.DISABLED_BY_SCHEDULE, msg)
            return AuthResult(AuthState.FORBIDDEN, "auth limit reached")
        if "auth/index" in url:
            url = str(client.post(url, data={"enter": "1"}).url)
        if "id/index" in url:
            return _submit_phone(client, url, phone_str, method)
        return _pending_state(url)
    except httpx.HTTPError as exc:
        logger.error("auth failed: %s", exc)
        return AuthResult(AuthState.FAILED, f"portal error: {exc}")


def confirm_sms(client: httpx.Client, code: str) -> AuthResult:
    """Submit the SMS code and report the resulting portal state."""
    try:
        client.post(
            "/sms/confirm",
            data={"VerifySmsForm[smsCode]": code},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        logger.error("sms confirm failed: %s", exc)
        return AuthResult(AuthState.FAILED, f"portal error: {exc}")
    state = portal_status(client)
    if state == AuthState.SUCCESS:
        return AuthResult(AuthState.SUCCESS, "authorized over sms")
    return AuthResult(state, "sms code rejected")


def confirm_call(client: httpx.Client) -> AuthResult:
    """Poll /call/check once; returns SUCCESS when the call is picked up."""
    try:
        check_url = f"/call/check?_={int(time.time() * 1000)}"
        resp = client.get(check_url, headers={"X-Requested-With": "XMLHttpRequest"})
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                if route := data.get("route"):
                    client.get(f"{route}")
                return AuthResult(AuthState.SUCCESS, "authorized over call")
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("call confirm failed: %s", exc)
        return AuthResult(AuthState.FAILED, f"portal error: {exc}")
    return AuthResult(AuthState.WAIT_CALL, "call not picked up yet")
