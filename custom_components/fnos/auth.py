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
