# Development

Pump status, alerts, statistics, protection settings, and outlet control for the PumpFuse Sump Pump Monitor (PF-SUMP-001). Keep documentation minimal and never hard-wrap Markdown.

Targets the latest Home Assistant release only. `requires-python` and `.python-version` mirror Home Assistant's own, so raising one means raising the other.

```sh
uv sync --locked
uv run ruff format --diff .
uv run ruff check .
uv run mypy .
```

There are no tests. `mypy --strict` against the locked Home Assistant is the gate that catches API drift.

Run these locally before committing; neither is installed by `uv sync` or checked in CI.

```sh
uvx ssort .
uvx pyproject-fmt pyproject.toml
```

Sort functions in dependency order. Avoid superfluous comments and docstrings; only include them when they clarify complex logic.

## Device API

The monitor serves JSON at `http://<host>/api/v1/` with no authentication. Vendor docs: [REST API](https://www.pumpfuse.com/pfa01/products/sump/rest-api.html), [MQTT & Home Assistant](https://www.pumpfuse.com/pfa01/products/sump/mqtt-ha.html). The entities mirror the MQTT discovery set, replacing the two bitmask numbers with one switch per bit and the `sump/event` topic with an event entity fed from the history ring. The telemetry switch is omitted because it only drives MQTT streaming.

The HTTP server handles one request at a time, so requests run in sequence. Each poll reads only `status` and `sump/status` (about 25 ms). `info` (MAC check), `sump/learn`, and `sump/history` are reread every 60 s, after an error or command, and whenever the run count, alerts, protection mode, or lockout changes or uptime goes backwards. `sump/last-run` is read only when `last_run_end_ms` changes. Unknown paths return 404 and wrong methods return 405.

Real runs are about 12 s and can be a day or more apart, so the 5 s default exists to catch `pump_running`; counters and last-run details survive any interval. The vendor MQTT discovery maps Baseline power to `learn.wattage_mean`. On firmware 1.0.0 the MQTT `sump/state` heartbeat was observed frozen at its first retained payload, so REST is the more reliable source. Reset statistics clears `last_run_end_ms`, `inter_run_gap_mean`, and learn CVs to `null`.

Platform endpoints are undocumented but match the MCP `tools/list` at `POST /api/v1/mcp`: `GET info` (product, firmware, MAC), `GET config` (`device_name`), `GET status`, `GET`/`POST relay` with `{"relay": bool}`, `GET power`, and `GET telemetry`.

`POST sump/config` takes a partial body and rejects out-of-range values with a plain-text 400. Bits 0–4 of `alert_enable_mask` are low power, high power, long run, frequent cycling, and inactivity; bits 0–2 of `relay_cut_mask` are the first three.

The device does not advertise over mDNS and its DHCP hostname is derived from the user-set name, so discovery matches the Espressif MAC prefix and rejects anything whose `info.product` is not `sump`.
