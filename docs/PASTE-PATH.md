# 图片与群聊收藏表情的路径修复

这是针对本机 TIM 3.4.8.22124 路径异常的可选方案，经 AI 辅助分析和实机验证形成。不是所有图片或表情失败都适用，欢迎补充可复现的记录。

## 已观察到的问题

图片粘贴时 OpenClipboard 和 GetClipboardData(CF_BITMAP) 成功，但保存到 AppData/Roaming/Tencent/Users/<账号>/TIM/WinTemp/RichOle/*.png 时，CreateFileW 返回 Windows 错误 649。还原 riched20、GF 和 arkGraphic 文字补丁后仍失败。

群聊收藏表情及文字与表情混合消息使用 Common.dll 的 Util::FS::GetTempPathW，缓存路径包含 Tencent/QQTempSys；旧 AppData 入口上的读写也返回错误 649。普通图片和私聊收藏表情在当时测试中正常。

实际目录中的原有 Tencent 数据可访问。修正两处路径后，用户确认图片能进入输入框，两种群聊表情发送正常，重启后表情发送仍正常。该方案不改 Windows 目录链接，也不迁移聊天数据。

## 当前方案：启动阶段修改内存

tools/launch_tim.py 使用 Frida 启动 TIM，在路径被缓存前修正 KernelUtil.dll 与 Common.dll 的初始化。两处补丁完成后解除连接并退出；写入的原生代码继续留在 TIM 内存中，磁盘 DLL 保持原样。

需要先完全退出 TIM，再执行：

~~~powershell
python -m pip install frida
python tools/launch_tim.py --tim-dir 'TIM安装目录' --appdata-dir '实际AppData目录'
~~~

--appdata-dir 必须是包含原有 Tencent 文件夹的父目录，不能使用任意空目录。启动器验证指令上下文与代码洞空间，Common.dll 还校验已验证原件的 SHA-256。版本不匹配时应停止并重新分析。

每次需要修复时都必须通过启动器启动。TIM 已启动后，旧路径可能已经缓存，普通 TIM.exe 或快捷方式不会应用修复。

## 开机自启

自启入口可指向同一 Python 环境的 pythonw.exe，参数为启动器脚本绝对路径、--tim-dir、--appdata-dir 和 --background。后者对应 TIM 原来的 /background 参数。

修改前保留原自启入口，避免同时保留两份启动项。pythonw.exe 可避免控制台窗口；结果写入本地 tools/launch_tim.log，该日志已排除提交。

退出 TIM 后改回普通启动即可移除本次内存补丁；如果修改了自启入口，还需恢复原入口。

## 旧磁盘方案已停用

旧版直接修改 KernelUtil.dll 后，Authenticode 状态为 HashMismatch，原始备份为 Valid。实机捕获到 AppUtil.dll 的 crsignv 回调显示“软件已被破坏”错误 0x80010001。

恢复原 DLL 后，短时对照没有再次捕获同样错误，长期稳定性仍需观察。这是本机证据，不能用来解释所有软件损坏提示。

patch_paste_path.py --apply 已停用，只保留状态检查、还原和启动器所需的补丁生成。曾安装旧版磁盘补丁的用户，应先关闭 TIM 并执行：

~~~powershell
python tools/patch_paste_path.py --tim-dir 'TIM安装目录' --status
python tools/patch_paste_path.py --tim-dir 'TIM安装目录' --revert
~~~

未安装过旧版的用户跳过还原。build.ps1 -Rollback 不包含这份独立磁盘补丁。

## 实现位置与限制

KernelUtil 在 RVA 0x100B1D 调用 SHGetSpecialFolderPathW(CSIDL_APPDATA)。内存补丁在其后的 0x100B23 使用代码洞重写栈内路径缓冲区，后续 Tencent/Users 等路径拼接继续执行。

Common 的补丁位于 RVA 0x78082，在计算长度并追加 Tencent/QQTempSys 前替换 AppData 根目录。缓存全局地址为 RVA 0x29436C；启动时按实际模块基址填写地址，以适应 ASLR，并保留所需寄存器和标志位。

当前仅验证 TIM 3.4.8.22124 的特定 DLL。升级后需要重新验证指令、缓存和缓冲区布局。此方案没有关闭 TIM 文件检查，也没有完成长期运行验证。反馈时请提供版本、操作步骤和脱敏错误记录。
