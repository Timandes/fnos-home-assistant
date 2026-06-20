# fnOS 2FA Login Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add fnOS two-factor authentication support to the Home Assistant config flow using `fnos>=0.13.0`, prompting for a 6-digit code and submitting it with trusted-device enabled.

**Architecture:** Keep runtime entity/coordinator behavior unchanged. Add a small pure-Python auth classification helper that can be tested without Home Assistant, then wire the existing config flow into a two-step `user` -> `twofa` login flow backed by a temporary `FnosClient`.

**Tech Stack:** Home Assistant config flow, Python async, voluptuous schemas, pyfnos `FnosClient.login()` and `FnosClient.submit_twofa_code()`, unittest.

---

## File Structure

- Create `custom_components/fnos/auth.py`
  - Owns pure authentication response classification and 2FA code validation.
  - Has no Home Assistant imports and no pyfnos imports so it is easy to unit test.

- Create `custom_components/fnos/tests/test_config_flow_auth.py`
  - Loads `auth.py` directly with `importlib.util.spec_from_file_location`.
  - Tests response classification and code validation without importing Home Assistant.

- Modify `custom_components/fnos/config_flow.py`
  - Uses `auth.py` helper results.
  - Replaces single-step boolean validation with `user` and `twofa` steps.
  - Keeps temporary `FnosHub` on the flow instance while waiting for the code.

- Modify `custom_components/fnos/manifest.json`
  - Raises dependency from `fnos>=0.10.1` to `fnos>=0.13.0`.

- Modify `custom_components/fnos/strings.json`
  - Adds the `twofa` step and new error keys.

- Modify `custom_components/fnos/translations/zh-Hans.json`
  - Adds Chinese 2FA labels and error text.

- Modify `custom_components/fnos/translations/en.json`
  - Adds English 2FA labels and error text.

- Modify `README.md`
  - Documents two-factor login support, trusted-device behavior, setup-required limitation, and the pyfnos dependency requirement.

## Task 1: Add Auth Classification Helper

**Files:**
- Create: `custom_components/fnos/auth.py`
- Test: `custom_components/fnos/tests/test_config_flow_auth.py`

- [ ] **Step 1: Write failing tests for login response classification**

Create `custom_components/fnos/tests/test_config_flow_auth.py` with:

```python
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
```

- [ ] **Step 2: Run tests and verify they fail because `auth.py` does not exist**

Run:

```bash
python3 custom_components/fnos/tests/test_config_flow_auth.py
```

Expected:

```text
FileNotFoundError
```

- [ ] **Step 3: Implement `auth.py`**

Create `custom_components/fnos/auth.py`:

```python
"""Authentication helpers for the fnOS config flow."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Optional


class AuthStatus(Enum):
    """Authentication status values used by the config flow."""

    SUCCESS = "success"
    TWOFA_REQUIRED = "twofa_required"
    TWOFA_SETUP_REQUIRED = "twofa_setup_required"
    INVALID_AUTH = "invalid_auth"
    INVALID_TWOFA_CODE = "invalid_twofa_code"
    CANNOT_CONNECT = "cannot_connect"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AuthResult:
    """Classified authentication result."""

    status: AuthStatus
    response: Optional[dict[str, Any]] = None


def _is_final_login_success(response: dict[str, Any]) -> bool:
    """Return True when fnOS returned final login credentials."""
    return (
        response.get("result") == "succ"
        and bool(response.get("token"))
        and bool(response.get("secret"))
    )


def classify_login_response(response: dict[str, Any]) -> AuthResult:
    """Classify a pyfnos username/password login response."""
    if _is_final_login_success(response):
        return AuthResult(AuthStatus.SUCCESS, response)

    if response.get("twofaRequired") is True:
        return AuthResult(AuthStatus.TWOFA_REQUIRED, response)

    if response.get("twofaSetupRequired") is True:
        return AuthResult(AuthStatus.TWOFA_SETUP_REQUIRED, response)

    if response.get("result") == "fail":
        return AuthResult(AuthStatus.INVALID_AUTH, response)

    return AuthResult(AuthStatus.UNKNOWN, response)


def classify_twofa_response(response: dict[str, Any]) -> AuthResult:
    """Classify a pyfnos 2FA verification response."""
    if _is_final_login_success(response):
        return AuthResult(AuthStatus.SUCCESS, response)

    if response.get("result") == "fail":
        return AuthResult(AuthStatus.INVALID_TWOFA_CODE, response)

    return AuthResult(AuthStatus.UNKNOWN, response)


def is_valid_twofa_code(code: str) -> bool:
    """Return True when the code is exactly six digits."""
    return re.fullmatch(r"\d{6}", code) is not None
```

