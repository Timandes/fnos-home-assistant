# Disk Temperature Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Report disk temperature from the existing resource-monitor data when valid, then fall back to the already-fetched normalized SMART or NVMe SMART temperature without adding API calls.

**Architecture:** Add a pure `extract_disk_temperature(data)` helper that mirrors the value validation and source priority in pyfnos `tools/list_disk_temperatures.py`. Keep the coordinator unchanged and make the existing `disk_temp` sensor call the helper with its already-merged `resmon` and `smart` dictionaries.

**Tech Stack:** Python 3.12, standard-library `math`, Home Assistant sensor descriptions, `unittest`, AST-based wiring verification.

## Global Constraints

- Do not add SDK or API calls.
- Do not change the coordinator refresh flow or response merging.
- Reuse the existing `data["resmon"]` and `data["smart"]` values.
- Keep `ResourceMonitor.disk()` temperature as the preferred low-cost source.
- Resolve valid values in this exact order: `resmon.temp`, `smart.temperature.current`, `smart.nvme_smart_health_information_log.temperature`, then `None`.
- Reject missing values, malformed containers, strings, booleans, zero, NaN, and infinity; accept finite non-zero `int` and `float` values.
- Do not add runtime dependencies.
- Use Angular/Conventional Commits with English commit messages and never include `Co-Authored-By`.
- Run every command from `/Users/timandes/Projects/fnos/fnos-home-assistant/.worktrees/bugfix-disk-temperature-fallback`.

---

### Task 1: Pure Disk Temperature Resolver

**Files:**
- Create: `custom_components/fnos/disk_temperature.py`
- Create: `custom_components/fnos/tests/test_disk_temperature.py`

**Interfaces:**
- Consumes: the existing merged disk value as `data: object`, with optional nested `resmon` and `smart` dictionaries.
- Produces: `extract_disk_temperature(data: object) -> int | float | None` for the sensor wiring in Task 2.

- [ ] **Step 1: Write the failing resolver tests**

Create `custom_components/fnos/tests/test_disk_temperature.py` with this complete content. `runpy.run_path()` deliberately loads the pure module by file path so the test does not execute `custom_components.fnos.__init__` or require Home Assistant to be installed.

```python
"""Disk temperature resolution tests."""

import math
from pathlib import Path
import runpy
import unittest


FNOS_ROOT = Path(__file__).resolve().parents[1]
TEMPERATURE_MODULE = runpy.run_path(
    str(FNOS_ROOT / "disk_temperature.py")
)
extract_disk_temperature = TEMPERATURE_MODULE["extract_disk_temperature"]


class DiskTemperatureTests(unittest.TestCase):
    """Verify pyfnos-compatible disk temperature resolution."""

    def test_resmon_temperature_wins(self):
        data = {
            "resmon": {"temp": 33},
            "smart": {
                "temperature": {"current": 36},
                "nvme_smart_health_information_log": {"temperature": 41},
            },
        }

        self.assertEqual(33, extract_disk_temperature(data))

    def test_missing_resmon_falls_back_to_smart_temperature(self):
        data = {
            "resmon": None,
            "smart": {"temperature": {"current": 36}},
        }

        self.assertEqual(36, extract_disk_temperature(data))

    def test_zero_resmon_falls_back_to_smart_temperature(self):
        data = {
            "resmon": {"temp": 0},
            "smart": {"temperature": {"current": 37}},
        }

        self.assertEqual(37, extract_disk_temperature(data))

    def test_invalid_smart_temperature_falls_back_to_nvme_log(self):
        data = {
            "resmon": {},
            "smart": {
                "temperature": {"current": None},
                "nvme_smart_health_information_log": {"temperature": 41},
            },
        }

        self.assertEqual(41, extract_disk_temperature(data))

    def test_invalid_values_fall_through_to_next_source(self):
        for invalid in (True, "32", math.nan, math.inf, -math.inf):
            with self.subTest(invalid=invalid):
                data = {
                    "resmon": {"temp": invalid},
                    "smart": {"temperature": {"current": 32}},
                }

                self.assertEqual(32, extract_disk_temperature(data))

    def test_finite_negative_temperature_is_valid(self):
        self.assertEqual(
            -5,
            extract_disk_temperature({"resmon": {"temp": -5}}),
        )

    def test_malformed_or_missing_data_returns_none(self):
        cases = (
            None,
            {},
            {"resmon": None, "smart": None},
            {
                "resmon": [],
                "smart": {
                    "temperature": "invalid",
                    "nvme_smart_health_information_log": [],
                },
            },
            {
                "resmon": {"temp": False},
                "smart": {
                    "temperature": {"current": 0},
                    "nvme_smart_health_information_log": {
                        "temperature": math.nan
                    },
                },
            },
        )

        for data in cases:
            with self.subTest(data=data):
                self.assertIsNone(extract_disk_temperature(data))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the focused tests and verify the red state**

Run:

```bash
uv run --python 3.12 --no-project python -m unittest discover \
  custom_components/fnos/tests -p 'test_disk_temperature.py'
```

Expected: `ERROR` while importing `test_disk_temperature` with `FileNotFoundError` for `custom_components/fnos/disk_temperature.py`; no production code exists yet.

- [ ] **Step 3: Implement the minimal pure resolver**

Create `custom_components/fnos/disk_temperature.py` with this complete content:

```python
"""Disk temperature resolution helpers."""
from __future__ import annotations

import math


_TEMPERATURE_PATHS = (
    ("resmon", "temp"),
    ("smart", "temperature", "current"),
    ("smart", "nvme_smart_health_information_log", "temperature"),
)


