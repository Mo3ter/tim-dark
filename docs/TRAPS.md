# 踩过的坑

下面每一条都花过实打实的时间。大致按"不知道的话损失多大"排序。

## 1. `mask` / `topground` / `headcover` 是**乘算色调图**

`*mask*.gft`、`*topground*.gft`、`*headcover*` 不是普通的白底位图。
把它们翻黑，会让**整个窗口的亮度乘以 `24/255`**（约八分之一）。

**在这种状态下做的任何颜色实验都是无效的。** 我因此白花了一整天，还得出过
"TIM 不读自己的皮肤颜色"这个**错误结论**。`skinpatch.py` 的 `SKIP_RE` / `EXCLUDE_RE`
必须包含这几个名字。

症状：整个窗口均匀地暗了约 8 倍，颜色还在，但全都被压扁。

## 2. `.gmd` 里 `alpha == 0x00` 的颜色是**不透明**

早期 `transform()` 里有一句 `if a == 0: return argb`（"透明，跳过"）。
但 TIM 在很多属性上用 alpha 0 表示**不透明**，这一句把一整族文字颜色悄悄丢掉了：
`labelTextColor 0x00000000`、`labelexTextColor`、`labelColor`、`lnnTextColor`……
症状：少数几个标签怎么改都还是黑的。

## 3. 扫描器会把同一处颜色报两遍

TD 扫描器和紧凑扫描器可能落在同一处 4 字节上。变换跑两遍就会把颜色改坏：
第一遍把黑色文字提亮成 `0xE8E8E8`，第二遍看到"接近白"，把它当成**表面色**又压暗回去 ——
`tabnode_blackfonttext.gmd` 最后变成了 `0x191919`。

要按**值的绝对偏移**去重，而不是按 `(偏移, 长度)`。

## 4. `theme.xml` 运行时根本不被读取

把 `TextColor.Text` 改成纯红，屏幕上是 **0 个红像素**。
聊天正文的颜色来自 FORMATS.md 里描述的那条代码路径，不来自调色板。
**不要在 `theme.xml` 上花时间期待可见效果。**

## 5. ……但它还是会被缓存，在 `rdo.cache` 里

`%APPDATA%\Tencent\TIM\rdo.cache` 是一个 **zlib** 块（魔数 `78 9C`），
里面存着解出来的资源文本，其中包括 `theme.xml`。改了 `.rdb` 之后 TIM **不会刷新它**，
于是那份旧的会静默生效。

每次装完资源都要删掉（或改名）`rdo.cache` 和 `loginrdo.cache`。清缓存**不需要重新登录**。
`build.ps1` 已经自动做了。

## 6. 验证必须用真实屏幕，不能用 `PrintWindow`

* `PrintWindow` 渲染出来的**比实际屏幕更亮**，所以"我这边看着可读"毫无意义；
* 按窗口矩形裁剪桌面时，会**把你自己的窗口也框进去** —— 我有好几次量的其实是我自己界面的像素。

正确流程：用 `ctypes` 枚举可见顶层窗口（`IsWindowVisible` + `GetWindowThreadProcessId`），
用 `PIL.ImageGrab` 抓全屏，按那个矩形裁剪，然后**在具体文字区域里逐行**统计亮像素。
整窗 `p95/max` 会被头像和表情图污染。

还有一条：**转发聊天记录卡片和普通消息气泡是两种控件**，
它颜色正常不代表正文正常。

## 7. TIM 会留下僵尸进程，一直锁着 DLL

强杀之后，`TIM.exe` 可能残留一个 `ThreadCount=1`、工作集 0.2 MB 的僵尸进程。
`taskkill /F` 回你 *"没有运行实例"*，`Stop-Process -Force` 也无效，
但它仍然持有镜像映射 —— 于是补丁 `arkGraphic.dll` / `GF.dll` 时 `PermissionError`。

绕法：镜像映射是用 `FILE_SHARE_DELETE` 打开的，所以**先把被锁的文件改名，再把新文件放进去**：

```powershell
Move-Item GF.dll GF.dll.locked-<时间戳>
Copy-Item GF.patched.dll GF.dll
```

`patch_dll.py` 会自动这么做。

## 8. 代码洞**绝对不能碰寄存器**

`GF.dll` 补丁的第一版把 `push esi` 改成了 `mov esi, 0FFFFFFFFh`。
结果 TIM **直接启动不了** —— `esi` 在那条 `call SetTextColor` 之后还有用途。
能用的版本是自己压入两个参数，然后跳回**没有被改动**的那条 `call`，一个寄存器都不碰。

如果打完 DLL 补丁 TIM 起不来：先把 `*.dll.orig` 还原回去，再重新读一遍代码洞。

## 9. 登录风控

连续重启 TIM 很多次之后，腾讯会开始弹图片验证码，还包括那种
"选出所有包含文字『宏』的图片"——字被画进风景地形里。
点选时**必须点在图片正中**；点偏到上方的空白带不会产生勾选，验证码会静默重开，
表现为"怎么点都过不去"。

## 10. 杂项

* `gmdark.py` 的属性名正则必须是 `(color|colour|clr)`。写成 `(color|colour|clrtext)`
  会把 `clrHText` / `clrSelText`（列表控件文字色）整族漏掉。
* 裸 `color` 的值接近白时，通常是**容器填充色**；但文件名说明不是的就例外
  （`BottomBar_FontText` 是"深底白字"）。**用文件名判断，别只看值。**
* `AutoColor` 皮肤的裸 `color` 是**输入亮度**。喂它白色，TIM 会算出**黑字** —— 正好相反。
* `build.ps1` 必须对**整个 `Xtml.rdb`** 跑 `gmdark.py`。用 `--only login` 会让整个主窗口没被改到。
* **不要相信"脚本没报错"**：一个 Python 辅助脚本的语法错误，让好几次构建静默跳过了
  `theme.xml`，而基于那几次构建得出的结论全是错的。
