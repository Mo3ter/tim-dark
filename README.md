# tim-dark —— 用 AI 分析 TIM 之后做的深色模式

> **先说清楚这个项目是什么**：它是**用 AI 分析 TIM 之后做的深色模式**。
> 只对 TIM 做了**比较简单的分析与解包**，最后的效果**基本可用，但细节还需要打磨**。
> 现在的补丁**还有很多地方要改** —— 这里只是把**目前的进度**放到 GitHub 上，
> 万一有哪位大神做出更好的方案，大家能有个参考，或者直接把这个替代掉。
>
> 所以：**别把它当成成品**。能跑、能看、能还原，仅此而已。

做法上它**不是覆盖层、也不是注入滤镜**，而是重写 TIM 自己的皮肤资源，
再给它图形引擎里两处绘制调用打二进制补丁：不注入进程、不常驻后台、
不影响点击和截图，**一条命令可以完整还原**。

下面的基础资源和两个引擎补丁由 `build.ps1` 管理；另行安装的可选补丁需要用各自的 `--revert` 还原。

```
   原版 TIM                                tim-dark
   ────────                                ────────
   白底黑字                     ──►        深底白字
   没有换肤接口                            重打包 .rdb + 两处代码洞
```

> 仓库里**故意不放截图**：一张 TIM 截图会带上别人的头像、昵称和聊天内容。
> 在自己的账号上跑一遍就知道了。

---

## 它做了什么

| 层次 | 改动 | 为什么必须改 |
|---|---|---|
| `Res.rdb` / `Xtml.rdb` / `Themes\Default.rdb` | 所有表面颜色和贴图重绘成深色，所有文字设成纯白 `#FFFFFF` | TIM 的皮肤就是 `.rdb` 里的普通文件，这部分属于"常规换肤" |
| `arkGraphic.dll` | 一条 `mov` 改成跳到代码洞 | 聊天正文/会话列表的文字颜色是**代码里算的**，任何皮肤里都没有 |
| `GF.dll` | 一条 `call` 改成跳到代码洞 | 群成员名单、群公告等文字走 **GDI** 绘制，颜色写死是黑 |

三条命令：

```powershell
.\build.ps1 -Backup            # 首次：备份 TIM 的 4 个原始 .rdb
.\build.ps1 -Install           # 构建 → 安装 → 打 DLL 补丁 → 清缓存 → 重启 TIM
.\build.ps1 -Rollback          # 全部还原（资源 + 两个 DLL）
```