- [ ] **Step 4: Run auth helper tests and verify they pass**

Run:

```bash
python3 custom_components/fnos/tests/test_config_flow_auth.py
```

Expected:

```text
Ran 8 tests

OK
```

- [ ] **Step 5: Commit helper and tests**

Run:

```bash
git add custom_components/fnos/auth.py custom_components/fnos/tests/test_config_flow_auth.py
git commit -m "test: cover fnOS auth result classification"
```

## Task 2: Refactor Config Flow For Structured Login Results

**Files:**
- Modify: `custom_components/fnos/config_flow.py`
- Test: `custom_components/fnos/tests/test_config_flow_auth.py`

- [ ] **Step 1: Add tests for connection and 2FA validation behavior in the helper layer**

Append these tests to `AuthHelperTests` in `custom_components/fnos/tests/test_config_flow_auth.py`:

```python
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
```

- [ ] **Step 2: Run helper tests**

Run:

```bash
python3 custom_components/fnos/tests/test_config_flow_auth.py
```

Expected:

```text
Ran 10 tests

OK
```

- [ ] **Step 3: Replace imports and schemas in `config_flow.py`**

In `custom_components/fnos/config_flow.py`, add `CONF_2FA_CODE` and the helper imports near the existing imports:

```python
from .auth import (
    AuthResult,
    AuthStatus,
    classify_login_response,
    classify_twofa_response,
    is_valid_twofa_code,
)
```

Add constants and the 2FA schema below `_LOGGER`:

```python
CONF_2FA_CODE = "code"

STEP_TWOFA_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_2FA_CODE): str,
    }
)
```

Keep `STEP_USER_DATA_SCHEMA` unchanged.

- [ ] **Step 4: Replace `FnosHub` authentication methods**

Replace the existing `FnosHub.authenticate()` and `disconnect()` methods with:

```python
    async def login(self, username: str, password: str) -> AuthResult:
        """Connect to fnOS and perform username/password login."""
        try:
            # pylint: disable=import-outside-toplevel
            from fnos import FnosClient

            self._client = FnosClient()
            await self._client.connect(self.host)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _LOGGER.warning("Cannot connect to fnOS host %s: %s", self.host, exc)
            return AuthResult(AuthStatus.CANNOT_CONNECT)

        try:
            response = await self._client.login(username, password)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _LOGGER.warning("fnOS login failed for host %s: %s", self.host, exc)
            return AuthResult(AuthStatus.UNKNOWN)

        return classify_login_response(response)

    async def submit_twofa_code(self, code: str) -> AuthResult:
        """Submit a 2FA code and request trusted-device status."""
        if not self._client:
            return AuthResult(AuthStatus.CANNOT_CONNECT)

        try:
            response = await self._client.submit_twofa_code(
                code,
                trust_device=True,
            )
        except ValueError:
            return AuthResult(AuthStatus.INVALID_TWOFA_CODE)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            _LOGGER.warning("fnOS two-factor verification failed for host %s: %s", self.host, exc)
            return AuthResult(AuthStatus.UNKNOWN)

        return classify_twofa_response(response)

    async def close(self) -> None:
        """Close the temporary fnOS client."""
        if not self._client:
            return

        close = getattr(self._client, "close", None)
        if close:
            await close()
            return

        disconnect = getattr(self._client, "disconnect", None)
        if disconnect:
            await disconnect()
```

Remove `validate_input()` because the config flow will now branch on `AuthResult`.

- [ ] **Step 5: Add pending state and entry helpers to `FnosConfigFlow`**

Inside `FnosConfigFlow`, below `VERSION = 1`, add:

```python
    def __init__(self) -> None:
        """Initialize the config flow."""
        self._pending_hub: FnosHub | None = None
        self._pending_user_input: dict[str, Any] | None = None

    def _create_entry_from_user_input(
        self,
        user_input: dict[str, Any],
    ) -> ConfigFlowResult:
        """Create a config entry from validated user input."""
        host = user_input[CONF_HOST]
        friendly_name = user_input.get(CONF_NAME)
        return self.async_create_entry(
            title=friendly_name or host,
            data=user_input,
        )

    async def _clear_pending_hub(self) -> None:
        """Close and clear any pending authentication client."""
        if self._pending_hub:
            await self._pending_hub.close()
        self._pending_hub = None
```

