# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-07-19

### Changed
- `set_param` and `set_mode` now pass through the actuation safety gate,
  matching arm/disarm. Previously only arm/disarm were gated; the README
  overstated the gating and this release makes the claim true.
- `ardupilot_set_mode` returns `command_sent` instead of `set`, reflecting
  that the mode change is requested, not confirmed via heartbeat.

### Added
- `set_param` rejects `ARMING_CHECK` writes (case-insensitive) on every link
  kind, even with `--enable-actuation` and `--allow-real-vehicle` set.
- Denial tests covering the gated write paths.

## [0.1.1] - 2026-07-14

### Fixed
- Removed the stale prerelease install note from the project description that
  PyPI preserves from the 0.1.0 release metadata.
- Kept package and MCP registry metadata aligned for the refresh release.

## [0.1.0] - 2026-06-22

First release. Published to PyPI (`ardupilot-mavlink-mcp`) and the MCP registry
(`io.github.rmeadomavic/ardupilot-mavlink-mcp`).

### Added
- v1 tool surface against ArduPilot SITL: `ardupilot_connect`,
  `ardupilot_vehicle_state`, `ardupilot_recent_statustext`,
  `ardupilot_get_param`/`set_param`/`list_params`, `ardupilot_set_mode`,
  gated `ardupilot_arm`/`disarm`, and an `ardupilot://telemetry` resource.
- Async-stream-to-sync-cache bridge: background recv thread, thread-safe
  message cache, STATUSTEXT ring buffer, request-then-collect param store.
- Safety gate: actuation off by default; real-vehicle actuation double-gated.
- Read tools carry MCP `readOnlyHint`; actuation tools carry `destructiveHint`.
- Validation harnesses: `scripts/wire_check.py` (offline real-MAVLink wire)
  and `scripts/sitl_check.py` (live ArduPilot SITL).

### Security
- Actuation refuses real (non-loopback/serial) links unless explicitly allowed;
  link classification fails safe toward "real". Arming respects vehicle safety
  checks — no force-arm, no `ARMING_CHECK` bypass.

[Unreleased]: https://github.com/rmeadomavic/ardupilot-mcp/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/rmeadomavic/ardupilot-mcp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/rmeadomavic/ardupilot-mcp/releases/tag/v0.1.0
