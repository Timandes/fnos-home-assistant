"""fnOS coordinator for Home Assistant."""
from datetime import timedelta
import logging

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.device_registry import DeviceInfo

from fnos import (
    SystemInfo,
    ResourceMonitor,
    Store,
    NotConnectedError,
)

from .const import (
    DOMAIN,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_DISK_SCAN_INTERVAL,
    CONF_SCAN_INTERVAL,
    CONF_DISK_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class FnosSystemCoordinator(DataUpdateCoordinator):
    """Coordinator for system-level data (CPU, memory, network, uptime)."""

    def __init__(self, hass, config_entry, api):
        """Initialize system coordinator."""
        interval = config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        super().__init__(
            hass,
            _LOGGER,
            name="fnOS System",
            config_entry=config_entry,
            update_interval=timedelta(seconds=interval),
            always_update=True
        )
        self.api = api
        self.system_info = SystemInfo(self.api)
        self.res_mon = ResourceMonitor(self.api)
        self.stor = Store(self.api)
        self.data = None
        self.machine_id = None
        self.device_id = None
        self.device_info = None
        self.host_name_data = None

    async def _async_setup(self):
        """Set up the coordinator.

        Called automatically during async_config_entry_first_refresh.
        """
        _LOGGER.debug(
            "[%s] system coordinator _async_setup called",
            self.config_entry.title,
        )

        self.data = await self._async_update_data()

        machine_id_resp = await self.system_info.get_machine_id()
        machine_id = machine_id_resp.get("data").get("machineId")
        self.machine_id = machine_id

        self.host_name_data = self.data.get("host_name")
        host_name = self.host_name_data.get("hostName")
        trim_version = self.host_name_data.get("trimVersion")

        hardware_info_resp = await self.system_info.get_hardware_info()
        cpu_name = hardware_info_resp.get("data").get("cpu").get("name")

        self.device_id = machine_id
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{machine_id}")},
            name=f"{host_name}",
            manufacturer="fnOS",
            model=cpu_name,
            sw_version=trim_version,
            via_device=(DOMAIN, machine_id),
        )

    async def async_setup(self):
        """Set up coordinator."""
        _LOGGER.debug("system coordinator async_setup called")

    async def async_shutdown(self) -> None:
        """Shutdown the coordinator."""
        if self.api:
            await self.api.close()

    async def _async_update_data(self):
        """Fetch system-level data from fnOS API."""
        _LOGGER.debug(
            "[%s] system coordinator _async_update_data called",
            self.config_entry.title,
        )
        _LOGGER.debug("[%s] system coordinator update", self.config_entry.title)

        try:
            host_name_resp = await self.system_info.get_host_name()
        except NotConnectedError:
            await self.api.reconnect()
            host_name_resp = await self.system_info.get_host_name()

        try:
            uptime_result = await self.system_info.get_uptime()
        except NotConnectedError:
            await self.api.reconnect()
            uptime_result = await self.system_info.get_uptime()

        try:
            cpu_result = await self.res_mon.cpu()
        except NotConnectedError:
            await self.api.reconnect()
            cpu_result = await self.res_mon.cpu()

        try:
            memory_result = await self.res_mon.memory()
        except NotConnectedError:
            await self.api.reconnect()
            memory_result = await self.res_mon.memory()

        try:
            net_result = await self.res_mon.net()
        except NotConnectedError:
            await self.api.reconnect()
            net_result = await self.res_mon.net()

        data = {
            "uptime": uptime_result.get("data"),
            "host_name": host_name_resp.get("data"),
            "cpu": cpu_result.get("data"),
            "memory": memory_result.get("data"),
            "net": net_result.get("data"),
        }
        _LOGGER.debug("_async_update_data returned with %s", data)
        return data


class FnosDiskCoordinator(DataUpdateCoordinator):
    """Coordinator for disk/storage data (volumes, SMART, disk IO)."""

    def __init__(self, hass, config_entry, api):
        """Initialize disk coordinator."""
        interval = config_entry.options.get(
            CONF_DISK_SCAN_INTERVAL, DEFAULT_DISK_SCAN_INTERVAL
        )
        super().__init__(
            hass,
            _LOGGER,
            name="fnOS Disk",
            config_entry=config_entry,
            update_interval=timedelta(seconds=interval),
            always_update=True
        )
        self.api = api
        self.stor = Store(self.api)
        self.res_mon = ResourceMonitor(self.api)
        self.data = None
        self.machine_id = None
        self.device_info = None
        self.host_name_data = None

    async def _async_setup(self):
        """Set up the disk coordinator."""
        _LOGGER.debug(
            "[%s] disk coordinator _async_setup called",
            self.config_entry.title,
        )
        self.data = await self._async_update_data()

    async def async_setup(self):
        """Set up coordinator."""
        _LOGGER.debug("disk coordinator async_setup called")

    async def _async_update_data(self):
        """Fetch disk/storage data from fnOS API."""
        _LOGGER.debug(
            "[%s] disk coordinator _async_update_data called",
            self.config_entry.title,
        )
        _LOGGER.debug("[%s] disk coordinator update", self.config_entry.title)

        try:
            store_result = await self.stor.general()
        except NotConnectedError:
            await self.api.reconnect()
            store_result = await self.stor.general()
        _LOGGER.debug("_async_update_data got stor.general %s", store_result)

        disk_resp = await self._async_retrieve_disk()

        data = {
            "store": store_result,
            "disk": disk_resp,
        }
        _LOGGER.debug("_async_update_data returned with %s", data)
        return data

    async def _async_retrieve_disk(self):
        """Fetch disk list with SMART and IO data."""
        try:
            disk_resp = await self.stor.list_disks()
        except NotConnectedError:
            await self.api.reconnect()
            disk_resp = await self.stor.list_disks()
        _LOGGER.debug("_async_update_data got stor.listDisk %s", disk_resp)

        try:
            resmon_disk_resp = await self.res_mon.disk()
        except NotConnectedError:
            await self.api.reconnect()
            resmon_disk_resp = await self.res_mon.disk()
        _LOGGER.debug("_async_update_data got resmon.disk %s", resmon_disk_resp)

        for item in disk_resp.get("disk"):
            name = item.get("name")

            resmon = self._find_from_resmon(
                resmon_disk_resp.get("data").get("disk"), name
            )
            item["resmon"] = resmon

            try:
                smart_resp = await self.stor.get_disk_smart(name)
            except NotConnectedError:
                await self.api.reconnect()
                smart_resp = await self.stor.get_disk_smart(name)

            item["smart"] = smart_resp.get("smart")

        return disk_resp.get("disk")

    def _find_from_resmon(self, resmon_disks, name):
        """Find resmon data for a specific disk."""
        for item in resmon_disks:
            if item.get("name") == name:
                return item
        return None


# Backward-compatible alias
FnosCoordinator = FnosSystemCoordinator
