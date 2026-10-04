# TIM-黑暗/深色模式（tim-dark）

这是一个借助 AI 分析 TIM 资源和绘制逻辑、逐步制作的实验性深色模式项目。目前在已测试的环境中基本可用，界面细节、版本适配和长期稳定性仍需要完善。

这个仓库公开当前的脚本、分析记录和修复方法，供大家参考、修改和继续改进。欢迎提交 Issue、PR，或者在此基础上做出更好的方案。

## AI 参与了哪些工作

开发过程中使用 AI 辅助分析资源结构、梳理绘制调用、编写脚本和提出排查假设，再通过本机文件比对、调用记录和实际操作验证。文档中的格式和调用位置来自这些观察，不是腾讯提供的官方说明，也不代表已经覆盖 TIM 的全部实现。

分析记录保留了已验证的结果、适用版本和仍待确认的限制。发现错误或更好的实现方式，欢迎直接指出并修改。

## 实现原理

TIM 的背景、文字和输入框由不同路径绘制，单独替换一个颜色配置不能覆盖整个界面。

| 部分 | 做法 |
|---|---|
| 皮肤资源 | 解包 .rdb，修改识别到的 .gmd 颜色属性和背景贴图，再按原始清单打包 |
| 自动文字颜色 | 部分 AutoColor 属性是亮度输入，需要调整输入值，让引擎选择白字 |
| 引擎绘制 | 对已定位的 arkGraphic.dll 和 GF.dll 调用做小范围二进制补丁，处理资源未覆盖的黑字 |
| 待输入文字 | 可选 riched20.dll 补丁，将已定位的黑色绘制参数改为白色 |
| 特定环境的路径异常 | 可选启动器在 TIM 启动阶段修正内存中的 AppData 路径，解决已复现的图片和收藏表情缓存失败 |

资源处理包含通用颜色规则和特定控件覆盖规则，不是所有界面都已经适配。透明色键、强调色和部分图片需要单独处理。引擎调用也可能被多个控件共用，修改后应检查相关界面。

基础深色模式修改本地资源和 DLL；可选路径启动器使用 Frida 短暂连接进程，写入内存补丁后退出。两种方案的安装与还原方式不同。

## 适用版本

| 方案 | 当前验证版本 |
|---|---|
| build.ps1 基础资源与引擎补丁 | TIM 3.5.0.22149 |
| patch_input.py 输入文字补丁 | TIM 3.4.8.22124 |
| launch_tim.py 路径修复 | TIM 3.4.8.22124 的已验证 DLL |

这些版本不能互相代用。TIM 升级后需要重新验证资源、指令和缓冲区布局；不要通过跳过校验强行安装。

## 基础深色模式

需要 Windows、PowerShell 5 或以上、Python 3 和 Pillow。请把安装目录替换成自己的实际路径。

~~~powershell
python -m pip install Pillow
$timDir = 'C:\software\TIM'
.\build.ps1 -TimDir $timDir -Backup
.\build.ps1 -TimDir $timDir -Install
~~~

安装流程从备份构建资源，安装资源和引擎补丁，更新皮肤缓存并重启 TIM。首次操作前请保留原始备份。默认版本目录为 Resource.3.5.0.22149。

~~~powershell
.\build.ps1 -TimDir $timDir -Rollback
~~~

上述还原覆盖基础资源和两个引擎 DLL，不包含独立输入补丁，也不会恢复手动改过的开机自启配置。

## 可选输入文字补丁

适用于已验证的 TIM 3.4.8.22124。关闭 TIM 后执行：

~~~powershell
python tools/patch_input.py --tim-dir 'TIM安装目录' --apply
python tools/patch_input.py --tim-dir 'TIM安装目录' --status
~~~

独立还原：

~~~powershell
python tools/patch_input.py --tim-dir 'TIM安装目录' --revert
~~~

实现位置、备份和验证范围见 [输入文字说明](docs/INPUT-WHITE.md)。

## 可选图片与收藏表情路径修复

仅在符合已记录路径异常的环境中使用，不是深色模式的必装步骤。实际 AppData 目录必须包含原有 Tencent 数据，不能指向任意空目录。

~~~powershell
python -m pip install frida
python tools/launch_tim.py --tim-dir 'TIM安装目录' --appdata-dir '实际AppData目录'
~~~

需要先退出 TIM。每次启动都应使用此启动器，普通 TIM.exe 启动不会应用内存补丁。开机自启可指向同一 Python 环境的 pythonw.exe 和启动器，并追加 --background；修改前保留原入口，避免重复启动。

旧版磁盘路径补丁已停用。曾安装旧版的用户需先用 patch_paste_path.py --revert 恢复原 DLL。完整步骤见 [路径修复说明](docs/PASTE-PATH.md)。

## 欢迎修改和贡献

可以从配色细节、遗漏控件、资源解析、其他版本适配或文档纠错入手。欢迎提出不同的实现方式，也欢迎维护自己的分支。

反馈问题时，请说明 TIM 版本、使用的补丁、操作步骤和是否能稳定复现。提供日志或截图前，请去除账号、昵称、头像、聊天内容和私人路径。无需上传原始 TIM DLL 或资源包。

提交补丁时，请写明验证版本和实际测试结果；涉及二进制改动时保留原件备份、指令校验、代码洞边界检查和独立还原方式。AI 提出的假设也应经过验证后再作为结论记录。

现有自动检查：

~~~powershell
python -m unittest discover -s tests -v
~~~

测试覆盖部分颜色规则和补丁生成边界，不能替代真实 TIM 的界面、聊天功能和长期运行验证。

## 分析文档

- [资源格式与颜色路径](docs/FORMATS.md)
- [排查注意事项](docs/TRAPS.md)
- [AI 辅助分析与验证记录](docs/CN-NOTES.md)
- [待输入文字补丁](docs/INPUT-WHITE.md)
- [图片和收藏表情路径修复](docs/PASTE-PATH.md)

本项目不是腾讯官方项目，不分发 TIM 安装包、原始 DLL、资源素材或聊天数据。脚本作用于用户本地已安装的 TIM。项目代码采用 [MIT 许可证](LICENSE)，TIM、QQ 等名称属于其各自权利人。
