"""Support for aria2 downloader."""
import asyncio
import logging

from homeassistant.const import CONF_HOST, DATA_RATE_MEGABYTES_PER_SECOND
from homeassistant.components.sensor import SensorEntity

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the aria2."""
    _LOGGER.debug("Adding aria2 to Home Assistant")

    ws_client = hass.data[DOMAIN][config_entry.entry_id]['ws_client']

    state_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="sensor"
    )
    ws_client.on_global_stat(lambda stat: state_coordinator.async_set_updated_data(stat))

    async def refresh_stats():
        while True:
            await ws_client.call_global_stat()
            await ws_client.refresh_downloads()
            await asyncio.sleep(3)

    hass.loop.create_task(refresh_stats())

    aria_name = "aria " + hass.data[DOMAIN][config_entry.entry_id][CONF_HOST]
    async_add_entities([
        Aria2Sensor(state_coordinator, aria_name, lambda data: data.download_speed / 1000000, DATA_RATE_MEGABYTES_PER_SECOND, "download speed"),
        Aria2Sensor(state_coordinator, aria_name, lambda data: data.upload_speed / 1000000, DATA_RATE_MEGABYTES_PER_SECOND, "upload speed"),
        Aria2Sensor(state_coordinator, aria_name, lambda data: data.num_active, None, "number of active download"),
        Aria2Sensor(state_coordinator, aria_name, lambda data: data.num_waiting, None, "number of waiting download"),
        Aria2Sensor(state_coordinator, aria_name, lambda data: data.num_stopped_total, None, "number of stopped download")
    ], True)

class Aria2Sensor(SensorEntity):
    """A base class for all aria2 sensors."""

    def __init__(self, coordinator, aria_name, state_function, unit, sensor_name):
        """Initialize the sensor."""
        self._coordinator = coordinator
        self._aria_name = aria_name
        self._sensor_name = sensor_name
        self._state_function = state_function
        self._unit = unit

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._sensor_name

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


