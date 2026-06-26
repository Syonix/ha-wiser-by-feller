"""Constants for the Wiser by Feller integration."""

DOMAIN = "wiser_by_feller"
DEFAULT_API_USER = "homeassistant"
DEFAULT_IMPORT_USER = "admin"
MANUFACTURER = "Feller by Schneider Electric"
CONF_IMPORTUSER = "import_user"
# Marker stored when the import user is unknown (e.g. for entries created before
# the import user was persisted). Distinguishes "we don't know" from a real user.
IMPORT_USER_UNKNOWN = "<unknown>"
OPTIONS_ALLOW_MISSING_GATEWAY_DATA = "allow_missing_gateway_data"
HA_BLUE = "#1abcf2"
LED_OFF_COLOR = "#000000"
MIN_FIRMWARE_BUTTON_LED_OVERRIDE = (6, 0, 41)
MIN_FIRMWARE_MANAGED_BUTTONS = (6, 0, 42)
MIN_FIRMWARE_REFRESH_PROPERTIES = (6, 0, 40)

EVENT_BUTTON = f"{DOMAIN}_button_event"