def _get_nested(mapping: object, *keys: str) -> object:
    """Return a nested value, or None when a path is malformed or missing."""
    current = mapping
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def _is_valid_temperature(value: object) -> bool:
    """Return whether a value matches pyfnos temperature semantics."""
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and value != 0
    )


def extract_disk_temperature(data: object) -> int | float | None:
    """Return the first valid temperature from existing disk data."""
    for path in _TEMPERATURE_PATHS:
        temperature = _get_nested(data, *path)
        if _is_valid_temperature(temperature):
            return temperature
    return None
```

- [ ] **Step 4: Run the focused tests and verify the green state**

Run:

```bash
uv run --python 3.12 --no-project python -m unittest discover \
  custom_components/fnos/tests -p 'test_disk_temperature.py'
```

Expected: `Ran 7 tests` and `OK`.

- [ ] **Step 5: Commit the resolver and its tests**

```bash
git add custom_components/fnos/disk_temperature.py \
  custom_components/fnos/tests/test_disk_temperature.py
git diff --cached --check
git commit -m "fix: add disk temperature resolver"
```

Expected: one commit containing only the pure resolver and its seven behavioral tests, with no `Co-Authored-By` trailer.

---

### Task 2: Connect the Disk Temperature Sensor

**Files:**
- Modify: `custom_components/fnos/tests/test_disk_temperature.py`
- Modify: `custom_components/fnos/sensor.py:30-38,265-275`

**Interfaces:**
- Consumes: `extract_disk_temperature(data: object) -> int | float | None` from Task 1.
- Produces: the existing `disk_temp` sensor description calling the resolver with the coordinator's already-merged disk data.

- [ ] **Step 1: Write the failing sensor-wiring test**

In `custom_components/fnos/tests/test_disk_temperature.py`, add `import ast` before `import math`, then add this class immediately before the existing `if __name__ == "__main__":` block:

```python
class DiskTemperatureSensorWiringTests(unittest.TestCase):
    """Verify the Home Assistant sensor delegates to the pure resolver."""

    def test_disk_temperature_sensor_uses_resolver(self):
        source = (FNOS_ROOT / "sensor.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        imports_resolver = any(
            isinstance(node, ast.ImportFrom)
            and node.level == 1
            and node.module == "disk_temperature"
            and any(
                alias.name == "extract_disk_temperature"
                for alias in node.names
            )
            for node in tree.body
        )
        self.assertTrue(
            imports_resolver,
            "sensor.py must import extract_disk_temperature",
        )

        storage_assignment = next(
            (
                node
                for node in tree.body
                if isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name)
                    and target.id == "STORAGE_DISK_SENSORS"
                    for target in node.targets
                )
            ),
            None,
        )
        self.assertIsNotNone(storage_assignment)

        disk_temp_keywords = None
        for node in ast.walk(storage_assignment.value):
            if not isinstance(node, ast.Call):
                continue
            keywords = {
                keyword.arg: keyword.value
                for keyword in node.keywords
                if keyword.arg is not None
            }
            key = keywords.get("key")
            if isinstance(key, ast.Constant) and key.value == "disk_temp":
                disk_temp_keywords = keywords
                break

        self.assertIsNotNone(disk_temp_keywords)
        value_fn = disk_temp_keywords.get("value_fn")
        self.assertIsInstance(value_fn, ast.Lambda)
        self.assertEqual(
            "extract_disk_temperature(data)",
            ast.unparse(value_fn.body),
        )
```

- [ ] **Step 2: Run the focused tests and verify the wiring failure**

Run:

```bash
uv run --python 3.12 --no-project python -m unittest discover \
  custom_components/fnos/tests -p 'test_disk_temperature.py'
```

Expected: `Ran 8 tests` and `FAILED (failures=1)` with `sensor.py must import extract_disk_temperature`.

- [ ] **Step 3: Import and call the resolver from the existing sensor**

In `custom_components/fnos/sensor.py`, add the local import after the coordinator import:

```python
from .coordinator import FnosSystemCoordinator, FnosDiskCoordinator
from .disk_temperature import extract_disk_temperature
```

Replace only the `disk_temp` description's `value_fn` with:

```python
        value_fn=lambda entity, data: extract_disk_temperature(data)
```

Do not modify `custom_components/fnos/coordinator.py`; its existing calls and merged `resmon`/`smart` data remain unchanged.

- [ ] **Step 4: Run the focused tests and verify the sensor wiring**

Run:

```bash
uv run --python 3.12 --no-project python -m unittest discover \
  custom_components/fnos/tests -p 'test_disk_temperature.py'
```

Expected: `Ran 8 tests` and `OK`.

- [ ] **Step 5: Run the full regression and syntax checks**

Run:

```bash
uv run --python 3.12 --no-project python -m unittest discover \
  custom_components/fnos/tests
uv run --python 3.12 --no-project python -m compileall -q \
  custom_components/fnos
git diff --check
```

Expected: `Ran 35 tests` and `OK`; `compileall` and `git diff --check` exit with status 0 and no error output.

- [ ] **Step 6: Confirm the API chain is untouched**

Run:

```bash
git diff 04639d4 -- custom_components/fnos/coordinator.py
git diff --stat 04639d4 -- custom_components/fnos
```

Expected: the coordinator diff is empty; the stat lists only `disk_temperature.py`, `sensor.py`, and `test_disk_temperature.py`.

- [ ] **Step 7: Commit the sensor integration**

```bash
git add custom_components/fnos/sensor.py \
  custom_components/fnos/tests/test_disk_temperature.py
git diff --cached --check
git commit -m "fix: fall back to smart disk temperature"
```

Expected: one commit wiring the existing sensor to the tested resolver, with no coordinator change and no `Co-Authored-By` trailer.
