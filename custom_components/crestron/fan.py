"""Platform for Crestron Fan integration."""
import voluptuous as vol
import logging

import homeassistant.helpers.config_validation as cv
from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.util import slugify
from homeassistant.const import CONF_NAME
from .const import HUB, DOMAIN, CONF_SPEED_JOIN, CONF_SPEED_STEPS, CONF_REVERSE_JOIN

_LOGGER = logging.getLogger(__name__)

PLATFORM_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Required(CONF_SPEED_JOIN): cv.positive_int,
        vol.Optional(CONF_SPEED_STEPS): cv.positive_int,
        vol.Optional(CONF_REVERSE_JOIN): cv.positive_int,
    },
    extra=vol.ALLOW_EXTRA,
)

async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    hub = hass.data[DOMAIN][HUB]
    entity = [CrestronFan(hub, config)]
    async_add_entities(entity)


class CrestronFan(FanEntity):
    def __init__(self, hub, config):
        self._hub = hub
        self._name = config.get(CONF_NAME)
        self._speed_join = config.get(CONF_SPEED_JOIN)
        self._speed_steps = config.get(CONF_SPEED_STEPS)
        self._reverse_join = config.get(CONF_REVERSE_JOIN)
        self._unique_id = slugify(f"{DOMAIN}_fan_{self._name}")
        
        # Set up supported features
        self._attr_supported_features = FanEntityFeature.SET_SPEED
        if self._reverse_join is not None:
            self._attr_supported_features |= FanEntityFeature.DIRECTION
        
        # Configure speed mode based on speed_steps
        if self._speed_steps is not None:
            # Stepped speed control
            self._attr_speed_count = self._speed_steps
        else:
            # Stepless analog control (0-65535 mapped to 0-100)
            self._attr_speed_count = 100

    async def async_added_to_hass(self):
        self._hub.register_callback(self.process_callback)

    async def async_will_remove_from_hass(self):
        self._hub.remove_callback(self.process_callback)

    async def process_callback(self, cbtype, value):
        self.async_write_ha_state()

    @property
    def available(self):
        return self._hub.is_available()

    @property
    def name(self):
        return self._name

    @property
    def should_poll(self):
        return False

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def is_on(self):
        return self.percentage is not None and self.percentage > 0

    @property
    def percentage(self):
        """Return the current speed percentage."""
        raw_value = self._hub.get_analog(self._speed_join)
        if raw_value == 0:
            return 0
        
        if self._speed_steps is not None:
            # Stepped control: find which step the analog value represents
            # Steps are evenly divided: step 1 = 65535/steps, step 2 = 2*65535/steps, etc.
            step_size = 65535 / self._speed_steps
            current_step = min(self._speed_steps, max(1, round(raw_value / step_size)))
            return int((current_step / self._speed_steps) * 100)
        else:
            # Stepless control: direct percentage mapping
            return max(1, min(100, int((raw_value / 65535) * 100)))

    @property
    def current_direction(self):
        """Return the current direction of the fan."""
        if self._reverse_join is None:
            return None
        return "reverse" if self._hub.get_digital(self._reverse_join) else "forward"

    async def async_set_percentage(self, percentage):
        """Set the speed percentage of the fan."""
        if percentage == 0:
            await self.async_turn_off()
            return
        
        if self._speed_steps is not None:
            # Stepped control: map percentage to discrete steps
            # Step 1 gets 65535/steps, step 2 gets 2*65535/steps, etc.
            step = max(1, min(self._speed_steps, round((percentage / 100) * self._speed_steps)))
            analog_value = int((step * 65535) / self._speed_steps)
        else:
            # Stepless control
            analog_value = int((percentage / 100) * 65535)
        
        self._hub.set_analog(self._speed_join, analog_value)

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs):
        """Turn on the fan."""
        if percentage is None:
            # Default to lowest speed
            if self._speed_steps is not None:
                percentage = int((1 / self._speed_steps) * 100)
            else:
                percentage = 1
        await self.async_set_percentage(percentage)

    async def async_turn_off(self, **kwargs):
        """Turn off the fan."""
        self._hub.set_analog(self._speed_join, 0)

    async def async_set_direction(self, direction):
        """Set the direction of the fan."""
        if self._reverse_join is None:
            return
        
        reverse_state = direction == "reverse"
        self._hub.set_digital(self._reverse_join, reverse_state)