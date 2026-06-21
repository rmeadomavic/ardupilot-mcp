# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- v1 tool surface scaffolded against SITL: `connect`, `vehicle_state`,
  `recent_statustext`, `get_param`/`set_param`/`list_params`, `set_mode`,
  gated `arm`/`disarm`, and a `mavlink://telemetry` resource.
- Async-stream-to-sync-cache bridge: background recv thread, thread-safe
  message cache, STATUSTEXT ring buffer, request-then-collect param store.
- Safety gate: actuation off by default; real-vehicle actuation double-gated.

### Changed
-

### Fixed
-

### Security
- Actuation refuses real (non-loopback/serial) links unless explicitly allowed;
  link classification fails safe toward "real".

## [0.1.0] - 2026-06-21

### Added
- Initial scaffold.
