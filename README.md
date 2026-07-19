# ardupilot-mcp

An [MCP](https://modelcontextprotocol.io) server that lets an AI agent talk to an ArduPilot vehicle over MAVLink. Read state, inspect and change parameters, switch modes, read prearm failures, and (gated) arm or disarm. SITL-first.

Install: `pipx install ardupilot-mavlink-mcp`

`mcp-name: io.github.rmeadomavic/ardupilot-mavlink-mcp`

![CI](https://github.com/rmeadomavic/ardupilot-mcp/actions/workflows/ci.yml/badge.svg)
[![PyPI](https://img.shields.io/pypi/v/ardupilot-mavlink-mcp)](https://pypi.org/project/ardupilot-mavlink-mcp/)
![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![MCP](https://img.shields.io/badge/MCP-server-2d3a2e)

> [!WARNING]
> **This tool can ARM and command a real aircraft.** A bad command can spin props or fly a vehicle away. Defaults are built to stop that: actuation is OFF unless you pass `--enable-actuation`, and even then it refuses a real (non-loopback) link unless you also pass `--allow-real-vehicle`. Develop against SITL. On hardware, bench-test with **props off** first. No warranty — you own the outcome.

## Why

Most ArduPilot tooling for LLMs targets post-flight log analysis. This one drives the **live link**: connect to a running vehicle, read its state and params, change modes, and diagnose why it won't arm — in the moment, not after landing. The useful case: point an agent at a vehicle that won't arm, have it read the params and the prearm `STATUSTEXT`, and tell you why, instead of you squinting at a GCS message log. The arm tool reports the real `COMMAND_ACK` result and hands back the prearm reasons on refusal; it never force-arms.

## Architecture

```
  agent (MCP client)                    ardupilot-mcp                     vehicle
 ┌──────────────────┐   JSON-RPC    ┌──────────────────────┐   MAVLink   ┌──────────┐
 │ Claude / etc.    │ ───stdio────▶ │  FastMCP tools       │ ──udp/tcp/  │ ArduPilot│
 │                  │ ◀───────────  │   │                  │   serial──▶ │  (SITL   │
 └──────────────────┘               │   ▼                  │ ◀────────── │  or FC)  │
                                    │  recv thread (1 reader)            └──────────┘
                                    │   ├─▶ message cache (latest/type)
                                    │   ├─▶ param store (request/collect)
                                    │   └─▶ COMMAND_ACK + STATUSTEXT
                                    └──────────────────────┘
```

MAVLink is an async stream; MCP tools are synchronous. One background thread owns the link and is the only reader — it caches the latest message of each type and routes `PARAM_VALUE` into a param store. Tool calls read from those caches (params block until the data arrives). No two threads ever call `recv_match`.

## What it does

- **Reads vehicle state from cache, instantly.** Mode, armed, GPS fix and sats, battery, attitude, position — served from cached telemetry, no blocking on the link.
- **Diagnoses a no-arm.** `ardupilot_arm` returns the `COMMAND_ACK` result and, on refusal, the prearm `STATUSTEXT` (e.g. `AHRS: waiting for home`, `Accels inconsistent`). Safety checks are respected — no `ARMING_CHECK=0`, no force-arm magic number.
- **Gets and sets parameters** on the real param table, with `set` confirmed by the echoed `PARAM_VALUE`.
- **Switches flight modes** by name, mapped per vehicle type (Copter/Rover/Plane/Sub) — not hardcoded numbers.

## Quick start (SITL)

You need an ArduPilot SITL instance. From an `ardupilot` checkout:

```bash
# starts ArduCopter SITL; serves MAVLink on tcp:127.0.0.1:5760
sim_vehicle.py -v ArduCopter --console
```

Install and run the server (read-only by default):

```bash
pipx install ardupilot-mavlink-mcp          # or: uv tool install ardupilot-mavlink-mcp
ardupilot-mavlink-mcp --connect tcp:127.0.0.1:5760
```

To allow parameter writes, mode changes, and arm/disarm against SITL, add `--enable-actuation`.

## Use with an MCP client

Claude Code:

```bash
claude mcp add ardupilot -- ardupilot-mavlink-mcp --connect tcp:127.0.0.1:5760
```

Claude Desktop / any `mcpServers` config:

```json
{
  "mcpServers": {
    "ardupilot": {
      "command": "ardupilot-mavlink-mcp",
      "args": ["--connect", "tcp:127.0.0.1:5760"]
    }
  }
}
```

Connection strings are pymavlink syntax: `tcp:127.0.0.1:5760` (SITL), `udp:127.0.0.1:14550`, `serial:/dev/ttyACM0:115200`.

## Tools

| Tool | Kind | What it does |
| --- | --- | --- |
| `ardupilot_connect` | — | Connect to a vehicle. Default is local SITL. |
| `ardupilot_vehicle_state` | read | Mode, armed, GPS, battery, attitude, position — from cache. |
| `ardupilot_recent_statustext` | read | Recent STATUSTEXT/prearm messages. Read this to see why arming failed. |
| `ardupilot_get_param` | read | Read one parameter. |
| `ardupilot_set_param` | write | Set a parameter, confirmed via echoed `PARAM_VALUE`. |
| `ardupilot_list_params` | read | List params, optional glob (`ATC_RAT_*`). |
| `ardupilot_set_mode` | write | Send a request to set flight mode by name. |
| `ardupilot_arm` / `ardupilot_disarm` | write | Gated. Confirmed via `COMMAND_ACK`. |

Write tools are gated and carry the MCP `destructiveHint`. Live telemetry is also exposed as the resource `ardupilot://telemetry`.

## Supported vehicles

| Vehicle | Firmware | Status |
| --- | --- | --- |
| ArduCopter | 4.5 | ✓ validated on SITL |
| ArduRover (UGV/USV) | 4.x | ~ mode map present, not yet validated |
| ArduPlane | 4.x | ~ mode map present, not yet validated |
| ArduSub | 4.x | ~ untested |

MAVLink2 is assumed. Not flown on hardware — SITL only so far.

## Safety model

1. Actuation tools are OFF by default. Enable with `--enable-actuation`.
2. Even enabled, actuation on a real link (serial or non-loopback network) is refused unless `--allow-real-vehicle` is also set.
3. Link classification fails safe: anything not clearly loopback is treated as a real vehicle.
4. `arm`, `disarm`, `set_param`, and `set_mode` all pass through this gate before sending.
5. Arming has no force-arm option, and `set_param` rejects `ARMING_CHECK` writes (case-insensitive) on every link, even when both actuation flags are enabled.

## Status

Working: reads plus gated parameter writes, mode changes, and arm/disarm against ArduCopter SITL. Validated three ways — unit tests (Python 3.10–3.12), a real-MAVLink-wire check (`scripts/wire_check.py`), and a live ArduPilot SITL run (`scripts/sitl_check.py`).

Open targets: validate Rover/Plane/Sub; mission upload/download and guided flight (takeoff/goto/land) are deferred — mission protocol is a stateful handshake and guided commands are fly-away risk. See [ROADMAP.md](ROADMAP.md).

## Develop

```bash
git clone https://github.com/rmeadomavic/ardupilot-mcp && cd ardupilot-mcp
uv venv && uv pip install -e ".[dev]"
pytest -q
ruff check . && ruff format --check .
python scripts/wire_check.py            # offline real-wire check, no SITL needed
```

## License

[MIT](LICENSE) — Kyle Adomavicius
