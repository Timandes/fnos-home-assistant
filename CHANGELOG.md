# 变更日志

本项目所有重要变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.2.2] - 2026-01-31

### 修复
- 修复集成卸载时崩溃的问题，将 coordinator 关闭时的 `disconnect()` 方法调用改为 `close()`
