"""Constants for the FireBrick integration."""

from datetime import timedelta

DOMAIN = "firebrick"

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 10

MANUFACTURER = "FireBrick Ltd"

# Ignore uptime-derived "connected since" jitter smaller than this.
CONNECTED_SINCE_TOLERANCE = timedelta(seconds=5)
