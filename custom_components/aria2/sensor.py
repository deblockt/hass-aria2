"""Support for aria2 downloader."""
import logging

from datetime import timedelta
from homeassistant.const import CONF_HOST, DATA_RATE_MEGABYTES_PER_SECOND
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback

import async_timeout


from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up the aria2."""
    _LOGGER.debug("Adding aria2 to Home Assistant")

    aria2 = hass.data[DOMAIN][config_entry.entry_id]['aria2_client']

    async def async_state_update_data():
        """Fetch aria 2 stats data from API."""
        try:
            async with async_timeout.timeout(3):
                return await hass.async_add_executor_job(aria2.get_stats)
        except:
            _LOGGER.exception('can not refresh aria2 sensor due to exception')
            return None


    state_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="sensor",
        update_method=async_state_update_data,
        update_interval=timedelta(seconds=30),
    )

    await state_coordinator.async_config_entry_first_refresh()

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


