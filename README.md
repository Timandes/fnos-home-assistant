# 飞牛fnOS HomeAssistant组件

飞牛fnOS集成是一个**非官方**提供支持的 Home Assistant 的集成组件，它可以让您在 Home Assistant 中将飞牛fnOS视为智能设备。

## 安装

> Home Assistant 版本要求：
>
> - Core $\geq$ 2024.4.4
> - Operating System $\geq$ 13.0
>
> Python 版本要求：$\geq$ 3.12.0
>
> 原因：Home Assistant Core 2024.4.4 要求 Python >= 3.12.0（参见 [pyproject.toml](https://github.com/home-assistant/core/blob/2024.4.4/pyproject.toml) 中的 `requires-python` 配置项）。

### 方法 1：使用 git clone 命令从 GitHub 下载

```bash
cd config
git clone https://github.com/Timandes/fnos-home-assistant.git
cd fnos-home-assistant
./install.sh /config
```

推荐使用此方法安装这个集成组件，可以及时同步最新的功能。


### 方法 2: [HACS](https://hacs.xyz/)

一键从 HACS 安装集成：

[![打开您的 Home Assistant 实例并打开 Home Assistant 社区商店内的飞牛fnOS集成。](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Timandes&repository=fnos-home-assistant&category=integration)

或者，HACS > 在搜索框中输入 **fnos** > 点击 **飞牛fnOS** ，进入集成详情页  > DOWNLOAD


### 方法 3：通过 [Samba](https://github.com/home-assistant/addons/tree/master/samba) 或 [FTPS](https://github.com/hassio-addons/addon-ftp) 手动安装

下载并将 `custom_components/fnos` 文件夹复制到 Home Assistant 的 `config/custom_components` 文件夹下。



## 配置

### 登录

[设置 > 设备与服务 > 添加集成](https://my.home-assistant.io/redirect/brand/?brand=fnos) > 搜索“`fnOS`” > 下一步 > 请点击此处进行登录 > 使用飞牛fnOS帐号登录（注意：这里是飞牛fnOS系统管理员帐号，不是FN Connect帐号）

[![打开您的 Home Assistant 实例并开始配置一个新的飞牛fnOS集成实例。](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=fnos)

### 多NAS登录

用一个载有飞牛fnOS的NAS中的管理员帐号登录并配置完成后，您可以在 fnOS Integration 页面中继续添加其他NAS的帐号。

方法：[设置 > 设备与服务 > 已配置 > fnOS](https://my.home-assistant.io/redirect/integration/?domain=fnos) > 添加中枢 > 下一步 > 请点击此处进行登录 > 使用飞牛fnOS帐号登录

[![打开您的 Home Assistant 实例并显示飞牛fnOS集成。](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=fnos)



### 轮询间隔配置

集成安装后，可在集成配置页面调整轮询间隔：

[设置 > 设备与服务 > 已配置 > fnOS](https://my.home-assistant.io/redirect/integration/?domain=fnos) > 点击集成卡片上的"配置"按钮

| 配置项 | 说明 | 默认值 | 推荐范围 |
|-------|------|-------|---------|
| **系统轮询间隔** | CPU、内存、网络、运行时间 | 30 秒 | 10-300 秒 |
| **磁盘轮询间隔** | 存储卷、S.M.A.R.T. 健康状态 | 3600 秒（1小时） | 300-86400 秒 |

> **提示**：磁盘轮询会触发物理磁盘读取，可能唤醒休眠中的硬盘。如果希望硬盘保持休眠状态，建议将磁盘轮询间隔设置为较长值（如 1 小时或更长）。

## 文档

- [许可证](LICENSE)
- [更新日志](CHANGELOG.md)
- 开发文档： https://developers.home-assistant.io/docs/creating_component_index

## 硬盘健康监测算法说明

本组件提供以下四个硬盘健康监测指标：

| 指标名称 | 算法逻辑 |
|---------|---------|
| **Status (S.M.A.R.T)** | 定义硬盘的总体健康状况。直接显示 S.M.A.R.T. 的 `smart_status.passed` 字段。如果 `passed` 为 `true`，显示 `"Healty"`，表示硬盘健康状态正常；如果 `passed` 为 `false`，显示 `"Unhealty"`，表示硬盘健康状态异常；如果无法获取S.M.A.R.T.信息，显示 `"Unknown"`。 |
| **Below min remaining life** | 着重检查硬盘的损耗是否还在可控范围内。根据硬盘类型及日常运维经验采用不同算法：<br>• **普通 HDD**：检查 S.M.A.R.T. 属性 ID=5（重映射扇区计数）的 `raw.value` 是否大于0。如果 `raw.value > 0`，则触发告警。<br>• **NVMe SSD**：检查 `percentage_used`（已用寿命百分比）是否高于50。如果 `percentage_used >= 50`，则触发告警。<br>• **SAS HDD**：检查 `smart.scsi_grown_defect_list` 是否大于0。如果 `smart.scsi_grown_defect_list > 0`，则触发告警。 |
| **Exceeded max bad sectors** | 根据硬盘类型采用不同算法：<br>• **普通 HDD**：检查 S.M.A.R.T. 属性 ID=5（重映射扇区计数）的 `value` 是否低于 `thresh`（阈值）。如果 `value < thresh`，则触发告警。<br>• **NVMe SSD**：检查 `available_spare`（可用备用空间）是否低于 `available_spare_threshold`（可用备用空间阈值）。如果 `available_spare < available_spare_threshold`，则触发告警。<br>• **SAS HDD**：检查 `smart.scsi_grown_defect_list` 是否大于0。如果 `smart.scsi_grown_defect_list > 0`，则触发告警（此行为存疑，待确认）。 |
| **Reallocated sector/Retired block/Grown Defect count** | 提取 S.M.A.R.T. 属性 ID=5（重映射扇区计数）的 `raw.value` 字段，显示硬盘的重映射扇区数量（对于 SSD 则为已退役块数量）。该数值越大，表示硬盘健康状况越差。如果硬盘不支持或没有此属性（例如某些 NVMe SSD），则返回 `-1`。 |

