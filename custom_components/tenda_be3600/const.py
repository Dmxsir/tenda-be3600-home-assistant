"""Constants for the Tenda BE3600 integration."""

from homeassistant.const import Platform

DOMAIN = "tenda_be3600"
CONF_PASSWORD_DIGEST = "password_digest"
DEFAULT_HOST = "tendawifi.com"
UPDATE_INTERVAL = 30

PLATFORMS = (Platform.SENSOR, Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER)
