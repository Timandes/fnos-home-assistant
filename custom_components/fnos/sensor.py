"""fnOS sensor platform."""
from __future__ import annotations

import logging

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_DISKS,
    PERCENTAGE,
    EntityCategory,
    UnitOfInformation,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_VOLUMES, DOMAIN
from . import FnosData
from .coordinator import FnosCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class FnosSensorEntityDescription(SensorEntityDescription):
    """Describes F&OS sensor entity."""

    value_fn: callable


SENSOR_TYPES: tuple[FnosSensorEntityDescription, ...] = (
    FnosSensorEntityDescription(
        key="uptime",
        translation_key="uptime",
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.DURATION,
        value_fn=lambda data: data.get("uptime").get("uptime"),
    ),
    FnosSensorEntityDescription(
        key="cpu_usage",
        translation_key="cpu_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER_FACTOR,
        value_fn=lambda data: data.get("cpu").get("cpu").get("busy").get("all"),
    ),
    FnosSensorEntityDescription(
        key="memory_usage",
        translation_key="memory_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER_FACTOR,
        value_fn=lambda data: (data.get("memory").get("mem").get("used") /
                               data.get("memory").get("mem").get("total") * 100.0),
    ),
    FnosSensorEntityDescription(
        key="cpu_temperature",
        translation_key="cpu_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda data: data.get('cpu').get("cpu").get('temp')[0],
    ),
    # Deprecated by volume_percentage_used
    FnosSensorEntityDescription(
        key="disk_usage",
        translation_key="disk_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER_FACTOR,
        value_fn=lambda data: max((item["fssize"] - item["frsize"]) /
                                  item["fssize"] * 100.0
                                  for item in data.get("store").get("array"))
    ),
)

STORAGE_VOL_SENSORS: tuple[FnosSensorEntityDescription, ...] = (
    FnosSensorEntityDescription(
        key="volume_size_used",
        translation_key="volume_size_used",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.TERABYTES,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("fssize") - data.get("frsize")
    ),
    FnosSensorEntityDescription(
        key="volume_size_total",
        translation_key="volume_size_total",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.TERABYTES,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("fssize")
    ),
    FnosSensorEntityDescription(
        key="volume_percentage_used",
        translation_key="volume_percentage_used",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda data: ((data["fssize"] - data["frsize"]) /
                               data["fssize"] * 100.0)
    ),
)

STORAGE_DISK_SENSORS: tuple[FnosSensorEntityDescription, ...] = (
    FnosSensorEntityDescription(
        key="disk_smart_status",
        translation_key="disk_smart_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.get("smart").get('smart_status').get('passed')
    ),
    # FnosSensorEntityDescription(
    #     key="disk_status",
    #     translation_key="disk_status",
    #     entity_category=EntityCategory.DIAGNOSTIC,
    #     value_fn=lambda data: data.get("todo")
    # ),
    # FnosSensorEntityDescription(
    #     key="disk_temp",
    #     translation_key="disk_temp",
    #     native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    #     device_class=SensorDeviceClass.TEMPERATURE,
    #     state_class=SensorStateClass.MEASUREMENT,
    #     entity_category=EntityCategory.DIAGNOSTIC,
    #     value_fn=lambda data: data.get("todo")
    #),
)

async def async_setup_entry(
    _hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up F&OS sensor based on a config entry."""
    _LOGGER.warning("[%s] sensor.async_setup_entry called", entry.title)

    data: FnosData = entry.runtime_data
    coordinator = data.coordinator

    entities = [
        FnosSensorEntity(coordinator, description) for description in SENSOR_TYPES
    ]

    # Handle all volumes
    if coordinator.data.get("store").get("array"):
        entities.extend(
            [
                FnosVolumeSensorEntity(coordinator, description, volume)
                for volume in entry.data.get(CONF_VOLUMES,
                                           coordinator.data.get("store").get("array"))
                for description in STORAGE_VOL_SENSORS
            ]
        )

    # Handle all disks
    if coordinator.data.get("disk"):
        entities.extend(
            [
                FnosDiskSensorEntity(coordinator, description, disk)
                for disk in entry.data.get(CONF_DISKS, coordinator.data.get("disk"))
                for description in STORAGE_DISK_SENSORS
            ]
        )

    async_add_entities(entities)


class FnosSensorEntity(CoordinatorEntity[FnosCoordinator], SensorEntity):
    """Representation of a fnOS sensor."""

    entity_description: FnosSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FnosCoordinator,
        description: FnosSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.machine_id}_{description.key}"
        self._attr_device_info = coordinator.device_info

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success


class FnosVolumeSensorEntity(CoordinatorEntity[FnosCoordinator], SensorEntity):
    """Representation of a volume sensor in fnOS."""

    entity_description: FnosSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FnosCoordinator,
        description: FnosSensorEntityDescription,
        volume
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.volume_name = volume.get("name")
        volume_uuid = volume.get("uuid")
        trim_version = self.coordinator.data['host_name'].get('trimVersion')
        # hostName实际上“设置”页可修改的“设备名称”
        host_name = self.coordinator.data.get("host_name").get('hostName')

        self.entity_description = description
        self._attr_unique_id = f"{coordinator.machine_id}_{volume_uuid}_{description.key}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.machine_id}_{volume_uuid}")},
            name=f"{host_name} ({self.volume_name})",
            manufacturer="fnOS",
            model="Volume",
            sw_version=trim_version,
            via_device=(DOMAIN, coordinator.machine_id),
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        data = {}
        for item in self.coordinator.data.get("store").get("array"):
            if item.get("name") == self.volume_name:
                data = item
                break

        return self.entity_description.value_fn(data)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success


class FnosDiskSensorEntity(CoordinatorEntity[FnosCoordinator], SensorEntity):
    """Representation of a disk sensor in fnOS."""

    entity_description: FnosSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FnosCoordinator,
        description: FnosSensorEntityDescription,
        disk
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        _LOGGER.warning("[FnosDiskSensorEntity] disk: %s", disk)
        _LOGGER.warning("[FnosDiskSensorEntity] coordinator.data.get(disk): %s",
                       self.coordinator.data.get("disk"))

        self.disk_name = disk.get("name")
        disk_sn = disk.get("serialNumber")
        disk_model = disk.get("modelName")
        disk_vendor = disk.get("vendor")
        trim_version = self.coordinator.data['host_name'].get('trimVersion')
        # hostName实际上“设置”页可修改的“设备名称”
        host_name = self.coordinator.data.get("host_name").get('hostName')

        self.entity_description = description
        self._attr_unique_id = f"{coordinator.machine_id}_{disk_sn}_{description.key}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.machine_id}_{disk_sn}")},
            name=f"{host_name} ({self.disk_name})",
            manufacturer=disk_vendor,
            model=disk_model,
            sw_version=trim_version,
            via_device=(DOMAIN, coordinator.machine_id),
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        data = {}
        for item in self.coordinator.data.get("disk"):
            if item.get("name") == self.disk_name:
                data = item
                break

        return self.entity_description.value_fn(data)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success