- [ ] **Step 6: Rewrite `async_step_user`**

Replace the body of `async_step_user` with:

```python
        errors: dict[str, str] = {}
        if user_input is not None:
            await self._clear_pending_hub()

            hub = FnosHub(user_input[CONF_HOST])
            result = await hub.login(
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )

            if result.status == AuthStatus.SUCCESS:
                await hub.close()
                return self._create_entry_from_user_input(user_input)

            if result.status == AuthStatus.TWOFA_REQUIRED:
                self._pending_hub = hub
                self._pending_user_input = dict(user_input)
                return await self.async_step_twofa()

            await hub.close()
            if result.status in {
                AuthStatus.CANNOT_CONNECT,
                AuthStatus.INVALID_AUTH,
                AuthStatus.TWOFA_SETUP_REQUIRED,
            }:
                errors["base"] = result.status.value
            else:
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
```

- [ ] **Step 7: Add `async_step_twofa`**

Add this method to `FnosConfigFlow` after `async_step_user`:

```python
    async def async_step_twofa(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle the two-factor authentication step."""
        errors: dict[str, str] = {}

        if self._pending_hub is None or self._pending_user_input is None:
            return await self.async_step_user()

        if user_input is not None:
            code = user_input[CONF_2FA_CODE]
            if not is_valid_twofa_code(code):
                errors["base"] = "invalid_twofa_code"
            else:
                result = await self._pending_hub.submit_twofa_code(code)
                if result.status == AuthStatus.SUCCESS:
                    entry_input = self._pending_user_input
                    await self._clear_pending_hub()
                    self._pending_user_input = None
                    return self._create_entry_from_user_input(entry_input)

                if result.status == AuthStatus.INVALID_TWOFA_CODE:
                    errors["base"] = "invalid_twofa_code"
                elif result.status == AuthStatus.CANNOT_CONNECT:
                    errors["base"] = "cannot_connect"
                else:
                    errors["base"] = "unknown"

        return self.async_show_form(
            step_id="twofa",
            data_schema=STEP_TWOFA_DATA_SCHEMA,
            errors=errors,
        )
```

- [ ] **Step 8: Run syntax check with Python 3.12 or newer**

Run:

```bash
python3.12 -m py_compile custom_components/fnos/auth.py custom_components/fnos/config_flow.py
```

Expected:

```text
no output
```

If `python3.12` is not installed, run the same command in the Home Assistant development Python environment that supports the repository's `type FnosConfigEntry = ...` syntax.

- [ ] **Step 9: Run helper tests**

Run:

```bash
python3 custom_components/fnos/tests/test_config_flow_auth.py
```

Expected:

```text
Ran 10 tests

OK
```

- [ ] **Step 10: Commit config flow refactor**

Run:

```bash
git add custom_components/fnos/auth.py custom_components/fnos/config_flow.py custom_components/fnos/tests/test_config_flow_auth.py
git commit -m "feat: support fnOS two-factor config flow"
```

## Task 3: Update Manifest And Translation Metadata

**Files:**
- Modify: `custom_components/fnos/manifest.json`
- Modify: `custom_components/fnos/strings.json`
- Modify: `custom_components/fnos/translations/zh-Hans.json`
- Modify: `custom_components/fnos/translations/en.json`
- Test: `custom_components/fnos/tests/test_config_flow_auth.py`

- [ ] **Step 1: Add metadata tests**

Append these tests to `AuthHelperTests`:

```python
    def test_manifest_requires_pyfnos_0130(self):
        import json

        manifest_path = ROOT / "custom_components" / "fnos" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertIn("fnos>=0.13.0", manifest["requirements"])

    def test_translation_files_include_twofa_step_and_errors(self):
        import json

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
```

- [ ] **Step 2: Run tests and verify metadata checks fail**

Run:

```bash
python3 custom_components/fnos/tests/test_config_flow_auth.py
```

Expected:

```text
FAIL: test_manifest_requires_pyfnos_0130
FAIL: test_translation_files_include_twofa_step_and_errors
```

- [ ] **Step 3: Update `manifest.json`**

Change:

```json
"requirements": ["fnos>=0.10.1"],
```

to:

```json
"requirements": ["fnos>=0.13.0"],
```

- [ ] **Step 4: Update `strings.json`**

In `custom_components/fnos/strings.json`, add `twofa` under `config.step` and add two error keys:

