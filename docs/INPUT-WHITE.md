# 待输入文字变白：TIM 3.4.8.22124

这是 AI 辅助分析后经过本机验证的独立试验补丁，用于基础资源与 GF 配色未覆盖的富文本输入路径。欢迎补充其他控件和版本的验证结果。

## 实现

tools/patch_input.py 修改 TIM 自带 Bin/riched20.dll。在 RVA 0x164D3，把读取颜色参数和取得缓存地址的前 10 字节替换为相对 call 与 nop，保留后续比较和分支。

代码洞从 [esp+8] 读取颜色参数，因为 call 多压入一个返回地址。RGB 为黑时改为 00FFFFFFh，其他颜色保留；保留标志位，执行原来的 lea eax,[ecx+114h] 后返回。后续缓存比较和 SetTextColor 调用继续执行，不修改消息中保存的字体颜色。

补丁校验 14 字节指令上下文及 .text 尾部至少 32 字节全零空间，拒绝不匹配的 DLL，文件长度不变。原件保存在 Bin/riched20.dll.input-white.orig。

## 使用与还原

关闭 TIM 后执行，将目录替换为自己的安装位置：

~~~powershell
python tools/patch_input.py --tim-dir 'TIM安装目录' --apply
python tools/patch_input.py --tim-dir 'TIM安装目录' --status
python tools/patch_input.py --tim-dir 'TIM安装目录' --revert
~~~

安装或还原后重新启动 TIM。build.ps1 -Rollback 不包含此独立补丁，需要使用上述 --revert。

## 验证范围

2026-10-04 本机测试中，未发送的输入文字从黑色变为白色，背景仍为深色。修改范围为补丁点和代码洞，恢复这两段原字节后与原 DLL 逐字节一致。

该绘制路径可能被其他富文本控件共用，仍需观察其影响。当前只验证 TIM 3.4.8.22124，未验证 TIM 3.5 的对应位置。
