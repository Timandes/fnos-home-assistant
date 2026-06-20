"""Tests for fnOS config flow authentication helpers."""

from pathlib import Path
import importlib.util
import json
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
AUTH_PATH = ROOT / "custom_components" / "fnos" / "auth.py"
CONFIG_FLOW_PATH = ROOT / "custom_components" / "fnos" / "config_flow.py"


def load_auth_module():
    """Load auth.py without importing the Home Assistant integration package."""
    spec = importlib.util.spec_from_file_location("fnos_auth_under_test", AUTH_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class AuthHelperTests(unittest.TestCase):
    """Authentication helper tests."""

    @classmethod
    def setUpClass(cls):
        cls.auth = load_auth_module()

    def test_classifies_final_login_success(self):
        result = self.auth.classify_login_response(
            {"result": "succ", "token": "token-value", "secret": "secret-value"}
        )

        self.assertEqual(result.status, self.auth.AuthStatus.SUCCESS)

    def test_classifies_twofa_required(self):
        result = self.auth.classify_login_response(
            {
                "result": "succ",
                "twofaRequired": True,
                "accessToken": "access-token",
            }
        )

        self.assertEqual(result.status, self.auth.AuthStatus.TWOFA_REQUIRED)

    def test_classifies_twofa_setup_required(self):
        result = self.auth.classify_login_response(
            {
                "result": "succ",
                "twofaSetupRequired": True,
                "accessToken": "access-token",
            }
        )

        self.assertEqual(result.status, self.auth.AuthStatus.TWOFA_SETUP_REQUIRED)

    def test_classifies_failed_login_as_invalid_auth(self):
        result = self.auth.classify_login_response(
            {"result": "fail", "msg": "invalid password"}
        )

        self.assertEqual(result.status, self.auth.AuthStatus.INVALID_AUTH)

    def test_classifies_unrecognized_login_response_as_unknown(self):
        result = self.auth.classify_login_response({"result": "succ"})

        self.assertEqual(result.status, self.auth.AuthStatus.UNKNOWN)

    def test_classifies_twofa_submit_success(self):
        result = self.auth.classify_twofa_response(
            {"result": "succ", "token": "token-value", "secret": "secret-value"}
        )

        self.assertEqual(result.status, self.auth.AuthStatus.SUCCESS)

    def test_classifies_twofa_submit_failure(self):
        result = self.auth.classify_twofa_response(
            {"result": "fail", "msg": "bad verification code"}
        )

        self.assertEqual(result.status, self.auth.AuthStatus.INVALID_TWOFA_CODE)

    def test_validates_six_digit_twofa_code(self):
        self.assertTrue(self.auth.is_valid_twofa_code("123456"))
        self.assertFalse(self.auth.is_valid_twofa_code("12345"))
        self.assertFalse(self.auth.is_valid_twofa_code("1234567"))
        self.assertFalse(self.auth.is_valid_twofa_code("12a456"))
        self.assertFalse(self.auth.is_valid_twofa_code(""))

    def test_auth_status_values_match_config_flow_error_keys(self):
        self.assertEqual(self.auth.AuthStatus.CANNOT_CONNECT.value, "cannot_connect")
        self.assertEqual(self.auth.AuthStatus.INVALID_AUTH.value, "invalid_auth")
        self.assertEqual(
            self.auth.AuthStatus.INVALID_TWOFA_CODE.value,
            "invalid_twofa_code",
        )
        self.assertEqual(
            self.auth.AuthStatus.TWOFA_SETUP_REQUIRED.value,
            "twofa_setup_required",
        )

    def test_twofa_required_status_is_not_an_error_key(self):
        self.assertEqual(
            self.auth.AuthStatus.TWOFA_REQUIRED.value,
            "twofa_required",
        )

    def test_config_flow_defines_twofa_step_and_trusts_device(self):
        text = CONFIG_FLOW_PATH.read_text(encoding="utf-8")

        self.assertIn("async def async_step_twofa", text)
        self.assertIn("STEP_TWOFA_DATA_SCHEMA", text)
        self.assertIn("submit_twofa_code(code)", text)
        self.assertIn("trust_device=True", text)

    def test_manifest_requires_pyfnos_0130(self):
        manifest_path = ROOT / "custom_components" / "fnos" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertIn("fnos>=0.13.0", manifest["requirements"])

    def test_translation_files_include_twofa_step_and_errors(self):
        translation_paths = [
            ROOT / "custom_components" / "fnos" / "strings.json",
            ROOT / "custom_components" / "fnos" / "translations" / "zh-Hans.json",
            ROOT / "custom_components" / "fnos" / "translations" / "en.json",
        ]

        for path in translation_paths:
            with self.subTest(path=path):
                data = json.loads(path.read_text(encoding="utf-8"))
                self.assertIn("twofa", data["config"]["step"])
                self.assertIn("invalid_twofa_code", data["config"]["error"])
                self.assertIn("twofa_setup_required", data["config"]["error"])


if __name__ == "__main__":
    unittest.main()
