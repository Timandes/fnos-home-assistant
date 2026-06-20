"""Config flow for the fnOS integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, CONF_NAME
from homeassistant.core import callback

from .auth import (
    AuthResult,
    AuthStatus,
    classify_login_response,
    classify_twofa_response,
    is_valid_twofa_code,
)
from .const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_DISK_SCAN_INTERVAL,
    CONF_SCAN_INTERVAL,
    CONF_DISK_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

CONF_2FA_CODE = "code"

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_TWOFA_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_2FA_CODE): str,
    }
)


class FnosHub:
    """Hub for fnOS integration."""

    def __init__(self, host: str) -> None:
        """Initialize."""
        self.host = host
        self._client = None

    async def login(self, username: str, password: str) -> AuthResult:
        """Connect to fnOS and perform username/password login."""
        try:
            # pylint: disable=import-outside-toplevel
            from fnos import FnosClient

            self._client = FnosClient()
            await self._client.connect(self.host)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _LOGGER.warning("Cannot connect to fnOS host %s: %s", self.host, exc)
            return AuthResult(AuthStatus.CANNOT_CONNECT)

        try:
            response = await self._client.login(username, password)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _LOGGER.warning("fnOS login failed for host %s: %s", self.host, exc)
            return AuthResult(AuthStatus.UNKNOWN)

        return classify_login_response(response)

    async def submit_twofa_code(self, code: str) -> AuthResult:
        """Submit a 2FA code and request trusted-device status."""
        if not self._client:
            return AuthResult(AuthStatus.CANNOT_CONNECT)

        try:
            response = await self._client.submit_twofa_code(
                code,
                trust_device=True,
            )
        except ValueError:
            return AuthResult(AuthStatus.INVALID_TWOFA_CODE)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _LOGGER.warning(
                "fnOS two-factor verification failed for host %s: %s",
                self.host,
                exc,
            )
            return AuthResult(AuthStatus.UNKNOWN)

        return classify_twofa_response(response)

    async def close(self) -> None:
        """Close the temporary fnOS client."""
        if not self._client:
            return

        close = getattr(self._client, "close", None)
        if close:
            await close()
            return

        disconnect = getattr(self._client, "disconnect", None)
        if disconnect:
            await disconnect()


class FnosConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for fnOS."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self._pending_hub: FnosHub | None = None
        self._pending_user_input: dict[str, Any] | None = None

    def _create_entry_from_user_input(
        self,
        user_input: dict[str, Any],
    ) -> ConfigFlowResult:
        """Create a config entry from validated user input."""
        host = user_input[CONF_HOST]
        friendly_name = user_input.get(CONF_NAME)
        return self.async_create_entry(
            title=friendly_name or host,
            data=user_input,
        )

    async def _clear_pending_hub(self) -> None:
        """Close and clear any pending authentication client."""
        if self._pending_hub:
            await self._pending_hub.close()
        self._pending_hub = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self._clear_pending_hub()
            self._pending_user_input = None

            hub = FnosHub(user_input[CONF_HOST])
            result = await hub.login(
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )

            if result.status == AuthStatus.SUCCESS:
                await hub.close()
                return self._create_entry_from_user_input(user_input)

            if result.status == AuthStatus.TWOFA_REQUIRED:
                self._pending_hub = hub
                self._pending_user_input = dict(user_input)
                return await self.async_step_twofa()

            await hub.close()
            if result.status in {
                AuthStatus.CANNOT_CONNECT,
                AuthStatus.INVALID_AUTH,
                AuthStatus.TWOFA_SETUP_REQUIRED,
            }:
                errors["base"] = result.status.value
            else:
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_twofa(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the two-factor authentication step."""
        errors: dict[str, str] = {}

        if self._pending_hub is None or self._pending_user_input is None:
            return await self.async_step_user()

        if user_input is not None:
            code = user_input[CONF_2FA_CODE]
            if not is_valid_twofa_code(code):
                errors["base"] = "invalid_twofa_code"
            else:
                result = await self._pending_hub.submit_twofa_code(code)
                if result.status == AuthStatus.SUCCESS:
                    entry_input = self._pending_user_input
                    await self._clear_pending_hub()
                    self._pending_user_input = None
                    return self._create_entry_from_user_input(entry_input)

                if result.status == AuthStatus.INVALID_TWOFA_CODE:
                    errors["base"] = "invalid_twofa_code"
                elif result.status == AuthStatus.CANNOT_CONNECT:
                    errors["base"] = "cannot_connect"
                else:
                    errors["base"] = "unknown"

        return self.async_show_form(
            step_id="twofa",
            data_schema=STEP_TWOFA_DATA_SCHEMA,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> FnosOptionsFlow:  # pylint: disable=unused-argument
        """Get the options flow for this handler."""
        return FnosOptionsFlow()


class FnosOptionsFlow(OptionsFlow):
    """Handle fnOS options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current_system = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        current_disk = self.config_entry.options.get(
            CONF_DISK_SCAN_INTERVAL, DEFAULT_DISK_SCAN_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL,
                        default=current_system,
                    ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
                    vol.Required(
                        CONF_DISK_SCAN_INTERVAL,
                        default=current_disk,
                    ): vol.All(vol.Coerce(int), vol.Range(min=300, max=86400)),
                }
            ),
        )
