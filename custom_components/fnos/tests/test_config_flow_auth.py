"""Tests for fnOS config flow authentication helpers."""

from pathlib import Path
import importlib.util
import sys
import unittest


ROOT = Path(__file__).resolve().parents[3]
AUTH_PATH = ROOT / "custom_components" / "fnos" / "auth.py"


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


if __name__ == "__main__":
    unittest.main()
