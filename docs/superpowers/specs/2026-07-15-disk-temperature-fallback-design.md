# Disk Temperature Fallback Design

## Goal

Fix disk temperature reporting for disks, especially NVMe devices, that are
present in `Store.list_disks()` and have SMART temperature data but are absent
from `ResourceMonitor.disk()`.

The calculation semantics follow pyfnos
`tools/list_disk_temperatures.py` at commit
`8afa75644b28b4f9b122809aaafc0352c434cc11`.

## Constraints

- Do not add SDK or API calls.
- Do not change the coordinator refresh flow or response merging.
- Reuse the existing `data["resmon"]` and `data["smart"]` values.
- Keep `ResourceMonitor.disk()` temperature as the preferred low-cost source.
- Limit the change to disk temperature calculation and its tests.

## Temperature Resolution

Resolve the first valid value in this order:

1. `data["resmon"]["temp"]`
2. `data["smart"]["temperature"]["current"]`
3. `data["smart"]["nvme_smart_health_information_log"]["temperature"]`
4. `None` when no source contains a valid value

A temperature is valid only when it is an `int` or `float`, excluding
`bool`, is finite, and is not zero. Missing fields, malformed containers,
strings, booleans, zero, NaN, and infinite values must fall through to the
next source without raising an exception.

The SMART paths omit the outer SDK response key because the coordinator
already stores `smart_resp.get("smart")` in `data["smart"]`.

## Implementation Boundary

Add a small pure temperature extraction helper in the integration package and
call it from the `disk_temp` sensor description. Keeping this calculation free
of Home Assistant dependencies makes the pyfnos-compatible behavior directly
unit-testable.

Do not alter `FnosDiskCoordinator._async_retrieve_disk()`: it will continue to
call `Store.list_disks()`, `ResourceMonitor.disk()`, and the existing
`Store.get_disk_smart(name)` path exactly as it does today.

## Error Handling

The helper must tolerate `None`, missing keys, and non-dictionary intermediate
values. Invalid sources are skipped silently because a disk may legitimately
be absent from resource monitoring or SMART data may be unavailable while a
disk is in standby. When every source is invalid, returning `None` lets Home
Assistant represent the sensor state as unknown.

## Tests

Add focused unit tests covering:

- a valid resource-monitor temperature wins over SMART values;
- missing resource-monitor data falls back to normalized SMART temperature;
- invalid resource-monitor data, including zero, falls back to SMART;
- missing or invalid normalized SMART temperature falls back to the NVMe log;
- booleans, strings, NaN, and infinity are rejected;
- malformed or entirely missing data returns `None` without raising.

Run the new unit tests, the complete existing unit-test suite, and the
project's available lint or syntax checks before completion.
