from __future__ import annotations

from dataclasses import dataclass

from rtwi.log import get_logger
from rtwi.machine import RTMachine
from rtwi.models import AuthState

logger = get_logger(__name__)


@dataclass(frozen=True)
class FixResult:
    """Outcome of a full fix run."""

    state: AuthState
    message: str
    rolls: int = 0


def _maybe_roll(machine: RTMachine, rolls: int) -> tuple[FixResult | None, int]:
    """Roll the MAC when allowed; returns (outcome, new_rolls) or (None, rolls+1)."""
    if not machine.config.auto_roll or rolls >= machine.config.max_rolls:
        return (
            FixResult(
                AuthState.FORBIDDEN, "auth limit reached, rolls exhausted", rolls
            ),
            rolls,
        )
    if machine.roll() is None:
        return (
            FixResult(
                AuthState.FORBIDDEN, "roll requires root; run with --sudo", rolls
            ),
            rolls,
        )
    logger.info("rolled MAC, retrying authorization")
    return None, rolls + 1


def run_fix(
    machine: RTMachine,
    *,
    sms_message: str = "SMS code required: run `rtwi sms <code>`",
) -> FixResult:
    """Authorize, rolling the MAC on FORBIDDEN until authorized or rolls run out."""
    if not machine.connected():
        return FixResult(
            AuthState.OFFLINE,
            "Wi-Fi is not connected to the target network",
        )

    rolls = 0
    while True:
        result = machine.auth()
        if result.state == AuthState.SUCCESS:
            return FixResult(AuthState.SUCCESS, result.message, rolls)
        if result.state == AuthState.WAIT_SMS:
            logger.info("authentication paused on SMS code request")
            return FixResult(AuthState.WAIT_SMS, sms_message, rolls)
        if result.state == AuthState.WAIT_CALL:
            confirm = machine.call_loop()
            return FixResult(confirm.state, confirm.message, rolls)
        if result.state == AuthState.FORBIDDEN:
            outcome, rolls = _maybe_roll(machine, rolls)
            if outcome is not None:
                return outcome
            continue
        if result.state != AuthState.FAILED:
            logger.warning("unexpected auth state %s", result.state)
        return FixResult(AuthState.FAILED, result.message, rolls)
