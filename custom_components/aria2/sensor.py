"""Support for aria2 downloader."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any, Callable

from homeassistant.const import CONF_HOST, UnitOfDataRate
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    CoordinatorEntity,
)

from .aria2_client import WSClient
from .aria2_commands import (
    DownloadKeys,
    TellActive,
    TellWaiting,
    GetGlobalStat,
)
from .const import (
    DOMAIN,
    TIMEOUT_SECONDS,
    COORDINATOR_FAST_UPDATE_SECONDS,
    STATE_ACTIVE,
    STATE_WAITING,
    STATE_PAUSED,
    BYTES_TO_MEGABYTES,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities) -> None:
    """Set up aria2 sensor platform.

    Args:
        hass: Home Assistant instance
        config_entry: ConfigEntry with aria2 server configuration
        async_add_entities: Callback to add sensor entities
    """
    _LOGGER.debug("Adding aria2 to Home Assistant")

    ws_client: WSClient = hass.data[DOMAIN][config_entry.entry_id]["ws_client"]
    service_attributes: dict[str, Any] = hass.data[DOMAIN][config_entry.entry_id]["service_attributes"]

    async def async_state_update_data():
        """Fetch aria 2 stats data from API."""
        async with asyncio.timeout(TIMEOUT_SECONDS):
            return await ws_client.call(GetGlobalStat())

    state_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="sensor",
        update_method=async_state_update_data,
        update_interval=timedelta(seconds=COORDINATOR_FAST_UPDATE_SECONDS),
    )

    aria_name = f"aria {hass.data[DOMAIN][config_entry.entry_id][CONF_HOST]}"
    async_add_entities(
        [
            Aria2Sensor(
                state_coordinator,
                aria_name,
                service_attributes,
                lambda data: data.download_speed / BYTES_TO_MEGABYTES,
                UnitOfDataRate.MEGABYTES_PER_SECOND,
                "download speed",
            ),
            Aria2Sensor(
                state_coordinator,
                aria_name,
                service_attributes,
                lambda data: data.upload_speed / BYTES_TO_MEGABYTES,
                UnitOfDataRate.MEGABYTES_PER_SECOND,
                "upload speed",
            ),
            Aria2Sensor(
                state_coordinator,
                aria_name,
                service_attributes,
                lambda data: data.num_active,
                None,
                "number of active download",
            ),
            Aria2Sensor(
                state_coordinator,
                aria_name,
                service_attributes,
                lambda data: data.num_waiting,
                None,
                "number of waiting download",
            ),
            Aria2Sensor(
                state_coordinator,
                aria_name,
                service_attributes,
                lambda data: data.num_stopped_total,
                None,
                "number of stopped download",
            ),
            Aria2StateListSensor(
                ws_client,
                aria_name,
                service_attributes,
                [STATE_ACTIVE],
                STATE_ACTIVE,
                "active gids"
            ),
            Aria2StateListSensor(
                ws_client,
                aria_name,
                service_attributes,
                [STATE_WAITING, STATE_PAUSED],
                STATE_WAITING,
                "waiting gids"
            )
        ],
        True,
    )


class Aria2StateListSensor(SensorEntity):
    """Sensor for aria2 download GID lists by state.

    Tracks downloads in specific states (active, waiting, paused) and
    provides their GIDs as a newline-separated list.
    """

    _attr_should_poll = False
    _attr_available = True

    def __init__(
        self,
        ws_client: WSClient,
        aria_name: str,
        service_attributes: dict[str, Any],
        states: list[str],
        command_state: str,
        sensor_name: str,
    ) -> None:
        """Initialize the sensor."""
        self._gid_set: set[str] = set()
        self._aria_name = aria_name
        self._states = states
        self._command_state = command_state
        self._ws_client = ws_client

        self._attr_name = f"{aria_name}-{sensor_name}"
        self._attr_unique_id = f"{aria_name}-{sensor_name}"
        self._attr_device_info = service_attributes

    @property
    def state(self) -> str:
        """Return the state of the sensor."""
        return "\n".join(sorted(self._gid_set))

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        async def on_download_state_updated(download_gid: str, status: str) -> None:
            if status in self._states:
                self._gid_set.add(download_gid)
            else:
                self._gid_set.discard(download_gid)

            self.async_write_ha_state()

        self._ws_client.on_download_state_updated(on_download_state_updated)

        state_to_command = {
            STATE_ACTIVE: TellActive,
            STATE_WAITING: TellWaiting
        }
        downloads = await self._ws_client.call(state_to_command.get(self._command_state)(keys=[DownloadKeys.GID, DownloadKeys.STATUS]))
        self._gid_set = {d.gid for d in downloads if d.status in self._states}
        
class Aria2Sensor(CoordinatorEntity, SensorEntity):
    """Base sensor for aria2 statistics.

    Generic sensor that displays aria2 statistics like download speed,
    upload speed, and download counts.
    """

    _attr_should_poll = False

    def __init__(
        self,
        coordinator: DataUpdateCoordinator,
        aria_name: str,
        service_attributes: dict[str, Any],
        state_function: Callable,
        unit: str | None,
        sensor_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._state_function = state_function

        self._attr_name = f"{aria_name}-{sensor_name}"
        self._attr_unique_id = f"{aria_name}-{sensor_name}"
        self._attr_device_info = service_attributes
        self._attr_native_unit_of_measurement = unit

        # Set state_class and device_class based on unit
        if unit == UnitOfDataRate.MEGABYTES_PER_SECOND:
            self._attr_state_class = SensorStateClass.MEASUREMENT
            self._attr_device_class = SensorDeviceClass.DATA_RATE
        elif unit is None:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        if self.coordinator.data:
            return round(self._state_function(self.coordinator.data), 2)
        return None
