from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.components.light import LightEntity
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

from .coordinator import FnosCoordinator

from dataclasses import dataclass
from homeassistant.core import callback

from fnos import FnosClient, SystemInfo
import asyncio

_LOGGER = logging.getLogger(__name__)

# TODO List the platforms that you want to support.
# For your initial PR, limit it to 1 platform.
_PLATFORMS: list[Platform] = [Platform.SENSOR]

@dataclass
class FnosData:
    """Data for the synology_dsm integration."""

    api: FnosClient
    coordinator: FnosCoordinator

# TODO Create ConfigEntry type alias with API object
# TODO Rename type alias and update all entry annotations
type New_NameConfigEntry = ConfigEntry[FnosData]  # noqa: F821


def on_message_handler(message):
    """消息回调处理函数"""
    print(f"收到消息: {message}")

# TODO Update entry annotation
async def async_setup_entry(hass: HomeAssistant, entry: New_NameConfigEntry) -> bool:
    """Set up fnOS from a config entry."""

    _LOGGER.warn("fnos.async_setup_entry called")

    # TODO 1. Create API instance
    # TODO 2. Validate the API connection (and authentication)
    # TODO 3. Store an API object for your platforms to access
    # entry.runtime_data = MyAPI(...)

    client = FnosClient()
    
    # 设置消息回调
    client.on_message(on_message_handler)
    
    # 连接到服务器（必须指定endpoint）
    await client.connect(entry.data.get(CONF_HOST))
    
    # 等待连接建立
    await asyncio.sleep(3)

    # 使用命令行参数中的用户名和密码
    result = await client.login(entry.data.get(CONF_USERNAME), entry.data.get(CONF_PASSWORD))
    print("登录结果:", result)

    coordinator = FnosCoordinator(hass, entry, client)

    entry.runtime_data = FnosData(
        api = client,
        coordinator = coordinator,
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


# TODO Update entry annotation
async def async_unload_entry(hass: HomeAssistant, entry: New_NameConfigEntry) -> bool:
    """Unload a config entry."""

    _LOGGER.warn("fnos.async_unload_entry called")

    return await hass.config_entries.async_unload_platforms(entry, _PLATFORMS)
