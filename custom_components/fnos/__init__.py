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

_PLATFORMS: list[Platform] = [Platform.SENSOR]

@dataclass
class FnosData:
    """Data for the fnOS integration."""

    api: FnosClient
    coordinator: "FnosCoordinator"

type FnosConfigEntry = ConfigEntry[FnosData]  # noqa: F821


def on_message_handler(message):
    """消息回调处理函数"""
    print(f"收到消息: {message}")

async def async_setup_entry(
    hass: HomeAssistant, entry: FnosConfigEntry
) -> bool:
    """Set up fnOS from a config entry."""
    # Import here to avoid circular import
    from .coordinator import (  # pylint: disable=import-outside-toplevel
        FnosCoordinator,
    )

    _LOGGER.warning("fnos.async_setup_entry called")

    client = FnosClient()

    # 设置消息回调
    client.on_message(on_message_handler)

    # 连接到服务器（必须指定endpoint）
    await client.connect(entry.data.get(CONF_HOST))

    # 使用命令行参数中的用户名和密码
    result = await client.login(
        entry.data.get(CONF_USERNAME),
        entry.data.get(CONF_PASSWORD)
    )
    print("登录结果:", result)

    coordinator = FnosCoordinator(hass, entry, client)

    entry.runtime_data = FnosData(
        api=client,
        coordinator=coordinator,
    )

    # Fetch initial data so we have data when entities subscribe
    #
    # If the refresh fails, async_config_entry_first_refresh will
    # raise ConfigEntryNotReady and setup will try again later
    #
    # If you do not want to retry setup on failure, use
    # coordinator.async_refresh() instead
    #
    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, _PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: FnosConfigEntry
) -> bool:
    """Unload a config entry."""

    _LOGGER.warning("fnos.async_unload_entry called")

    return await hass.config_entries.async_unload_platforms(
        entry, _PLATFORMS
    )
