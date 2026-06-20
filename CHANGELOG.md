# 变更日志

本项目所有重要变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.4.0] - 2026-06-20

### 新增
- 支持 fnOS 双重验证（2FA）登录流程：当服务器要求 2FA 时，配置向导会提示输入 6 位验证码
- 提交 2FA 验证码时请求 fnOS 将 Home Assistant 标记为可信设备
- 支持 2FA 账号的重新认证流程：token 过期、失效或不可用时，可通过 Home Assistant UI 重新输入验证码
- 升级 pyfnos 依赖要求至 `fnos>=0.13.0`

### 修复
- 修复启用 2FA 后运行期重新登录无法获取 `secret`，导致集成初始化失败的问题
- 修复 2FA 重新认证中临时连接断开后提交验证码显示 `unknown` 的问题；提交验证码时会自动重建 2FA challenge
- 修复 token 登录后断线重连仍调用 pyfnos 默认密码重连逻辑，导致 `没有保存的用户名和密码用于重连` 的问题

### 改进
- 运行期优先使用已保存的 token、long token 和 decrypted secret 恢复会话，并在 token 刷新后回写配置项
- 避免在日志中输出密码、验证码、token、secret 等敏感认证材料

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
