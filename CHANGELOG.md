# 变更日志

本项目所有重要变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.3.0] - 2026-04-17

### 新增
- 拆分 coordinator：系统指标（CPU/内存/网络）与磁盘指标（存储卷/S.M.A.R.T.）使用独立轮询周期，避免高频轮询唤醒休眠硬盘
- 新增 Options Flow：支持在集成配置页面自定义系统轮询间隔（默认 30 秒）和磁盘轮询间隔（默认 3600 秒）
- 新增简体中文翻译（`zh-Hans`）

### 修复
- 修复磁盘休眠时 SMART 数据为 null 导致的 `AttributeError`，该异常会使 coordinator 永久停止更新所有实体

### 改进
- 实测数据：HDD 每日唤醒次数从约 8 次降至 0 次（非维护时段）

感谢 [@genelee26](https://github.com/genelee26) 的贡献 ([#3](https://github.com/Timandes/fnos-home-assistant/pull/3))

## [0.2.3] - 2026-04-17

### 修复
- 修复 pylint 警告：清理 `binary_sensor.py` 中大量未使用的导入
- 修复 pylint 警告：消除代码风格问题（行过长、多余括号、引号不一致）
- 修复拼写错误：`Healty`/`Unhealty` 改为 `Healthy`/`Unhealthy`
- 重构日志等级治理，统一关键日志为调试级别（`debug`）
- 将初始化与回调中的 `print` 输出移除，改为 `_LOGGER.debug`
- 保留缺失 SMART 数据告警为 `warning`：`No SMART info was found for disk %s`
- 新增日志级别约束测试：`custom_components/fnos/tests/test_logging_levels.py`

## [0.2.2] - 2026-01-31

### 修复
- 修复集成卸载时崩溃的问题，将 coordinator 关闭时的 `disconnect()` 方法调用改为 `close()`
