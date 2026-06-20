"""fnOS Home Assistant integration."""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from fnos import FnosClient

from .auth import AuthStatus, classify_login_response, is_connection_error
from .const import (  # pylint: disable=import-self
    DOMAIN,
    CONF_AUTH_TOKEN,
    CONF_LONG_TOKEN,
    CONF_DECRYPTED_SECRET,
)

_LOGGER = logging.getLogger(__name__)

_PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]

@dataclass
class FnosData:
    """Data for the fnOS integration."""

    api: FnosClient
    coordinator: "FnosSystemCoordinator"
    disk_coordinator: "FnosDiskCoordinator"

type FnosConfigEntry = ConfigEntry[FnosData]  # noqa: F821


def on_message_handler(message):
    """消息回调处理函数"""
    _LOGGER.debug("收到消息: %s", message)


def _stored_auth_data_from_client(client: FnosClient) -> dict[str, str]:
    """Return auth material captured by pyfnos after a final login."""
    data = {}
    token = getattr(client, "token", None)
    long_token = getattr(client, "long_token", None)
    get_secret = getattr(client, "get_decrypted_secret", None)
    secret = get_secret() if get_secret else getattr(client, "decrypted_secret", None)

    if token:
        data[CONF_AUTH_TOKEN] = token
    if long_token:
        data[CONF_LONG_TOKEN] = long_token
    if secret:
        data[CONF_DECRYPTED_SECRET] = secret

    return data


def _client_has_final_auth_data(client: FnosClient) -> bool:
    """Return whether pyfnos has enough auth data for API requests."""
    return bool(_stored_auth_data_from_client(client).get(CONF_DECRYPTED_SECRET))


def _token_login_succeeded(response: dict | None) -> bool:
    """Return whether pyfnos token login returned an authenticated state."""
    if not response or response.get("errno"):
        return False

    return response.get("result") != "fail"


async def _async_update_stored_auth(
    hass: HomeAssistant,
    entry: FnosConfigEntry,
    client: FnosClient,
) -> None:
    """Persist refreshed auth material after a successful login."""
    auth_data = _stored_auth_data_from_client(client)
    if not auth_data:
        return

    data = dict(entry.data)
    data.update(auth_data)
    if data != entry.data:
        hass.config_entries.async_update_entry(entry, data=data)


async def _async_login_client(
    hass: HomeAssistant,
    entry: FnosConfigEntry,
    client: FnosClient,
) -> None:
    """Authenticate pyfnos and make sure final API auth data is available."""
    stored_token = entry.data.get(CONF_AUTH_TOKEN)
    stored_long_token = entry.data.get(CONF_LONG_TOKEN)
    stored_secret = entry.data.get(CONF_DECRYPTED_SECRET)

    if stored_token and stored_secret:
        try:
            response = await client.login_via_token(
                stored_token,
                stored_long_token,
                stored_secret,
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            if is_connection_error(exc):
                raise ConfigEntryNotReady("Cannot connect to fnOS") from exc
            _LOGGER.debug(
                "Stored fnOS session refresh failed; falling back to password login: %s",
                exc,
            )
        else:
            if _token_login_succeeded(response) and _client_has_final_auth_data(client):
                await _async_update_stored_auth(hass, entry, client)
                return

            _LOGGER.debug(
                "Stored fnOS session refresh did not produce an authenticated state"
            )

    try:
        result = await client.login(
            entry.data.get(CONF_USERNAME),
            entry.data.get(CONF_PASSWORD),
        )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        if is_connection_error(exc):
            raise ConfigEntryNotReady("Cannot connect to fnOS") from exc
        raise ConfigEntryNotReady("fnOS login failed") from exc

    _LOGGER.debug(
        "fnOS login completed with result=%s twofa_required=%s twofa_setup_required=%s",
        result.get("result"),
        result.get("twofaRequired"),
        result.get("twofaSetupRequired"),
    )

    auth_result = classify_login_response(result)
    if auth_result.status == AuthStatus.SUCCESS:
        if not _client_has_final_auth_data(client):
            raise ConfigEntryNotReady("fnOS login did not produce final auth data")
        await _async_update_stored_auth(hass, entry, client)
        return

    if auth_result.status in {
        AuthStatus.TWOFA_REQUIRED,
        AuthStatus.TWOFA_SETUP_REQUIRED,
        AuthStatus.INVALID_AUTH,
    }:
        raise ConfigEntryAuthFailed(auth_result.status.value)

    raise ConfigEntryNotReady("Unexpected fnOS login response")


async def _async_reconnect_client(
    hass: HomeAssistant,
    entry: FnosConfigEntry,
    client: FnosClient,
) -> bool:
    """Reconnect pyfnos using the integration-managed auth flow."""
    if getattr(client, "connected", False):
        return True

    await client.connect(entry.data.get(CONF_HOST))
    await _async_login_client(hass, entry, client)
    return True


def _install_reconnect_handler(
    hass: HomeAssistant,
    entry: FnosConfigEntry,
    client: FnosClient,
) -> None:
    """Install a reconnect handler that understands stored fnOS auth material."""

    async def reconnect(
        connect_timeout: float = 3.0,  # pylint: disable=unused-argument
        login_timeout: float = 10.0,  # pylint: disable=unused-argument
    ) -> bool:
        return await _async_reconnect_client(hass, entry, client)

    client.reconnect = reconnect


async def async_setup_entry(
    hass: HomeAssistant, entry: FnosConfigEntry
) -> bool:
    """Set up fnOS from a config entry."""
    from .coordinator import (  # pylint: disable=import-outside-toplevel
        FnosSystemCoordinator,
        FnosDiskCoordinator,
    )

    _LOGGER.debug("fnos.async_setup_entry called")

    client = FnosClient()
    client.on_message(on_message_handler)
    try:
        await client.connect(entry.data.get(CONF_HOST))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        raise ConfigEntryNotReady("Cannot connect to fnOS") from exc

    await _async_login_client(hass, entry, client)
    _install_reconnect_handler(hass, entry, client)

    system_coordinator = FnosSystemCoordinator(hass, entry, client)
    disk_coordinator = FnosDiskCoordinator(hass, entry, client)

    entry.runtime_data = FnosData(
        api=client,
        coordinator=system_coordinator,
        disk_coordinator=disk_coordinator,
    )

    await system_coordinator.async_config_entry_first_refresh()

    disk_coordinator.machine_id = system_coordinator.machine_id
    disk_coordinator.device_info = system_coordinator.device_info
    disk_coordinator.host_name_data = system_coordinator.data["host_name"]

    await disk_coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: FnosConfigEntry
) -> None:
    """Handle options update — reload the integration."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(
    hass: HomeAssistant, entry: FnosConfigEntry
) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("fnos.async_unload_entry called")

    return await hass.config_entries.async_unload_platforms(
        entry, _PLATFORMS
    )
