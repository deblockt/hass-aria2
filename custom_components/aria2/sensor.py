"""Support for aria2 downloader."""

import asyncio
from datetime import timedelta
import logging
from custom_components.aria2.aria2_client import WSClient
from custom_components.aria2.aria2_commands import (
    DownoladKeys,
    TellActive,
    TellStopped,
    TellWaiting,
    GetGlobalStat,
)

from homeassistant.const import CONF_HOST, UnitOfDataRate
from homeassistant.components.sensor import SensorEntity

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)
import async_timeout

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the aria2."""
    _LOGGER.debug("Adding aria2 to Home Assistant")

    ws_client: WSClient = hass.data[DOMAIN][config_entry.entry_id]["ws_client"]
    service_attributes = hass.data[DOMAIN][config_entry.entry_id]["service_attributes"]

    async def async_state_update_data():
        """Fetch aria 2 stats data from API."""
        async with async_timeout.timeout(10):
            return await ws_client.call(GetGlobalStat())

    state_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="sensor",
        update_method=async_state_update_data,
        update_interval=timedelta(seconds=3),
    )

    aria_name = "aria " + hass.data[DOMAIN][config_entry.entry_id][CONF_HOST]
    async_add_entities(
        [
            Aria2Sensor(
                state_coordinator,
                aria_name,
                service_attributes,
                lambda data: data.download_speed / 1000000,
                UnitOfDataRate.MEGABYTES_PER_SECOND,
                "download speed",
            ),
            Aria2Sensor(
                state_coordinator,
                aria_name,
                service_attributes,
                lambda data: data.upload_speed / 1000000,
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
                'active',
                "active gids"
            ),
            Aria2StateListSensor(
                ws_client,
                aria_name,
                service_attributes,
                'waiting',
                "waiting gids"
            )
        ],
        True,
    )


class Aria2StateListSensor(SensorEntity):
    """A base class for state gid list sensor."""

    def __init__(
        self,
        ws_client,
        aria_name,
        service_attributes,
        state,
        sensor_name,
    ):
        """Initialize the sensor."""
        self._gid_list = ""
        self._aria_name = aria_name
        self._sensor_name = sensor_name
        self._state = state
        self._ws_client = ws_client
        self._service_attributes = service_attributes
        
    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._aria_name}-{self._sensor_name}"

    @property
    def device_info(self):
        return self._service_attributes

    @property
    def unique_id(self):
        """Return the unique id of the entity."""
        return f"{self._aria_name}-{self._sensor_name}"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._gid_list

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return None

    @property
    def should_poll(self):
        """Return the polling requirement for this sensor."""
        return False

    @property
    def available(self):
        """Could the device be accessed during the last update call."""
        return True

    async def async_added_to_hass(self):
        """Handle entity which will be added."""
        async def on_download_state_updated(download_gid, status):
            if status == self._state:
                if not download_gid in self._gid_list:
                    self._gid_list = self._gid_list + "\n" + download_gid
            else:
                self._gid_list = "\n".join(gid for gid in self._gid_list.split("\n") if gid != download_gid)

            self.async_write_ha_state()
            
        self._ws_client.on_download_state_updated(on_download_state_updated)
        
        state_to_command = {
            "active": TellActive,
            "waiting": TellWaiting
        }
        downloads = await self._ws_client.call(state_to_command.get(self._state)(keys=[DownoladKeys.GID, DownoladKeys.STATUS]))
        self._gid_list = "\n".join(d.gid for d in downloads if d.status == self._state)
        
class Aria2Sensor(SensorEntity):
    """A base class for all aria2 sensors."""

    def __init__(
        self,
        coordinator,
        aria_name,
        service_attributes,
        state_function,
        unit,
        sensor_name,
    ):
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._service_attributes = service_attributes
        self._aria_name = aria_name
        self._sensor_name = sensor_name
        self._state_function = state_function
        self._unit = unit

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._aria_name}-{self._sensor_name}"

    @property
    def device_info(self):
        return self._service_attributes

    @property
    def unique_id(self):
        """Return the unique id of the entity."""
        return f"{self._aria_name}-{self._sensor_name}"

    @property
    def state(self):
        """Return the state of the sensor."""
        if self._coordinator.data:
            return round(self._state_function(self._coordinator.data), 2)
        else:
            return None

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement of this entity, if any."""
        return self._unit

    @property
    def should_poll(self):
        """Return the polling requirement for this sensor."""
        return False

    @property
    def available(self):
        """Could the device be accessed during the last update call."""
        return True

    async def async_added_to_hass(self):
        """Handle entity which will be added."""
        self.async_on_remove(
            self._coordinator.async_add_listener(self.async_write_ha_state)
        )
