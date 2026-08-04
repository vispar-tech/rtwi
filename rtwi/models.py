from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from rtwi import __version__

PHONE_RE = re.compile(r"^\+7\d{10}$")


class AuthState(StrEnum):
    """Portal / auth-flow state (mirrors the rollmac-app state machine)."""

    OFFLINE = "offline"
    NEED_AUTH = "need_auth"
    PROCESSING = "processing"
    WAIT_SMS = "wait_sms"
    WAIT_CALL = "wait_call"
    SUCCESS = "success"
    FORBIDDEN = "forbidden"
    FAILED = "failed"


@dataclass(frozen=True)
class AuthResult:
    """Outcome of a single auth/confirm step."""

    state: AuthState
    message: str


@dataclass(frozen=True)
class WiFiState:
    """Snapshot of the Wi-Fi adapter state."""

    network: str
    mac: str
    ip: str
    ping_ms: float | None


class Config(BaseModel):
    """rtwi configuration persisted as YAML in ~/.config/rtwi/config.yaml."""

    phone: str | None = Field(
        default=None,
        description="Phone for portal auth, e.g. +7911XXXXXXX",
    )
    interface: str = Field(
        default="auto",
        description="Wi-Fi interface name; 'auto' detects it via networksetup",
    )
    method: str = Field(default="call", description="Auth method: call | sms")
    network: str = Field(default="Rostelecom", description="Target Wi-Fi network name")
    auto_roll: bool = Field(
        default=True,
        description="Automatically roll the MAC when the portal blocks auth",
    )
    max_rolls: int = Field(default=3, ge=1, description="Max MAC rolls per fix run")
    request_timeout: int = Field(default=5, ge=1, description="Portal HTTP timeout (s)")
    poll_interval: int = Field(
        default=5, ge=1, description="call/check poll interval (s)"
    )
    max_call_polls: int = Field(
        default=10, ge=1, description="Max call/check poll attempts"
    )
    user_agent: str = Field(default=f"rtwi/{__version__}")

    @field_validator("phone")
    @classmethod
    def _check_phone(cls, value: str | None) -> str | None:
        if not value:
            return None
        if PHONE_RE.match(value) is None:
            raise ValueError(f"invalid phone {value!r}: must match +7XXXXXXXXXX")
        return value

    @field_validator("method")
    @classmethod
    def _check_method(cls, value: str) -> str:
        if value not in {"call", "sms"}:
            raise ValueError("method must be 'call' or 'sms'")
        return value
