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
