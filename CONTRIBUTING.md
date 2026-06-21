# Contributing

Thanks for looking. This tool talks to vehicles, so the bar is "does it still
behave safely," not just "do the tests pass."

## Setup

```bash
uv venv && uv pip install -e ".[dev]"
pytest -q
ruff check . && ruff format --check .
```

## Before you open a PR

- `pytest` green and `ruff` clean.
- If you touched the MAVLink/connection path (`connection.py`, `params.py`,
  `cache.py`), re-validate against a real link:
  - `python scripts/wire_check.py` — offline, no SITL needed.
  - `python scripts/sitl_check.py` — against ArduPilot SITL on `tcp:5760`.
- New behavior gets a test. Tests that assert on a mock instead of the code
  under test will be sent back.

## Highest-value contributions right now

- Validating Rover/Plane/Sub against their SITL models and reporting what
  breaks (mode names, param differences, arming behavior).
- Real-hardware reports — what worked, what didn't, with logs. "Tested on
  SITL" is honest; "works on a Cube" needs evidence.

## Safety rules (non-negotiable)

- No force-arm, no `ARMING_CHECK=0`, no tool that bypasses prearm checks.
- Actuation stays off by default and double-gated on real links. Don't loosen
  the gate to make a demo easier.
- If a change could move a real vehicle, say so in the PR's Risk section.

## Style

Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`). Keep
subjects terse and say why the change matters.
