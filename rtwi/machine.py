from __future__ import annotations

import time

from rtwi import auth, rollmac, wifi
from rtwi.log import get_logger
from rtwi.models import AuthResult, AuthState, Config, WiFiState

logger = get_logger(__name__)


class RTMachine:
    """Facade tying Wi-Fi, MAC-roll and portal auth together for the CLI."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.client = auth.make_client(config)
        self._interface: str | None = None

    @property
    def interface(self) -> str:
        """Resolve (once) and return the configured Wi-Fi device name."""
        if self._interface is None:
            self._interface = wifi.resolve_interface(self.config)
        return self._interface

    def status(self) -> tuple[WiFiState, AuthState]:
        """Snapshot Wi-Fi state plus the live portal status."""
        interface = self.interface
        on = wifi.is_wifi_on(interface)
        portal = self.portal()
        wifi_state = WiFiState(
            network=wifi.current_network(interface),
            mac=wifi.current_mac(interface),
            ip=wifi.current_ip(interface) if on else "",
            ping_ms=wifi.average_ping_ms() if on else None,
        )
        return wifi_state, portal

    def portal(self) -> AuthState:
        """Query the portal authorization state."""
        return auth.portal_status(self.client)

    def auth(self) -> AuthResult:
        """Start the auth flow using the configured phone and method."""
        return auth.authenticate(self.client, self.config.phone, self.config.method)

    def sms(self, code: str) -> AuthResult:
        """Submit an SMS confirmation code."""
        return auth.confirm_sms(self.client, code)

    def poll_call(self) -> AuthResult:
        """Poll the call-confirmation endpoint once."""
        return auth.confirm_call(self.client)

    def call_loop(self) -> AuthResult:
        """Poll /call/check until confirmed or the poll budget runs out."""
        result = AuthResult(AuthState.WAIT_CALL, "call not picked up yet")
        for _ in range(self.config.max_call_polls):
            result = auth.confirm_call(self.client)
            if result.state != AuthState.WAIT_CALL:
                return result
            time.sleep(self.config.poll_interval)
        logger.info(
            "call confirmation timed out after %s polls", self.config.max_call_polls
        )
        return result

    def roll(self) -> str | None:
        """Roll the MAC; requires root privileges."""
        if not rollmac.is_root():
            logger.warning("MAC roll needs root; run with --sudo")
            return None
        return rollmac.roll_mac(self.interface)

    def connected(self) -> bool:
        """True when Wi-Fi is on and joined to the target network."""
        interface = self.interface
        on = wifi.is_wifi_on(interface)
        return not (not on or wifi.current_network(interface) != self.config.network)
