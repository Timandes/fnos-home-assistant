from __future__ import annotations

import logging

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
    PERCENTAGE,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN
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
        native_unit_of_measurement=UnitOfTime.SECONDS,
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
        value_fn=lambda data: data.get("memory").get("mem").get("used") / data.get("memory").get("mem").get("total") * 100.0,
    ),
    FnosSensorEntityDescription(
        key="temperature",
        translation_key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.TEMPERATURE,
        value_fn=lambda data: data.get('cpu').get("cpu").get('temp')[0],
    ),
    FnosSensorEntityDescription(
        key="disk_usage",
        translation_key="disk_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        device_class=SensorDeviceClass.POWER_FACTOR,
        value_fn=lambda data: max((item["fssize"] - item["frsize"]) / item["fssize"] * 100.0 for item in data.get("store").get("array"))
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up F&OS sensor based on a config entry."""
    _LOGGER.warn(f"[{entry.title}] sensor.async_setup_entry called")

    data: FnosData = entry.runtime_data
    coordinator = data.coordinator

    entities = [
        FnosSensorEntity(coordinator, description) for description in SENSOR_TYPES
    ]

    async_add_entities(entities)


class FnosSensorEntity(CoordinatorEntity[FnosCoordinator], SensorEntity):
    """Representation of a F&OS sensor."""

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
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{description.key}"

        # Set device info
        #self._device_id = coordinator.device_id
        self._attr_device_info = coordinator.device_info


    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.entity_description.value_fn(self.coordinator.data)