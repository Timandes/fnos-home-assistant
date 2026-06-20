"""Config flow for the fnOS integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    SOURCE_REAUTH,
)
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_NAME,
)
from homeassistant.core import callback

from .auth import (
    AuthResult,
    AuthStatus,
    classify_login_response,
    classify_twofa_response,
    is_connection_error,
    is_valid_twofa_code,
)
from .const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_DISK_SCAN_INTERVAL,
    CONF_SCAN_INTERVAL,
    CONF_DISK_SCAN_INTERVAL,
    CONF_AUTH_TOKEN,
    CONF_LONG_TOKEN,
    CONF_DECRYPTED_SECRET,
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
            _LOGGER.warning(
                "Cannot connect to fnOS host %s: %s",
                self.host,
                exc,
            )
            return AuthResult(AuthStatus.CANNOT_CONNECT)

        try:
            response = await self._client.login(username, password)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _LOGGER.warning("fnOS login failed for host %s: %s", self.host, exc)
            if is_connection_error(exc):
                return AuthResult(AuthStatus.CANNOT_CONNECT)
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
            if is_connection_error(exc):
                return AuthResult(AuthStatus.CANNOT_CONNECT)
            return AuthResult(AuthStatus.UNKNOWN)

        return classify_twofa_response(response)

    def stored_auth_data(self) -> dict[str, str]:
        """Return auth material captured after a final successful login."""
        if not self._client:
            return {}

        data = {}
        token = getattr(self._client, "token", None)
        long_token = getattr(self._client, "long_token", None)
        get_secret = getattr(self._client, "get_decrypted_secret", None)
        secret = (
            get_secret()
            if get_secret
            else getattr(self._client, "decrypted_secret", None)
        )

        if token:
            data[CONF_AUTH_TOKEN] = token
        if long_token:
            data[CONF_LONG_TOKEN] = long_token
        if secret:
            data[CONF_DECRYPTED_SECRET] = secret

        return data

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
        hub: FnosHub | None = None,
    ) -> ConfigFlowResult:
        """Create a config entry from validated user input."""
        host = user_input[CONF_HOST]
        friendly_name = user_input.get(CONF_NAME)
        entry_data = self._entry_data_from_user_input(user_input, hub)

        return self.async_create_entry(
            title=friendly_name or host,
            data=entry_data,
        )

    def _entry_data_from_user_input(
        self,
        user_input: dict[str, Any],
        hub: FnosHub | None = None,
    ) -> dict[str, Any]:
        """Build config entry data from validated user input and auth data."""
        entry_data = dict(user_input)
        if hub:
            entry_data.update(hub.stored_auth_data())
        return entry_data

    def _update_reauth_entry_from_user_input(
        self,
        user_input: dict[str, Any],
        hub: FnosHub | None = None,
    ) -> ConfigFlowResult:
        """Update the existing config entry after successful reauth."""
        return self.async_update_reload_and_abort(
            self._get_reauth_entry(),
            data_updates=self._entry_data_from_user_input(user_input, hub),
        )

    async def _clear_pending_hub(self) -> None:
        """Close and clear any pending authentication client."""
        if self._pending_hub:
            try:
                await self._pending_hub.close()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                _LOGGER.debug(
                    "Failed to close pending fnOS auth client: %s",
                    exc,
                )
        self._pending_hub = None
        self._pending_user_input = None

    async def _restart_twofa_challenge(self) -> AuthResult:
        """Rebuild a pending 2FA challenge after connection close."""
        if self._pending_user_input is None:
            return AuthResult(AuthStatus.CANNOT_CONNECT)

        if self._pending_hub:
            try:
                await self._pending_hub.close()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                _LOGGER.debug(
                    "Failed to close stale fnOS auth client: %s",
                    exc,
                )

        pending_input = self._pending_user_input
        hub = FnosHub(pending_input[CONF_HOST])
        result = await hub.login(
            pending_input[CONF_USERNAME],
            pending_input[CONF_PASSWORD],
        )

        if result.status == AuthStatus.TWOFA_REQUIRED:
            self._pending_hub = hub
            return result

        await hub.close()
        self._pending_hub = None
        return result

    async def _submit_twofa_code_with_reconnect(self, code: str) -> AuthResult:
        """Submit a 2FA code, rebuilding expired challenge state."""
        if self._pending_hub is None:
            return AuthResult(AuthStatus.CANNOT_CONNECT)

        result = await self._pending_hub.submit_twofa_code(code)
        if result.status != AuthStatus.CANNOT_CONNECT:
            return result

        restart_result = await self._restart_twofa_challenge()
        if restart_result.status != AuthStatus.TWOFA_REQUIRED:
            return restart_result

        if self._pending_hub is None:
            return AuthResult(AuthStatus.CANNOT_CONNECT)

        return await self._pending_hub.submit_twofa_code(code)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self._clear_pending_hub()

            hub = FnosHub(user_input[CONF_HOST])
            result = await hub.login(
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )

            if result.status == AuthStatus.SUCCESS:
                entry = self._create_entry_from_user_input(user_input, hub)
                await hub.close()
                return entry

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
                result = await self._submit_twofa_code_with_reconnect(code)
                if result.status == AuthStatus.SUCCESS:
                    entry_input = self._pending_user_input
                    if self.source == SOURCE_REAUTH:
                        entry = self._update_reauth_entry_from_user_input(
                            entry_input,
                            self._pending_hub,
                        )
                    else:
                        entry = self._create_entry_from_user_input(
                            entry_input,
                            self._pending_hub,
                        )
                    await self._clear_pending_hub()
                    return entry

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

    async def async_step_reauth(
        self,
        entry_data: Mapping[str, Any],
    ) -> ConfigFlowResult:
        """Handle reauthentication for an existing config entry."""
        return await self.async_step_reauth_confirm(dict(entry_data))

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Confirm updated credentials during reauthentication."""
        errors: dict[str, str] = {}
        reauth_entry_data = dict(self._get_reauth_entry().data)

        if user_input is not None:
            await self._clear_pending_hub()

            reauth_input = dict(reauth_entry_data)
            reauth_input.update(user_input)
            hub = FnosHub(reauth_input[CONF_HOST])
            result = await hub.login(
                reauth_input[CONF_USERNAME],
                reauth_input[CONF_PASSWORD],
            )

            if result.status == AuthStatus.SUCCESS:
                entry = self._update_reauth_entry_from_user_input(
                    reauth_input,
                    hub,
                )
                await hub.close()
                return entry

            if result.status == AuthStatus.TWOFA_REQUIRED:
                self._pending_hub = hub
                self._pending_user_input = reauth_input
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
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_HOST,
                        default=reauth_entry_data.get(CONF_HOST, ""),
                    ): str,
                    vol.Required(
                        CONF_USERNAME,
                        default=reauth_entry_data.get(CONF_USERNAME, ""),
                    ): str,
                    vol.Required(
                        CONF_PASSWORD,
                        default=reauth_entry_data.get(CONF_PASSWORD, ""),
                    ): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(  # pylint: disable=unused-argument
        config_entry: ConfigEntry,
    ) -> FnosOptionsFlow:
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
