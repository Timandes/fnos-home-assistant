from datetime import timedelta
import logging
import uuid

import async_timeout

from homeassistant.components.light import LightEntity
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN

from fnos import (
    SystemInfo, 
    ResourceMonitor, 
    Store, 
    NotConnectedError,
)

_LOGGER = logging.getLogger(__name__)

class FnosCoordinator(DataUpdateCoordinator):
    """My custom coordinator."""

    def __init__(self, hass, config_entry, api):
        """Initialize my coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Name of the data. For logging purposes.
            name="fnOS",
            config_entry=config_entry,
            # Polling interval. Will only be polled if there are subscribers.
            update_interval=timedelta(seconds=30),
            # Set always_update to `False` if the data returned from the
            # api can be compared via `__eq__` to avoid duplicate updates
            # being dispatched to listeners
            always_update=True
        )
        self.api = api
        self.system_info = SystemInfo(self.api)
        self.res_mon = ResourceMonitor(self.api)
        self.stor = Store(self.api)

    async def _async_setup(self):
        """Set up the coordinator

        This is the place to set up your coordinator,
        or to load data, that only needs to be loaded once.

        This method will be called automatically during
        coordinator.async_config_entry_first_refresh.
        """
        job_id = self._generate_job_id()
        _LOGGER.warn(f"[{self.config_entry.title}] [{job_id}] _async_setup called")
        
        self.data = await self._async_retrieve_from_fnos(job_id)

        machine_id_resp = await self.system_info.get_machine_id()
        machine_id = machine_id_resp.get('data').get('machineId')
        self.machine_id = machine_id

        # hostName实际上“设置”页可修改的“设备名称”
        host_name = self.data.get("host_name").get('hostName')
        trim_version = self.data.get("host_name").get('trimVersion')

        hardware_info_resp = await self.system_info.get_hardware_info()
        cpu_name = hardware_info_resp.get('data').get('cpu').get('name')
        
        self.device_id = machine_id
        self.device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{machine_id}")},
            name=f"{host_name}",
            manufacturer="fnOS",
            model=cpu_name,
            sw_version=trim_version,
            via_device=(DOMAIN, machine_id),
            #configuration_url="self._api.config_url",
        )

    async def async_setup(self):
        print("async_setup called")

    def _generate_job_id(self):
        return uuid.uuid4().hex

    async def _async_update_data(self):
        """Fetch data from API endpoint.

        This is the place to pre-process the data to lookup tables
        so entities can quickly look up their data.
        """
        job_id = self._generate_job_id()
        _LOGGER.warn(f"[{self.config_entry.title}] [{job_id}] _async_update_data called")

        return await self._async_retrieve_from_fnos(job_id)
    
    async def _async_retrieve_from_fnos(self, job_id):
        # try:
        #     # Note: asyncio.TimeoutError and aiohttp.ClientError are already
        #     # handled by the data update coordinator.
        #     async with async_timeout.timeout(10):
        #         # Grab active context variables to limit data required to be fetched from API
        #         # Note: using context is not required if there is no need or ability to limit
        #         # data retrieved from API.
        #         listening_idx = set(self.async_contexts())
        #         return await self.api.fetch_data(listening_idx)
        # except ApiAuthError as err:
        #     # Raising ConfigEntryAuthFailed will cancel future updates
        #     # and start a config flow with SOURCE_REAUTH (async_step_reauth)
        #     raise ConfigEntryAuthFailed from err
        # except ApiError as err:
        #     raise UpdateFailed(f"Error communicating with API: {err}")


        try:
            host_name_resp = await self.system_info.get_host_name()
        except NotConnectedError as err:
            await self.api.reconnect()
            host_name_resp = await self.system_info.get_host_name()
        
        try:
            uptime_result = await self.system_info.get_uptime()
        except NotConnectedError as err:
            await self.api.reconnect()
            uptime_result = await self.system_info.get_uptime()
        
        try:
            cpu_result = await self.res_mon.cpu()
        except NotConnectedError as err:
            await self.api.reconnect()
            cpu_result = await self.res_mon.cpu()
        
        try:
            memory_result = await self.res_mon.memory()
        except NotConnectedError as err:
            await self.api.reconnect()
            memory_result = await self.res_mon.memory()

        try:
            store_result = await self.stor.general()
        except NotConnectedError as err:
            await self.api.reconnect()
            store_result = await self.stor.general()
        _LOGGER.warn(f"[{self.config_entry.title}] [{job_id}] _async_update_data got stor.general {store_result}")

        disk_resp = await self._async_retrieve_disk_from_fnos(job_id)

        #print(f"[{job_id}] 系统运行时间信息5:", uptime_result)
        _LOGGER.warn(f"[{self.config_entry.title}] [{job_id}] _async_update_data returned with {uptime_result}")
        # self.hass.states.async_set(f"{DOMAIN}.uptime", uptime_result.get('data').get('uptime'))
        return {
            "uptime": uptime_result.get('data'),
            "host_name": host_name_resp.get('data'),
            "cpu": cpu_result.get('data'),
            "memory": memory_result.get('data'),
            "store": store_result,
            "disk": disk_resp,
        }
    
    async def _async_retrieve_disk_from_fnos(self, job_id):
        try:
            disk_resp = await self.stor.list_disks()
        except NotConnectedError as err:
            await self.api.reconnect()
            disk_resp = await self.stor.list_disks()

        _LOGGER.warn(f"[{self.config_entry.title}] [{job_id}] _async_update_data got stor.listDisk {disk_resp}")

        for item in disk_resp.get("disk"):
            name = item.get("name")

            try:
                smart_resp = await self.stor.get_disk_smart(name)
            except NotConnectedError as err:
                await self.api.reconnect()
                smart_resp = await self.stor.get_disk_smart(name)

            item["smart"] = smart_resp.get("smart")

        return disk_resp.get('disk')