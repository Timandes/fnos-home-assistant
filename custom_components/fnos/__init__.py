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

from fnos import FnosClient

from .const import DOMAIN  # pylint: disable=import-self

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
    await client.connect(entry.data.get(CONF_HOST))

    result = await client.login(
        entry.data.get(CONF_USERNAME),
        entry.data.get(CONF_PASSWORD)
    )
    _LOGGER.debug("登录结果: %s", result)

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
