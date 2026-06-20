# fnOS 2FA Login Support Design

## Context

`fnos-home-assistant` currently validates credentials in a single config flow step. It calls `FnosClient.connect(host)` and `FnosClient.login(username, password)`, then treats any non-success result or exception as `invalid_auth`. This makes accounts protected by fnOS two-factor authentication fail without a way for the user to enter the verification code.

`fnos==0.13.0` adds two-factor authentication support:

- `FnosClient.login()` returns `twofaRequired=True` when the account has 2FA enabled and a verification code is required.
- `FnosClient.login()` returns `twofaSetupRequired=True` when 2FA is enforced but the account has not bound an authenticator yet.
- `FnosClient.submit_twofa_code(code, trust_device=False)` submits a 6-digit code and can request that fnOS trust the device through `trust_device=True`.

## Goals

- Upgrade the integration dependency to `fnos>=0.13.0`.
- Detect a fnOS 2FA challenge during config flow login.
- Prompt the user for a 6-digit verification code when the server requires 2FA.
- Submit the verification code with `trust_device=True`.
- Improve error mapping so connection failures are not shown as invalid credentials.
- Document the behavior and limitations clearly.

## Non-Goals

- Do not persist fnOS `token`, `longToken`, or `secret` in the Home Assistant config entry.
- Do not change entity, coordinator, polling, or runtime data collection behavior.
- Do not implement 2FA setup inside Home Assistant when fnOS requires 2FA but the user has not bound an authenticator.
- Do not add a user-facing option for trusting the device. The integration always requests trusted-device status when submitting the code.
- Do not implement stable device ID persistence unless pyfnos exposes the required API in a future version.

## Recommended Approach

Use a two-step Home Assistant config flow:

1. `async_step_user`
   - Collect `host`, `username`, and `password`.
   - Create a temporary `FnosHub` with a `FnosClient`.
   - Connect to fnOS and call `login(username, password)`.
   - If login succeeds, create the config entry.
   - If `twofaRequired=True`, keep the temporary hub and original user input on the flow instance, then transition to `async_step_twofa`.
   - If `twofaSetupRequired=True`, show a setup-required error telling the user to bind an authenticator in the fnOS web UI first.

2. `async_step_twofa`
   - Collect only a 6-digit verification code.
   - Validate the code format before calling pyfnos.
   - Call `submit_twofa_code(code, trust_device=True)`.
   - If final login succeeds, create the same config entry that the normal flow would create.
   - If verification fails, stay on the `twofa` step and show a verification-code error.

The temporary `FnosClient` is used only while the config flow is active. After the config entry is created, `async_setup_entry` continues to create its own runtime client.

## Config Flow States

### `user`

Inputs:

- `host`
- `username`
- `password`

Outcomes:

- `success`: create entry.
- `twofa_required`: continue to `twofa`.
- `twofa_setup_required`: show setup-required error.
- `invalid_auth`: show invalid authentication error.
- `cannot_connect`: show cannot-connect error.
- `unknown`: show generic unknown error.

### `twofa`

Inputs:

- `code`

Outcomes:

- final login success: create entry.
- invalid or expired code: remain on `twofa` with `invalid_twofa_code`.
- connection/session failure: show `cannot_connect` or `unknown`, depending on the exception.

## Error Handling

The implementation should distinguish these cases:

- `cannot_connect`: WebSocket connection, handshake, endpoint, timeout, or network failure.
- `invalid_auth`: username or password is rejected by fnOS.
- `invalid_twofa_code`: code is not six digits, expired, or rejected by fnOS.
- `twofa_setup_required`: fnOS requires the account to enable 2FA, but no authenticator is bound yet.
- `unknown`: fallback for unexpected errors.

Sensitive values must not be logged:

- password
- verification code
- access token
- token
- long token
- secret

## User-Facing Text

Add a `twofa` config step to `strings.json`, `translations/zh-Hans.json`, and `translations/en.json`.

Chinese text:

- Title: `输入双重验证验证码`
- Description: `该 fnOS 账号需要双重验证。请输入身份验证器应用中的 6 位验证码。提交后，Home Assistant 会请求 fnOS 信任此设备，以减少后续验证码要求。`
- Code label: `验证码`
- Code description: `6 位数字验证码`
- `invalid_twofa_code`: `验证码无效或已过期，请重新输入。`
- `twofa_setup_required`: `该账号被要求启用双重验证，但尚未绑定验证器。请先在 fnOS Web 端完成双重验证设置。`

English text:

- Title: `Enter two-factor code`
- Description: `This fnOS account requires two-factor authentication. Enter the 6-digit code from your authenticator app. Home Assistant will ask fnOS to trust this device after submitting the code.`
- Code label: `Code`
- Code description: `6-digit verification code`
- `invalid_twofa_code`: `The verification code is invalid or expired. Try again.`
- `twofa_setup_required`: `This account is required to use two-factor authentication, but no authenticator is bound yet. Set it up in the fnOS web UI first.`

The wording says "ask fnOS to trust this device" instead of promising that future logins will never need a code. pyfnos documents that whether a trusted device skips future codes is decided by the fnOS server.

## Files To Change

- `custom_components/fnos/config_flow.py`
- `custom_components/fnos/manifest.json`
- `custom_components/fnos/strings.json`
- `custom_components/fnos/translations/zh-Hans.json`
- `custom_components/fnos/translations/en.json`
- `README.md`
- Optional: `custom_components/fnos/tests/test_config_flow_auth.py`

## Tests

Prefer focused tests that do not require a full Home Assistant config flow harness.

Suggested coverage:

- Normal login success maps to `success`.
- `twofaRequired=True` maps to `twofa_required`.
- `twofaSetupRequired=True` maps to `twofa_setup_required`.
- `result=fail` maps to `invalid_auth`.
- `connect()` exceptions map to `cannot_connect`.
- 2FA submit success maps to final login success.
- 2FA submit failure maps to `invalid_twofa_code`.
- Non-6-digit codes fail validation before calling pyfnos.
- `manifest.json` requires `fnos>=0.13.0`.
- Translation files include the new `twofa` step and error keys.
- Logging tests continue to reject sensitive payload dumps.

Full Home Assistant config flow tests are out of scope for this change because the repository does not currently include Home Assistant test fixtures.

## Known Risk

The largest risk is trusted-device persistence. pyfnos 0.13.0 generates a new device ID internally when logging in and when submitting 2FA. If fnOS associates trusted-device status with that generated device ID, then a config flow login may trust one generated device while `async_setup_entry` later logs in with a different generated device. In that case, the runtime login may still require 2FA after the config entry has been created.

This integration cannot fully solve that risk unless pyfnos exposes a stable device ID parameter or the integration switches to persisted token-based login. For this change, the integration should request trusted-device status and document that final trusted-device behavior is controlled by fnOS.

## Acceptance Criteria

- A user with 2FA enabled can add the integration by entering username, password, and then a 6-digit code.
- The 2FA code is submitted with `trust_device=True`.
- A user whose account requires 2FA setup gets a clear setup-required message.
- Connection failures are shown as connection failures, not invalid authentication.
- The integration declares `fnos>=0.13.0`.
- Documentation explains 2FA support and the trusted-device limitation.
