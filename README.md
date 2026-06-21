# mavlink-mcp

An [MCP](https://modelcontextprotocol.io) server that lets an agent talk to an
**ArduPilot** vehicle over **MAVLink** — read state, inspect/change parameters,
switch modes, and (gated, opt-in) arm/disarm.

**SITL-first.** The default target is ArduPilot SITL on loopback. Actuation is
**off by default** and refuses to touch a real vehicle unless you explicitly say
so. An agent should never arm hardware by accident.

> Status: v1 — read + param + mode + gated actuation against SITL. Mission
> upload/download and guided flight (takeoff/goto/land) are deferred to v2.

## Why

There's no maintained MAVLink/ArduPilot MCP server. The killer demo: connect an
agent to a vehicle, have it read params + prearm `STATUSTEXT`, and **diagnose a
no-arm** — a real field-instructor tool.

## Install

```bash
git clone <repo> mavlink-mcp && cd mavlink-mcp
uv venv --python 3.12
uv pip install -e ".[dev]"      # or: pip install -e .
```

## Quickstart against SITL

Start ArduPilot SITL (Linux / WSL / a companion box) and have it output to your
machine:

```bash
# in the ardupilot checkout
sim_vehicle.py -v ArduCopter --out=udp:127.0.0.1:14550 --console
```

Run the MCP server (defaults to `udp:127.0.0.1:14550`):

```bash
mavlink-mcp                       # read-only, SITL
mavlink-mcp --enable-actuation    # allow arm/disarm on SITL
```

> Native Windows can't easily run `sim_vehicle.py`. Run SITL on a Linux box (or
> a Jetson) and point `--connect` at its IP, or use a prebuilt SITL binary.

## Register with an MCP client

```jsonc
{
  "mcpServers": {
    "mavlink": {
      "command": "mavlink-mcp",
      "args": ["--connect", "udp:127.0.0.1:14550"]
    }
  }
}
```

## Tools

| Tool | What it does |
| --- | --- |
| `connect(conn_str)` | Connect to a vehicle. `udp:`, `tcp:`, `serial:`. Default SITL. |
| `vehicle_state()` | Mode, armed, GPS fix/sats, battery, attitude, position — from cache, instant. |
| `recent_statustext(n)` | Last n STATUSTEXT/prearm messages. The no-arm diagnostic goldmine. |
| `get_param(name)` | Read one parameter. |
| `set_param(name, value)` | Set a parameter, confirmed via echoed `PARAM_VALUE`. |
| `list_params(glob)` | List params, optional glob (`ATC_RAT_*`). |
| `set_mode(mode)` | Set flight mode by name (`GUIDED`, `RTL`, ...). |
| `arm()` / `disarm()` | **Gated.** Off unless `--enable-actuation`; real links also need `--allow-real-vehicle`. |

Live telemetry is also exposed as the resource `mavlink://telemetry`.

## Safety model

1. Actuation tools are **off by default**. Enable with `--enable-actuation`.
2. Even enabled, actuation on a **real** (non-loopback / serial) link is refused
   unless `--allow-real-vehicle` is also set.
3. Link classification fails safe: anything not clearly loopback is treated as a
   real vehicle.

## Architecture

MAVLink is an async stream; MCP tools are synchronous. A background thread owns
the link and is the only reader — it caches the latest message of each type and
routes `PARAM_VALUE` into a param store. Tool calls read from those caches (and,
for params, block until the requested data arrives). No two threads ever call
`recv_match`.

- `cache.py` — thread-safe latest-of-type + STATUSTEXT ring buffer
- `params.py` — request-then-collect param accumulator
- `safety.py` — link classifier + actuation gate
- `connection.py` — background recv thread tying it together
- `server.py` — FastMCP tool wiring + CLI

## Develop

```bash
pytest -q
ruff check . && ruff format --check .
```

## License

Apache-2.0.
