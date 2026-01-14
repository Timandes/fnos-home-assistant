"""fnOS sensor platform."""
from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity, BinarySensorEntityDescription
from homeassistant.components.binary_sensor.device_trigger import CONF_NOT_UNSAFE, CONF_UNSAFE
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
    UnitOfDataRate,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FnosData
from .const import CONF_NETWORK_IFS, CONF_VOLUMES, DOMAIN, ENTITY_UNIT_LOAD
from .coordinator import FnosCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class FnosBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes F&OS sensor entity."""

    value_fn: callable


STORAGE_DISK_BINARY_SENSORS: tuple[FnosBinarySensorEntityDescription, ...] = (
    FnosBinarySensorEntityDescription(
        key="disk_exceed_bad_sector_thr",
        translation_key="disk_exceed_bad_sector_thr",
        device_class=BinarySensorDeviceClass.SAFETY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda entity, data: entity.cal_disk_exceed_bad_sector_thr(data)
    ),
    FnosBinarySensorEntityDescription(
        key="disk_below_remain_life_thr",
        translation_key="disk_below_remain_life_thr",
        device_class=BinarySensorDeviceClass.SAFETY,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda entity, data: not data.get("smart").get("smart_status").get("passed")
    ),
)

SECURITY_BINARY_SENSORS: tuple[FnosBinarySensorEntityDescription, ...] = (
    FnosBinarySensorEntityDescription(
        key="status",
        translation_key="status",
        device_class=BinarySensorDeviceClass.SAFETY,
        value_fn=lambda data: False,
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,  # pylint: disable=unused-argument
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up F&OS sensor based on a config entry."""
    _LOGGER.debug("[%s] binary_sensor.async_setup_entry called", entry.title)

    data: FnosData = entry.runtime_data
    coordinator = data.coordinator

    entities = [
        FnosBinarySensorEntity(coordinator, description)
        for description in SECURITY_BINARY_SENSORS
    ]

    # Handle all disks
    if coordinator.data.get("disk"):
        entities.extend(
            [
                FnosDiskBinarySensorEntity(coordinator, description, disk)
                for disk in entry.data.get(
                    CONF_DISKS, coordinator.data.get("disk")
                )
                for description in STORAGE_DISK_BINARY_SENSORS
            ]
        )

    async_add_entities(entities)


class FnosBinarySensorEntity(CoordinatorEntity[FnosCoordinator], BinarySensorEntity):
    """Representation of a fnOS binary sensor."""

    entity_description: FnosBinarySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FnosCoordinator,
        description: FnosBinarySensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.machine_id}_{description.key}"
        )
        self._attr_device_info = coordinator.device_info

    @property
    def is_on(self) -> bool:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success


class FnosDiskBinarySensorEntity(CoordinatorEntity[FnosCoordinator], BinarySensorEntity):
    """Representation of a disk binary sensor in fnOS."""

    entity_description: FnosBinarySensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FnosCoordinator,
        description: FnosBinarySensorEntityDescription,
        disk
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        _LOGGER.info("[FnosDiskBinarySensorEntity] disk: %s", disk)
        _LOGGER.info(
            "[FnosDiskBinarySensorEntity] coordinator.data.get(disk): %s",
            self.coordinator.data.get("disk")
        )

        self.disk_name = disk.get("name")
        disk_sn = disk.get("serialNumber")
        disk_model = disk.get("modelName")
        disk_vendor = disk.get("vendor")
        trim_version = self.coordinator.data["host_name"].get("trimVersion")
        # hostName实际上“设置”页可修改的“设备名称”
        host_name = self.coordinator.data.get("host_name").get("hostName")

        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.machine_id}_{disk_sn}_{description.key}"
        )

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{coordinator.machine_id}_{disk_sn}")},
            name=f"{host_name} ({self.disk_name})",
            manufacturer=disk_vendor,
            model=disk_model,
            sw_version=trim_version,
            via_device=(DOMAIN, coordinator.machine_id),
        )

    @property
    def is_on(self) -> bool:
        """Return the state of the sensor."""
        data = {}
        for item in self.coordinator.data.get("disk"):
            if item.get("name") == self.disk_name:
                data = item
                break

        return self.entity_description.value_fn(self, data)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success

    def cal_disk_exceed_bad_sector_thr(self, data) -> bool:
        """Calculate disk_exceed_bad_sector_thr."""
        attrs = data.get("smart").get("ata_smart_attributes")
        if attrs is not None:
            return self._cal_disk_exceed_bad_sector_thr_for_normal_hdd(attrs)

        attrs = data.get("smart").get("nvme_smart_health_information_log")
        if attrs is not None:
            return self._cal_disk_exceed_bad_sector_thr_for_nvme_ssd(attrs)

        _LOGGER.warning("No SMART info was found for disk %s", data.get("name"))

        return False

    def _cal_disk_exceed_bad_sector_thr_for_normal_hdd(self, attrs) -> bool:
        """Calculate disk_exceed_bad_sector_thr for normal HDDs."""
        for item in attrs.get("table"):
            # TODO: 某些 SSD好像没有05
            if (item.get("id") == 5):
                threshold = item.get("thresh")
                if threshold is None:
                    threshold = 100

                return item.get("value") < threshold

        return False

    def _cal_disk_exceed_bad_sector_thr_for_nvme_ssd(self, attrs) -> bool:
        """Calculate disk_exceed_bad_sector_thr for NVME SSDs."""
        return attrs.get('available_spare') < attrs.get('available_spare_threshold')
