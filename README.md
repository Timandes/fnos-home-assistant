# fnOS HomeAssistant组件

飞牛fnOS集成是一个**非官方**提供支持的 Home Assistant 的集成组件，它可以让您在 Home Assistant 中将飞牛fnOS视为智能设备。

## 安装

> Home Assistant 版本要求：
>
> - Core $\geq$ 2024.4.4
> - Operating System $\geq$ 13.0

### 方法 1：使用 git clone 命令从 GitHub 下载

```bash
cd config
git clone https://github.com/Timandes/fnos-home-assistant.git
cd fnos-home-assistant
./install.sh /config
```

推荐使用此方法安装这个集成组件，可以及时同步最新的功能。



### 方法 2：通过 [Samba](https://github.com/home-assistant/addons/tree/master/samba) 或 [FTPS](https://github.com/hassio-addons/addon-ftp) 手动安装

下载并将 `custom_components/fnos` 文件夹复制到 Home Assistant 的 `config/custom_components` 文件夹下。



## 配置

### 登录

[设置 > 设备与服务 > 添加集成](https://my.home-assistant.io/redirect/brand/?brand=fnos) > 搜索“`fnOS`” > 下一步 > 请点击此处进行登录 > 使用飞牛fnOS帐号登录（注意：这里是飞牛fnOS系统管理员帐号，不是FN Connect帐号）

[![打开您的 Home Assistant 实例并开始配置一个新的飞牛fnOS集成实例。](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=fnos)

### 多NAS登录

用一个载有飞牛fnOS的NAS中的管理员帐号登录并配置完成后，您可以在 fnOS Integration 页面中继续添加其他NAS的帐号。

方法：[设置 > 设备与服务 > 已配置 > fnOS](https://my.home-assistant.io/redirect/integration/?domain=fnos) > 添加中枢 > 下一步 > 请点击此处进行登录 > 使用飞牛fnOS帐号登录

[![打开您的 Home Assistant 实例并显示飞牛fnOS集成。](https://my.home-assistant.io/badges/integration.svg)](https://my.home-assistant.io/redirect/integration/?domain=fnos)



## 文档

- [许可证](LICENSE)
- 开发文档： https://developers.home-assistant.io/docs/creating_component_index