```json
"twofa": {
  "title": "Enter two-factor code",
  "description": "This fnOS account requires two-factor authentication. Enter the 6-digit code from your authenticator app. Home Assistant will ask fnOS to trust this device after submitting the code.",
  "data": {
    "code": "Code"
  },
  "data_description": {
    "code": "6-digit verification code"
  }
}
```

Add to `config.error`:

```json
"invalid_twofa_code": "The verification code is invalid or expired. Try again.",
"twofa_setup_required": "This account is required to use two-factor authentication, but no authenticator is bound yet. Set it up in the fnOS web UI first."
```

- [ ] **Step 5: Update `translations/zh-Hans.json`**

In `custom_components/fnos/translations/zh-Hans.json`, add:

```json
"twofa": {
  "title": "输入双重验证验证码",
  "description": "该 fnOS 账号需要双重验证。请输入身份验证器应用中的 6 位验证码。提交后，Home Assistant 会请求 fnOS 信任此设备，以减少后续验证码要求。",
  "data": {
    "code": "验证码"
  },
  "data_description": {
    "code": "6 位数字验证码"
  }
}
```

Add to `config.error`:

```json
"invalid_twofa_code": "验证码无效或已过期，请重新输入。",
"twofa_setup_required": "该账号被要求启用双重验证，但尚未绑定验证器。请先在 fnOS Web 端完成双重验证设置。"
```

If `config.error` does not exist in the file, create it as a sibling of `config.step` and `config.abort`.

- [ ] **Step 6: Update `translations/en.json`**

In `custom_components/fnos/translations/en.json`, add:

```json
"twofa": {
  "title": "Enter two-factor code",
  "description": "This fnOS account requires two-factor authentication. Enter the 6-digit code from your authenticator app. Home Assistant will ask fnOS to trust this device after submitting the code.",
  "data": {
    "code": "Code"
  },
  "data_description": {
    "code": "6-digit verification code"
  }
}
```

Add to `config.error`:

```json
"invalid_twofa_code": "The verification code is invalid or expired. Try again.",
"twofa_setup_required": "This account is required to use two-factor authentication, but no authenticator is bound yet. Set it up in the fnOS web UI first."
```

If `config.error` does not exist in the file, create it as a sibling of `config.step` and `config.abort`.

- [ ] **Step 7: Validate JSON and run metadata tests**

Run:

```bash
python3 -m json.tool custom_components/fnos/manifest.json >/dev/null
python3 -m json.tool custom_components/fnos/strings.json >/dev/null
python3 -m json.tool custom_components/fnos/translations/zh-Hans.json >/dev/null
python3 -m json.tool custom_components/fnos/translations/en.json >/dev/null
python3 custom_components/fnos/tests/test_config_flow_auth.py
```

Expected:

```text
Ran 12 tests

OK
```

- [ ] **Step 8: Commit metadata updates**

Run:

```bash
git add custom_components/fnos/manifest.json custom_components/fnos/strings.json custom_components/fnos/translations/zh-Hans.json custom_components/fnos/translations/en.json custom_components/fnos/tests/test_config_flow_auth.py
git commit -m "feat: add fnOS 2FA config flow text"
```

## Task 4: Document 2FA Login Behavior

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add README text under the login configuration section**

In `README.md`, under the existing `### 登录` section after the sentence that says the account must be a fnOS system administrator account, add:

```markdown
### 双重验证（2FA）

从集成依赖 `fnos>=0.13.0` 开始，配置流程支持已绑定双重验证的 fnOS 账号。输入用户名和密码后，如果 fnOS 要求双重验证，Home Assistant 会继续提示输入身份验证器应用中的 6 位验证码。

提交验证码时，集成会请求 fnOS 信任当前 Home Assistant 设备，以减少后续验证码要求。是否后续免验证码由 fnOS 服务端决定。

如果 fnOS 提示该账号被要求启用双重验证但尚未绑定验证器，请先在 fnOS Web 端完成双重验证设置，再回到 Home Assistant 添加集成。
```

- [ ] **Step 2: Check README renders cleanly as Markdown**

Run:

```bash
python3 - <<'PY'
from pathlib import Path
text = Path("README.md").read_text(encoding="utf-8")
assert "双重验证（2FA）" in text
assert "fnos>=0.13.0" in text
assert "6 位验证码" in text
PY
```

Expected:

```text
no output
```

- [ ] **Step 3: Commit README update**

Run:

```bash
git add README.md
git commit -m "docs: document fnOS 2FA login support"
```

## Task 5: Guard Against Sensitive Logging

