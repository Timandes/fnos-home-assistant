"""日志级别约束测试。"""

from pathlib import Path
import ast
import unittest


ROOT = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT / "custom_components" / "fnos"


class LoggingPolicyTests(unittest.TestCase):
    """确保日志级别符合 issue #2 的治理策略。"""

    def _read(self, relative_path: str) -> str:
        return (SRC_ROOT / relative_path).read_text(encoding="utf-8")

    def _logger_calls(self, text: str):
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            func = node.func
            if not (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id == "_LOGGER"
                and isinstance(func.attr, str)
                and func.attr in {"debug", "info", "warning", "error", "critical"}
            ):
                continue

            if not node.args:
                continue

            if isinstance(node.args[0], ast.Constant) and isinstance(
                node.args[0].value, str
            ):
                yield func.attr, node.args[0].value

    def _assert_no_call_level(self, text: str, message: str, disallowed_level: str):
        calls = list(self._logger_calls(text))
        self.assertIsNone(
            next((call for call in calls if call[0] == disallowed_level and message in call[1]), None),
            f"message '{message}' should not be logged with _LOGGER.{disallowed_level}()"
        )

    def _assert_call_level(self, text: str, message: str, required_level: str):
        calls = list(self._logger_calls(text))
        self.assertIsNotNone(
            next((call for call in calls if call[0] == required_level and message in call[1]), None),
            f"message '{message}' should be logged with _LOGGER.{required_level}()"
        )

    def test_init_entry_logs_use_debug_and_no_print(self):
        text = self._read("__init__.py")

        self.assertNotIn("print(\"登录结果:\", result)", text)
        self.assertNotIn("print(\"收到消息:", text)

        self._assert_call_level(text, "fnos.async_setup_entry called", "debug")
        self._assert_call_level(text, "fnos.async_unload_entry called", "debug")

    def test_coordinator_logs_are_debug_and_no_warning_or_info_payload_dump(self):
        text = self._read("coordinator.py")

        for msg in (
            "_async_setup called",
            "_async_update_data called",
            "_async_update_data got stor.general %s",
            "_async_update_data returned with %s",
            "_async_update_data got stor.listDisk %s",
            "_async_update_data got resmon.disk %s",
        ):
            self._assert_call_level(text, msg, "debug")

        for msg in (
            "_async_setup called",
            "_async_update_data called",
            "_async_update_data got stor.general %s",
            "_async_update_data returned with %s",
            "_async_update_data got stor.listDisk %s",
            "_async_update_data got resmon.disk %s",
        ):
            self._assert_no_call_level(text, msg, "warning")
            self._assert_no_call_level(text, msg, "info")

    def test_sensor_entity_payload_logs(self):
        text = self._read("sensor.py")

        for msg in (
            "sensor.async_setup_entry called",
            "[FnosDiskSensorEntity] disk: %s",
            "[FnosDiskSensorEntity] coordinator.data.get(disk): %s",
            "[FnosNetworkIfsSensorEntity] ifs: %s",
            "[FnosNetworkIfsSensorEntity] coordinator.data.get(ifs): %s",
        ):
            self._assert_call_level(text, msg, "debug")
            self._assert_no_call_level(text, msg, "warning")
            self._assert_no_call_level(text, msg, "info")

        self._assert_call_level(
            text,
            "No SMART info was found for disk %s",
            "warning",
        )

    def test_binary_sensor_payload_logs(self):
        text = self._read("binary_sensor.py")

        for msg in (
            "[FnosDiskBinarySensorEntity] disk: %s",
            "[FnosDiskBinarySensorEntity] coordinator.data.get(disk): %s",
        ):
            self._assert_call_level(text, msg, "debug")
            self._assert_no_call_level(text, msg, "warning")
            self._assert_no_call_level(text, msg, "info")

        self._assert_call_level(
            text,
            "No SMART info was found for disk %s",
            "warning",
        )

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

    def test_auth_log_calls_do_not_dump_sensitive_variables(self):
        sensitive_argument_names = {
            "result",
            "response",
            "user_input",
            "password",
            "code",
            "token",
            "long_token",
            "secret",
            "access_token",
        }

        for relative_path in ("__init__.py", "config_flow.py"):
            text = self._read(relative_path)
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue

                func = node.func
                if not (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "_LOGGER"
                ):
                    continue

                for arg in node.args[1:]:
                    with self.subTest(path=relative_path, line=node.lineno):
                        if isinstance(arg, ast.Name):
                            self.assertNotIn(arg.id, sensitive_argument_names)


if __name__ == "__main__":
    unittest.main()
