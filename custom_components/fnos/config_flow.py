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
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

from .const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_DISK_SCAN_INTERVAL,
    CONF_SCAN_INTERVAL,
    CONF_DISK_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class FnosHub:
    """Hub for fnOS integration."""

    def __init__(self, host: str) -> None:
        """Initialize."""
        self.host = host
        self._client = None

    async def authenticate(self, username: str, password: str) -> bool:
        """Test if we can authenticate with the host."""
        try:
            # pylint: disable=import-outside-toplevel
            from fnos import FnosClient
            self._client = FnosClient()
            await self._client.connect(self.host)
            result = await self._client.login(username, password)
            return result.get("result", "succ") == "succ"
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _LOGGER.exception("Authentication failed: %s", exc)
            return False

    async def disconnect(self) -> None:
        """Disconnect from the host."""
        if self._client:
            await self._client.disconnect()


async def validate_input(
    hass: HomeAssistant,  # pylint: disable=unused-argument
    data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    hub = FnosHub(data[CONF_HOST])

    if not await hub.authenticate(
        data[CONF_USERNAME], data[CONF_PASSWORD]
    ):
        raise InvalidAuth

    return {}


class FnosConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for fnOS."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            friendly_name = user_input.get(CONF_NAME)

            try:
                await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception as exc:  # pylint: disable=broad-exception-caught
                _LOGGER.exception("Unexpected exception: %s", exc)
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=friendly_name or host, data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors
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


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""

    def __init__(self, message: str = "Cannot connect to fnOS") -> None:
        """Initialize the error."""
        super().__init__(message)
        self.message = message


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""

    def __init__(self, message: str = "Invalid authentication") -> None:
        """Initialize the error."""
        super().__init__(message)
        self.message = message
