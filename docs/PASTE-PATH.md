# 本机图片粘贴失败：AppData 挂载入口不可访问

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
