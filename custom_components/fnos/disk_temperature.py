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
