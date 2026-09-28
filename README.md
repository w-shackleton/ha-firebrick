# FireBrick for Home Assistant

> [!WARNING]
> This integration is AI-generated code, written with Claude Code. It has been tested against one FB2900 but has not had a thorough human review. Check it yourself before relying on it.

A custom integration that polls a FireBrick router (developed against an FB2900 on firmware V2.06.029) over its web interface. It provides:

| Source | Entities |
|---|---|
| `/status/ports/.xml` | Per port: link (on/off), link speed, receive/transmit rate, data received/transmitted |
| `/status/pppoe/xml` | Per PPPoE session: connected, connected since, IPv4 (and IPv6, disabled by default) |
| `/cqm/<graph>.json` | Per CQM graph: receive/transmit rate, data totals; for graphs that ping, latency (min/avg/max) and packet loss |

Rates are calculated from byte-counter deltas between polls (default every 30 s; this is configurable in the integration's options). New ports, sessions and CQM graphs are picked up automatically.

CQM latency and loss update when the FireBrick closes each 100 s sample. The throughput figures use the live counters.

## Router setup

Create a FireBrick user with view-only rights, and set its `allow` list to include Home Assistant's IP address. The integration uses HTTP Basic auth. When credentials are wrong, the FireBrick redirects to `/login/`, and Home Assistant then asks you to reauthenticate.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements_dev.txt

# Run the tests
.venv/bin/pytest

# Run a local Home Assistant with the integration loaded
mkdir -p config/custom_components
ln -sfn ../../custom_components/firebrick config/custom_components/firebrick
.venv/bin/hass -c config
```

Open http://localhost:8123, finish onboarding, then go to **Settings → Devices & services → Add integration → FireBrick**.

`tests/fixtures/` holds real responses captured from the router. Refresh them with `curl --user USER:PASS https://<firebrick>/status/ports/.xml` and so on.

## Installing on a real Home Assistant

Copy `custom_components/firebrick` into the `custom_components/` folder of your Home Assistant config directory and restart.