依赖：Python 3（含 Pillow）、PowerShell 5+、已安装 TIM 3.5.0.22149。
如果 TIM 装在 `C:\Program Files\` 下，需要管理员权限。

### 可选：聊天输入文字变白（TIM 3.4.8.22124）

聊天输入区使用 TIM 自带的 `riched20.dll`，基础主题的文字补丁没有覆盖这条路径。
新增的独立补丁只把绘制时 RGB 为黑的文字改成白色，保留其他字体颜色。
关闭 TIM 后执行，再正常启动 TIM：

```powershell
python tools/patch_input.py --tim-dir "你的TIM安装目录" --apply
python tools/patch_input.py --tim-dir "你的TIM安装目录" --status
python tools/patch_input.py --tim-dir "你的TIM安装目录" --revert
```

该补丁已在 **3.4.8.22124** 实机验证；尚未验证 3.5。
脚本校验原指令和代码洞，保留原始 DLL，不匹配时拒绝安装。
详见 [输入文字补丁说明](docs/INPUT-WHITE.md)。

### 可选：图片粘贴时临时目录不可访问

本次排查发现，图片粘贴失败来自 AppData 挂载入口错误：TIM 能读取剪贴板图片，
但无法写入 `WinTemp\RichOle`。还原文字补丁后问题仍存在。
如果也遇到这类路径错误，并已找到包含原有 Tencent 数据的实际 AppData 目录，
可以在关闭 TIM 后使用启动阶段的内存路径修复：

```powershell
# 如果装过旧版磁盘路径补丁，先还原一次
python tools/patch_paste_path.py --tim-dir "你的TIM安装目录" --revert
python -m pip install frida
python tools/launch_tim.py --tim-dir "你的TIM安装目录" --appdata-dir "实际AppData目录"
```

旧版磁盘补丁可能触发 TIM 的 `crsignv` 检查，显示错误 `0x80010001`，已停用 `--apply`。
现在启动器只修改进程内存，磁盘 `KernelUtil.dll` 保持原件；完成后退出，无常驻记录器。
这个可选启动器使用 Frida 短暂注入，每次启动都需要通过它运行；基础主题构建流程不变。
实际目录必须包含原有 `Tencent` 文件夹。此方案只验证了 **3.4.8.22124**。
详见 [图片粘贴路径修复](docs/PASTE-PATH.md)。

---

## 为什么要写这个项目

TIM 3.5 是老一代 C++/GF 框架的程序。网上能找到的"深色模式"方案基本只有两类：

* **覆盖层**：在窗口上面再盖一层反色的画面。文字是能看了，但点击、截图、全屏都会被破坏，
  而且那不是一个深色主题，是个滤镜；
* **只重绘皮肤贴图**：窗口变黑了，所有标签变成"黑底黑字"。

想把这件事做对，必须搞清三件事，每一件都花了实打实的时间：

1. **TIM 的皮肤存在哪** —— `.rdb` 容器，索引格式简单到可以自己解；
2. **大部分文字颜色根本不在皮肤里** —— 要么是 `AutoColor` 的**输入值**，要么写死在引擎代码里；
3. **TIM 会缓存解出来的资源** —— 你改了 `.rdb` 它照样用旧值。

三件事的细节分别在 [`docs/FORMATS.md`](docs/FORMATS.md) 和 [`docs/TRAPS.md`](docs/TRAPS.md)。
如果只看一份，看 `TRAPS.md`。

---

## 目录结构

```
build.ps1              一条龙：构建 / 安装 / 回滚
tools/
  rdb.py               .rdb 容器解包与重打包（往返字节一致）
  gmdscan.py           扫描编译后的 .gmd 皮肤，取出「属性名 + 值」记录
  gmdark.py            重绘 .gmd 里的颜色（含精确 OVERRIDE 指派表）
  makedark.py          appframework/config/theme.xml 的深色调色板
  skinpatch.py         重着色位图皮肤（.gft/.png），灰阶翻转 + 夜景压暗
  patch_dll.py         两处引擎补丁，支持 --status / --apply / --revert
  patch_input.py       3.4.8 聊天输入文字的可选白字补丁
  patch_paste_path.py  旧版图片路径磁盘补丁的状态检查和还原
  launch_tim.py        启动阶段图片路径内存修复（需要 Frida）
docs/
  FORMATS.md           .rdb / .gft / .gmd 文件格式（逆向结果）
  TRAPS.md             踩过的十个坑，按踩进去的顺序排列
  CN-NOTES.md          最原始的工作笔记（比 TRAPS 更啰嗦，含完整排查过程）
```

---

## 两处 DLL 补丁的原理

两处用的是同一招：把补丁点开头的几个字节换成**相对跳转**，跳进一段放在 `.text` 段末尾**零填充区**
里的小代码洞，做完效果再跳回来。那段区域仍在映射范围内且可执行（原始大小大于虚拟大小），
而且**所有跳转都是相对寻址，不需要改重定位表**，镜像保持位置无关。

### 一、`arkGraphic.dll` —— GF/ark 绘图引擎

```asm
; arkCanvasSetColor(HGCANVAS *画布, tagARGB 颜色)
8B 55 0C             mov  edx, [ebp+0Ch]      ; 颜色参数
89 90 98 01 00 00    mov  [eax+198h], edx     ; ← 补丁点（RVA 0x3C11）

; 改成
E8 xx xx xx xx       call 代码洞
90                   nop

; 代码洞
81 FA 00 00 00 FF    cmp  edx, 0FF000000h
75 05                jne  short 跳过
BA FF FF FF FF       mov  edx, 0FFFFFFFFh
89 90 98 01 00 00    mov  [eax+198h], edx     ; 照做原来的存储
C3                   ret
```

### 二、`GF.dll` —— 走 GDI 的那部分文字

`gdi32!SetTextColor` 在 `GF.dll` 里只有**一个调用点**（返回地址 `GF.dll+0x13050`）。
用 Frida 钩住就能看到颜色：

```
78 次  ff000000   @ GF.dll+0x13050
25 次  e6000000   @ GF.dll+0x13050
21 次  77000000   @ GF.dll+0x13050
```

```asm
; RVA 0x13045
89 45 C0             mov  [ebp-40h], eax
56                   push esi                 ; 颜色
50                   push eax                 ; hdc
FF 15 68 83 45 54    call [SetTextColor]

; 改成：跳到代码洞，由代码洞自己压入白色，再跳回那条 call
E9 xx xx xx xx       jmp 代码洞

