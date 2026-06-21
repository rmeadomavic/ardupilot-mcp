# Roadmap

Priority-bucketed. Subject to change as real use surfaces what matters.

## In progress
- Validate Rover/Plane/Sub against their SITL models (Copter is validated).

## High
- Mission download (read waypoints) — read-only, lower risk than upload.
- `MAV_CMD_SET_MESSAGE_INTERVAL` (511) for telemetry rates, replacing the
  current `REQUEST_DATA_STREAM` nudge.
- Publish to PyPI so `uvx ardupilot-mcp` works without a clone, plus a
  `server.json` entry in the MCP registry.

## Medium
- EKF/GPS/home readiness surfaced in `vehicle_state` (not just an armable bool).
- Dedicated source sysid/component so the server doesn't collide with a real
  GCS on a shared link.
- A short asciinema/GIF of the no-arm diagnosis flow.

## Low / later
- Mission upload (stateful handshake — fiddly, easy to get wrong).
- Guided flight (takeoff/goto/land) — fly-away risk; needs a hard real-vehicle
  gate and a lot of SITL soak time before it ships.

## Non-goals
- Force-arm / `ARMING_CHECK` bypass. Not happening.
- Becoming a full GCS. This is an agent's hands on a vehicle, not a ground
  station.
