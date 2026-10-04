# 本机 TIM 3.4.8.22124 输入文字试验

`tools/patch_input.py` 针对本机 TIM 自带 `Bin/riched20.dll` 的富文本绘制路径。
`GF.dll` 的补丁和 `.gmd` 的文字配色没有覆盖此调用。

在 RVA `0x164D3`，将读取颜色参数和取得缓存地址的 10 字节指令换成
`call 代码洞 / nop`。代码洞读取颜色参数，RGB 为黑时改成 `00FFFFFFh`，
其他颜色保留，随后执行原来的 `lea eax,[ecx+114h]` 并返回。
颜色缓存比较和原来的 `SetTextColor` 调用都继续执行。
代码洞保留标志位；因为 call 多压入一个返回地址，参数偏移为 `[esp+8]`。
使用相对 call，无新增绝对地址或重定位；不改用户消息中保存的字体颜色。

补丁校验 14 字节指令上下文及 `.text` 尾部至少 32 字节的全零余量，
拒绝不匹配的 DLL，保留 `Bin/riched20.dll.input-white.orig`，不改变文件长度。
这条路径可能被 TIM 中其他富文本控件共用，其他控件的实际影响仍需观察。

2026-10-04 本机实测：在“我的 iPhone”会话输入未发送的
“白色输入测试 White 123”，补丁前黑字，安装并重启后白字，背景仍为深色。
验证修改范围仅为补丁点及代码洞，恢复这两段原字节后与原 DLL 逐字节一致。

关闭 TIM 后安装或还原：

```powershell
python tools/patch_input.py --tim-dir 'X:\SoftWare\TIM' --apply
python tools/patch_input.py --tim-dir 'X:\SoftWare\TIM' --status
python tools/patch_input.py --tim-dir 'X:\SoftWare\TIM' --revert
```

此补丁目前为独立试验脚本，普通 `build.ps1 -Rollback` 不会还原它，
需要额外执行上面的 `--revert`。未验证 TIM 3.5 的该调用位置。
