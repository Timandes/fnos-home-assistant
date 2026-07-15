"""Disk temperature resolution tests."""

import ast
import math
from pathlib import Path
import runpy
import unittest


FNOS_ROOT = Path(__file__).resolve().parents[1]
TEMPERATURE_MODULE_PATH = FNOS_ROOT / "disk_temperature.py"
if TEMPERATURE_MODULE_PATH.exists():
    TEMPERATURE_MODULE = runpy.run_path(str(TEMPERATURE_MODULE_PATH))
    extract_disk_temperature = TEMPERATURE_MODULE[
        "extract_disk_temperature"
    ]
else:
    def extract_disk_temperature(_data):
        raise AssertionError("extract_disk_temperature is not implemented")


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
                if isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "STORAGE_DISK_SENSORS"
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


if __name__ == "__main__":
    unittest.main()
