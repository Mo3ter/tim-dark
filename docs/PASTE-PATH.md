# 本机图片粘贴失败：AppData 挂载入口不可访问

## 群聊收藏表情路径补充

群聊发送收藏表情（包括文字与表情混合消息）还会通过 Common.dll 的
`Util::FS::GetTempPathW` 使用独立的 `Tencent/QQTempSys` 缓存路径。
实机记录到此路径在旧 AppData 入口上读写返回 Windows 错误 649；
将缓存改为实际目录后，用户确认上述两种群聊发送都恢复正常。

启动器现在同时修复 Common.dll 的路径初始化：在系统路径 API 返回后、
计算字符串长度并追加 Tencent/QQTempSys 前覆盖 AppData 根目录。
原来的目录创建、缓存、锁和字符串管理流程继续执行。
Common.dll 采用已验证原件的 SHA-256 白名单；两处模块补丁完成后才解除连接。
同样只修改进程内存，磁盘 DLL 和开机自启入口的调用方式不变。

## 2026-10-05 更新：停用磁盘补丁，改为启动阶段内存修复

旧版修改磁盘 `KernelUtil.dll` 后，其 Authenticode 状态为 `HashMismatch`，
原始备份为 `Valid`。实机捕获到登录后 `AppUtil.dll` 的 `crsignv`
回调显示“软件已被破坏”错误 `0x80010001`。还原这份 DLL 后，
短时对照运行没有再捕获同样的错误；长期稳定性仍需继续观察。

因此 `patch_paste_path.py --apply` 已停用，保留 `--status` 和 `--revert`。
先关闭 TIM，已安装旧版补丁的用户执行一次 `--revert`。
未安装过旧版补丁的用户跳过还原步骤：

```powershell
python tools/patch_paste_path.py --tim-dir 'TIM安装目录' --revert
python -m pip install frida
python tools/launch_tim.py --tim-dir 'TIM安装目录' --appdata-dir '实际AppData目录'
```

启动器验证原始指令与空代码洞，在 KernelUtil 模块初始化前写入原有路径修复指令。
磁盘 DLL 保持原样；补丁完成后启动器解除连接并退出，TIM 继续运行。
它不修改或关闭 TIM 的文件检查。必须在启动阶段应用，因为 AppData 路径会被缓存，
已启动后再修改函数不能修复之前缓存的 RichOle 路径。
每次需要此路径修复时都应使用启动器；普通 TIM 快捷方式不会应用内存补丁。
开机自启入口也应指向此启动器，并可追加 `--background`，对应原有 TIM `/background`。
使用同一 Python 环境的 `pythonw.exe` 可避免弹出控制台；启动结果写入本地
`tools/launch_tim.log`（已排除提交）。请保留原自启入口备份，避免同时启动两份 TIM。
用户已确认启动阶段内存修复后图片能够进入普通聊天输入框。
只验证了 TIM 3.4.8.22124，Frida 是此启动器的额外依赖。

下面记录的是旧版磁盘方案的诊断与实现，供分析参考，不再推荐安装。

2026-10-04，TIM 3.4.8.22124 粘贴图片时，`OpenClipboard` 和
`GetClipboardData(CF_BITMAP)` 均成功，但保存到
`AppData/Roaming/Tencent/Users/<账号>/TIM/WinTemp/RichOle/*.png`
时 `CreateFileW` 返回 Windows 错误 649。还原 riched20、GF 和 arkGraphic
文字补丁后问题仍存在，不能归因于白字补丁。

本机原始 Tencent 数据在另一条可访问的实际路径中；其缓存文件大小和
时间与 AppData 入口一致。临时将 RichOle 文件操作转到该实际目录后，
图片成功进入普通聊天输入框。

## 持久修复

`tools/patch_paste_path.py` 针对本机 KernelUtil.dll：

* 内部系统数据目录函数在 RVA `0x100B1D` 调用
  `SHGetSpecialFolderPathW(CSIDL_APPDATA)`。
* 在调用之后的 RVA `0x100B23` 将原来的 `test eax,eax / je` 8 字节改为
  相对 call，代码洞重写栈内路径缓冲区为用户指定的实际 AppData 目录。
* 代码洞保存 esi/edi/ecx，以 call/pop 相对定位 UTF-16 字符串，无新增重定位。
* 后续原有 Tencent/Users/账号/TIM 路径拼接流程继续执行。
* 仅修改 TIM 自带 KernelUtil.dll，原件保存为
  `Bin/KernelUtil.dll.paste-path.orig`。Windows 原挂载入口保持不变。

这是本机路径异常的可选修复，不应默认应用到所有用户。
它影响 TIM 通过这个函数取得的系统数据路径；指定目录必须包含原有 Tencent 数据，
不能随意指定空目录。TIM 升级后需要重新验证指令与缓冲区布局。

关闭 TIM 后：

```powershell
python tools/patch_paste_path.py --tim-dir 'TIM安装目录' --appdata-dir '实际AppData目录' --apply
python tools/patch_paste_path.py --tim-dir 'TIM安装目录' --status
python tools/patch_paste_path.py --tim-dir 'TIM安装目录' --revert
```

`--appdata-dir` 应指向包含 Tencent 文件夹的父目录。
普通 `build.ps1 -Rollback` 不包含此独立补丁，需额外执行 `--revert`。

验证：修改仅涉及 8 字节补丁点及原有全零代码洞，文件长度不变，
恢复这两段原字节后与备份逐字节一致。安装后重新启动 TIM，
无需 Frida/后台进程，普通聊天 Ctrl+V 可以插入图片，白字补丁同时保留。
