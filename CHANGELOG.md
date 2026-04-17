# 变更日志

本项目所有重要变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### 修复
- 修复 pylint 警告：清理 `binary_sensor.py` 中大量未使用的导入
- 修复 pylint 警告：消除代码风格问题（行过长、多余括号、引号不一致）
- 修复拼写错误：`Healty`/`Unhealty` 改为 `Healthy`/`Unhealthy`

## [0.2.3] - 2026-04-17

### 修复
- 重构日志等级治理，统一关键日志为调试级别（`debug`）
- 将初始化与回调中的 `print` 输出移除，改为 `_LOGGER.debug`
- 保留缺失 SMART 数据告警为 `warning`：`No SMART info was found for disk %s`
- 新增日志级别约束测试：`custom_components/fnos/tests/test_logging_levels.py`

## [0.2.2] - 2026-01-31

### 修复
- 修复集成卸载时崩溃的问题，将 coordinator 关闭时的 `disconnect()` 方法调用改为 `close()`