; 代码洞
89 45 C0             mov  [ebp-40h], eax      ; 补上被覆盖的那条
68 FF FF FF FF       push 0FFFFFFFFh          ; 颜色 = 纯白
50                   push eax                 ; hdc
E9 xx xx xx xx       jmp  跳回那条 call
```

`SetTextColor` **只影响文字**，所以在这里强制成白色不可能弄坏任何背景 ——
这正是它比"把暗色一律刷白"安全得多的原因。

> ⚠️ 代码洞**绝对不能碰任何寄存器**。这个补丁的第一版为了省事写成
> `mov esi, 0FFFFFFFFh`，结果 **TIM 直接启动不了** —— `esi` 在那条 `call` 之后还有别的用途。
> 正确做法是自己压参数，然后跳回原来那条 `call`。

---

## 怎么改配色

面板颜色不是靠亮度猜的，而是在 `tools/gmdark.py` 顶部的指派表里**精确指定**：

```python
OVERRIDE = {
    # (文件名, 属性名, 原值): 新值      —— TIM 的颜色字节序是 0xAARRGGBB
    ("unify.xml_RecentPage.gmd", "clrFrom", 0xFF161616): 0xFF2A2A2B,   # 标题栏  42 42 43
    ("newchatframe_tim.xml_ChatFrameContent.gmd", "clrFrom", 0xFFF5F6F7): 0xFF1E1E1F,  # 内容区 30 30 31
    ("unify.xml_UnifyPanel.gmd", "clrFrom", 0xFF141414): 0xFF2F2F30,   # 左列表  47 47 48
}
```

**原值必须写进键里**：同一个属性名在一个文件里经常出现多条
（`UnifyPanel.gmd` 里还有个 `0x0B000000` 的半透明叠加层，不能一起改）。

### 怎么找出某个面板是哪个皮肤

1. 从**真实屏幕**截图里量出该区域的**精确 RGB**；
2. 到构建出来的 `src/` 里搜"补丁后正好等于这个值"的 `.gmd` 属性；
3. `0x14` / `0x16` 来自公式 `nl = 0x14 + (255 - L) * 0x3C / 255`，
   所以 `0x16` 意味着**原始亮度 245**（如 `0xFFF5F6F7`）、`0x14` 意味着**原始纯白**；
   拿这个原始值去**原始 dump** 里精确搜索，候选通常只有个位数，一击即中。

---

## 现状与已知不足（欢迎来改）

诚实列一下现在的问题，省得别人踩一遍：

| 不足 | 说明 |
|---|---|
| **补丁跟版本绑死** | 两处补丁点的 RVA（`0x3C11` / `0x13045`）和代码洞位置都是按 **3.5.0.22149** 写死的，TIM 一升级就全部失效。没有做版本识别，也没有做特征码搜索 |
| **只处理了"纯黑"文字** | `arkGraphic` 那条只在颜色**正好等于 `0xFF000000`** 时才替换。其它深灰色文字（如果有）不会被覆盖 |
| **配色是手工挑的** | 深色调色板是逐个面钉死的，不是一套完整的明度/对比度体系。某些面板之间的层次关系还比较粗糙 |
| **个别面板没验证到** | 只在**一台机器、一个账号、一个版本**上验证过。部分面板（尤其走 Webkit 的）没有逐一确认 |
| **代码洞依赖 `.text` 末尾空位** | 这个位置在其他版本里未必存在；没有做"找不到空位就放弃"的完整回退 |
| **`.gmd` 解析是启发式的** | 两个扫描器叠加使用、按偏移去重，靠的是经验规律，不是官方格式文档。遇到没见过的记录类型可能漏改或误改 |
| **自动化验证覆盖有限 / 暂无 CI** | 已增加输入框颜色分类与独立 DLL 补丁的合成数据回归测试；完整界面效果仍需实机验证。运行 `python -m unittest discover -s tests -v` |
| **没有卸载程序** | 还原靠 `build.ps1 -Rollback`，得留着这份脚本和 `*.dll.orig` 备份 |

如果你做出了更好的版本，非常欢迎 —— 这个仓库的价值大概就是**把踩过的坑记下来了**
（见 [`docs/TRAPS.md`](docs/TRAPS.md)），让别人少走弯路。

---

## 法律声明

本仓库**不包含腾讯的任何代码、数据或素材**。它只是一组 Python / PowerShell 脚本，
作用对象是**你自己机器上已经安装好的那份 TIM**；补丁修改的是本地安装，
`build.ps1 -Rollback` 可以还原。

TIM 与 QQ 是腾讯的商标，本项目与腾讯无关。

## 许可证

MIT —— 见 [LICENSE](LICENSE)。