**Files:**
- Modify: `custom_components/fnos/tests/test_logging_levels.py`
- Test: `custom_components/fnos/tests/test_logging_levels.py`

- [ ] **Step 1: Add a static sensitive-string logging test**

Append this test method to `LoggingPolicyTests`:

```python
    def test_config_flow_does_not_log_sensitive_payloads(self):
        text = self._read("config_flow.py")

        sensitive_terms = (
            "password",
            "code",
            "accessToken",
            "token",
            "longToken",
            "secret",
        )

        for level, message in self._logger_calls(text):
            with self.subTest(level=level, message=message):
                for term in sensitive_terms:
                    self.assertNotIn(term, message)
```

- [ ] **Step 2: Run logging test with Python 3.12 or newer**

Run:

```bash
python3.12 -m unittest custom_components/fnos/tests/test_logging_levels.py
```

Expected:

```text
Ran 5 tests

OK
```

If `python3.12` is not installed, run this in the Home Assistant development Python environment. The repository currently contains PEP 695 `type` alias syntax in `custom_components/fnos/__init__.py`, so Python 3.11 and older cannot parse the full existing test set.

- [ ] **Step 3: Fix config flow log messages if the sensitive logging test fails**

Use host-only log messages. These message templates are allowed:

```python
_LOGGER.warning("Cannot connect to fnOS host %s: %s", self.host, exc)
_LOGGER.warning("fnOS login failed for host %s: %s", self.host, exc)
_LOGGER.warning("fnOS two-factor verification failed for host %s: %s", self.host, exc)
_LOGGER.exception("Unexpected exception: %s", exc)
```

Do not add log messages that include `user_input`, `response`, `password`, `code`, `token`, `secret`, or `accessToken`.

- [ ] **Step 4: Commit logging guard**

Run:

```bash
git add custom_components/fnos/tests/test_logging_levels.py custom_components/fnos/config_flow.py
git commit -m "test: guard fnOS auth sensitive logging"
```

## Task 6: Final Verification And Cleanup

**Files:**
- Review: all changed files

- [ ] **Step 1: Inspect changed files**

Run:

```bash
git status --short
git diff --stat
git diff -- custom_components/fnos/auth.py custom_components/fnos/config_flow.py custom_components/fnos/manifest.json custom_components/fnos/strings.json custom_components/fnos/translations/zh-Hans.json custom_components/fnos/translations/en.json README.md custom_components/fnos/tests/test_config_flow_auth.py custom_components/fnos/tests/test_logging_levels.py
```

Expected:

```text
No unstaged changes if every task was committed.
```

- [ ] **Step 2: Run focused tests**

Run:

```bash
python3 custom_components/fnos/tests/test_config_flow_auth.py
```

Expected:

```text
Ran 12 tests

OK
```

- [ ] **Step 3: Run JSON validation**

Run:

```bash
python3 -m json.tool custom_components/fnos/manifest.json >/dev/null
python3 -m json.tool custom_components/fnos/strings.json >/dev/null
python3 -m json.tool custom_components/fnos/translations/zh-Hans.json >/dev/null
python3 -m json.tool custom_components/fnos/translations/en.json >/dev/null
```

Expected:

```text
no output
```

- [ ] **Step 4: Run full existing test suite in a Python 3.12+ environment**

Run:

```bash
python3.12 -m unittest discover custom_components/fnos/tests
```

Expected:

```text
OK
```

If `python3.12` is unavailable locally, record that full-suite verification is blocked by the local Python version and include the focused test results in the handoff.

- [ ] **Step 5: Manual config flow smoke test in Home Assistant**

Install the branch in a Home Assistant development instance and verify:

1. Add fnOS integration with an account that does not require 2FA.
2. Confirm the config entry is created from the first form.
3. Remove the config entry.
4. Add fnOS integration with an account that has 2FA enabled.
5. Confirm the first form transitions to the 2FA form.
6. Enter an invalid 6-digit code and confirm the form stays on the 2FA step with `invalid_twofa_code`.
7. Enter a valid 6-digit code and confirm the config entry is created.
8. Check logs and confirm no password, 2FA code, access token, token, long token, or secret is printed.

- [ ] **Step 6: Final status check**

Run:

```bash
git status --short --branch
git log --oneline -5
```

Expected:

```text
Branch is feature/fnos-2fa-login.
No uncommitted implementation changes remain.
Recent commits include the helper/tests, config flow, metadata, README, and logging guard commits.
```
