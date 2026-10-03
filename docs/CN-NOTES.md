# TIM 原生深色模式

**方案：直接改 TIM 自己的皮肤资源包**（`.rdb` / `.gft` 贴图 / `.gmd` 编译皮肤 / `theme.xml` 调色板）。
不注入、不挂钩子、不盖覆盖层 —— TIM 运行的就是改过的自己。

## 关键突破（也是我之前搞错的地方）

我一度以为「`.gmd` 和 `theme.xml` 里的颜色改了没用」，那是**错的**。

`*mask*.gft` 和 `*topground*.gft` 是**乘算色调图**：把它们当成普通白色贴图翻黑之后，
整个窗口的亮度会被乘上 24/255（约 1/8）。在那个 bug 生效期间做的所有颜色测试，
任何改动都被压成接近黑色 —— 所以我得出了错误结论，白绕了一大圈。

修掉之后做决定性验证：**把所有颜色属性强制成洋红、图片一个都不动**，登录窗立刻出现
175598 个纯洋红像素 ⇒ `.gmd` 里的颜色是运行时真正生效的。

## 三条腿（`build.ps1` 一条龙，`-Rollback` 还原）

| 工具 | 作用 |
|---|---|
| `skinpatch.py` | 贴图重着色。`chrome`（灰阶翻转：白底→深、黑字→浅）+ `night`（压暗彩图）。**`SKIP_RE` 必须含 `mask`/`topground`** |
| `gmdark.py` + `gmdscan.py` | 改 `.gmd` 编译皮肤里的颜色。按属性名分类：`background/clrFrom/border/...` 当表面（浅→深），`color/normalColor/clrText/...` 当文字（深→浅），饱和强调色（链接蓝、警告红）保留。**必须用短格式扫描器**，只扫 `TD` 记录会漏掉登录窗绝大多数颜色 |
| `makedark.py` | 改 `Themes\Default.rdb\appframework\config\theme.xml`（276 个具名色）。注意 `MaskColor=0xFF00FF` 是透明色键，**不能动** |

## 资源格式（逆向结果）

* **RDB**：16 字节魔数 `531E98204F8542F0` + u32 条目数 + i64 headerSize(36) + i64 nameSize；
  之后是 `UTF-16LE 名 + NUL + i64 偏移 + i64 大小`，偏移相对 `36 + nameSize`。
  `rdb.py` 解包/重打包，往返与原始文件**逐字节一致**。
* **GFT**：`TGF` 头，u32@0x10 = 数据偏移，`NINE` 段 @0x1C 是九宫格边距，后面是标准 PNG。
* **GMD/TXD**：`TD 01 01` + kind + 0x00 + strtype + u16 长度，载荷与 `0xFF ^ 长度` 异或；
  另有单字节标签的短格式（`<u8 tag><u16 len><payload>`），属性记录后跟 `<u32 n><n 字节原始值>`。

## 使用

```powershell
.\build.ps1 -Install      # 重建并安装（会重开 TIM）
.\build.ps1 -Rollback     # 还原成原始浅色
```

备份在 `backup/`（四个原始 rdb），随时可还原。

## 状态（已逐项验证）

验证方式：`PrintWindow` 抓图后**直接统计像素亮度**（不要看预览图，那个渲染器不可靠）。

| 部位 | 结果 |
|---|---|
| 主窗口 | ✅ 原生深色。左侧列表 med=20、右侧内容区 med=22、标题栏 22，均有浅色文字（max 255） |
| 聊天窗口 | ✅ 原生深色。med=22，消息/群成员列表/工具条/输入框全深色，表情图保持彩色 |
| 登录窗 | ✅ 原生深色。面板 `#141414` + 浅色文字 |
| 头像 | ✅ 彩色正常（`headcover` 必须排除，否则头像会被压暗到 med 15） |
| 覆盖层 | ✅ 已彻底移除（用户否决），全程不注入不挂钩子 |
| 回滚 | `build.ps1 -Rollback`，四个原始 rdb 在 `backup/` |

### 已知瑕疵

* 登录窗的账号/密码输入框底色仍是白的。**不是图片**（`Res.rdb` 里只剩 17 张纯白图，
  全是必须保留的 mask/headcover；`Default.rdb` 里 0 张），也不是能扫到的 `.gmd` 颜色属性，
  判断是代码画的白底。只影响登录那一屏。

### ★ 文字颜色的真相：AutoColor（Frida 实证）

**TIM 的文字颜色绝大多数不是资源里写死的，而是运行时算出来的。**

Frida 钩 `GF.dll` 的导出 `?GetTextColor@Text@GF@Util@@YA?ATtagARGB@@T4@@Z` 得到：

```
GetTextColor(背景亮度输入) -> 文字颜色
  in=0xff141414 (深)  ->  out=0xffffffff (白)      ← 正确
  in=0xffffffff (白)  ->  out=0xff000000 (黑)      ← 问题在这
```

承载这个**输入**的是 `*_AutoColor*` / `*_AutoLight*` 系列皮肤里的**裸 `color` 属性**：

| 皮肤 | 控制的文字 |
|---|---|
| `TabNode_AutoColorFontText.gmd` | 会话列表项的名字 |
| `UIStatic_AutoColor.gmd` | 自动配色的静态文本（消息正文、成员名） |
| `UIStatic_AutoLight.gmd` | 同上，浅色变体 |
| `iconbutton_autocolor.gmd` / `iconbutton_autolight.gmd` | 自动配色的图标按钮 |

原始的 `color` 是 `0xFFFFFFFF`（浅色主题下的"白底"）→ 框架算出**黑字**。

**所以要让这些文字变白，必须把这个输入改成深色**（`gmdark.py` 里 `AUTO_RE` 命中时输出 `0xFF141414`），
而不是去改文字颜色——改文字颜色**完全无效**（我用 6 个彩色探针 + 纯红 theme.xml 都验证过，界面上一个像素都没变）。

已排除的死路：

* **`theme.xml` 运行时根本不被读取**——把 `TextColor.Text` 改成 `0xRRGGBB`=纯红，屏幕上 0 个红像素；
* **这些文字不走 gdi32**——Frida 钩 `SetTextColor` / `ExtTextOutW` / `TextOutW` / `DrawTextW`，一次都没触发；
  TIM 用 **DirectWrite + Direct2D**（进程里加载了 `DWrite.dll`/`d2d1.dll`/`arkGraphic.dll`/`GF.dll`）；
* `Data.rdb` 里**没有任何 `.gmd`**（只有头像、字体、配置）。

### 最关键的一个坑：`rdo.cache`（TIM 的资源缓存）

**TIM 会把 `theme.xml` 这类文本资源解出来缓存到 `%APPDATA%\Tencent\TIM\rdo.cache`**
（zlib 压缩；魔数 `78 9c`，解压后能看到缓存的文件名和原文）。
**改了 `.rdb` 之后 TIM 不会刷新这个缓存**，于是它继续用缓存里那份**原始 `theme.xml`**：

```
<TV name="Text" value="0x000000" .../>   ← 正文颜色，纯黑
```

表现就是：`.gmd` 的改动（列表名、群成员名）全部生效，**唯独消息正文一直是黑的**——
因为聊天正文用的是 `TextColor.Text`，它只存在于 `theme.xml`，而这一份永远是缓存里的旧值。

**处理**：每次装完资源必须清掉缓存（`build.ps1` 的 `Stop-Tim` 里已自动做）：

```powershell
Move-Item "$env:APPDATA\Tencent\TIM\rdo.cache"       "$env:APPDATA\Tencent\TIM\rdo.cache.bak"
Move-Item "$env:APPDATA\Tencent\TIM\loginrdo.cache"  "$env:APPDATA\Tencent\TIM\loginrdo.cache.bak"
```

清掉后 TIM 会从 `.rdb` 重新解出缓存，改动立刻生效（不需要重登）。

### 关键坑（复现时务必注意）

1. `*mask*.gft` / `*topground*.gft` / `*headcover*` 是**乘算色调图或覆盖层**，绝不能当白底贴图翻黑。
   翻错会让整窗亮度 ×24/255，**所有颜色测试都会失真**。
2. **`.gmd` 里颜色的 alpha 字节 = 0x00 表示"不透明"，不是透明。**
   早期 `gmdark.transform()` 里一句 `if a == 0: return argb` 把
   `ContactNodeCtrl.gmd labelTextColor 0x00000000`（会话名/联系人名）、`labelexTextColor`、
   `FolderNode* labelColor`、`lnnTextColor` 等**一大批文字色全跳过了**。
3. 扫描器（`TD` 记录 + 单字节短格式）会对**同一处颜色值重复命中**，同一个变换跑两遍：
   第二遍把刚变浅的颜色当成"接近白的表面色"又压回深色
   （`tabnode_blackfonttext color` 曾变成 `0x191919` 而不是 `0xE8E8E8`）。修法：**按值的绝对偏移去重**。
4. **裸 `color` 的近白值不能一律当表面色**。`BottomBar_FontText` 这类皮肤是"深底白字"，
   靠**文件名**判定：文件名带 `fonttext/font/text/label/title/nick/name/caption/hint/tip` → 当文字。
5. **文字一律做成纯白 `0xFFFFFFFF`**。用户明确要求：灰阶（`0xA8A8A8` / `0xE8E8E8`）在他机器上仍然判定为"不可读"。
   所以 `transform()` 的 TEXT 分支是：除了"**饱和且 L ≥ 140**"的亮强调色（链接蓝）保留色相，
   **其余全部输出纯白**（保留原 alpha 字节）。实测近白行数：成员名 148、聊天正文 250、左侧列表 47。
6. **颜色属性的"名字匹配"要够宽**。这是最后一个、也是最隐蔽的坑：
   `TEXT_RE` 原来只写 `(color|colour|clrtext)`，于是
   `clrText` ✓ 能中，但 **`clrHText`（列表项文字）、`clrSelText`（列表选中文字）全都落空** →
   `classify()` 返回 `None` → 整族属性被静默跳过，一直是纯黑。
   表现就是：主窗口会话名正常，**聊天窗的会话列表、对方消息正文、群成员名单却全黑**
   （它们走的是 list control 的 `clrHText`/`clrSelText`）。
   现在写成 `(color|colour|clr)`——凡是带 `clr` 前缀的都是颜色。
   排查手法：`python -c "import gmdark; print(gmdark.classify('clrSelText'))"`，
   只要该改的属性没改，先看 `classify` 是不是返回了 `None`。
7. `build.ps1` 里 `gmdark.py` 必须对 **Xtml.rdb 全量**跑；只跑 `--only login` 主窗口完全不会被改到。
8. 杀 TIM 要确认干净。TIM 会留**僵尸进程**（`taskkill` 报"没有运行实例"但 `Get-Process` 仍列出），
   而且旧进程会继续用旧资源 → 测试结论全是假的。
9. **验证必须用真实屏幕（`PIL.ImageGrab`），不要用 `PrintWindow`**。
   `PrintWindow` 抓到的内容会明显比实际屏幕"更亮"，而且**裁剪窗口矩形时会把自己的窗口也框进去**，
   结果量的是别的窗口（我因此连续误判两次）。正确流程：
   ① `ctypes` 枚举 `IsWindowVisible` 的顶层窗口 + `GetWindowThreadProcessId` 找 TIM 的窗口矩形；
   ② `ImageGrab.grab()` 全屏后按该矩形裁剪；
   ③ 逐行统计"有亮像素(>140) / 近白(>240) 的行数"。
   另外别把**转发聊天记录卡片**当成普通消息气泡——它是另一种控件，颜色正常不代表正文正常。
10. TIM 有登录风控：反复重启会连续弹图片验证码。点格子必须点**图片正中**，
    偏到上方空白带不会产生勾选，会变成"空提交"死循环。

## ★★ 最终解法：二进制补丁 `arkGraphic.dll`（唯一能让文字变白的手段）

资源改不动那些文字（原因见上）。真正生效的是对 TIM 图形引擎的一次**函数级补丁**。

### 原理

`arkGraphic.dll` 的导出 `arkCanvasSetColor(HGCANVAS*, tagARGB)` 负责把当前颜色写进画布：

```asm
55                push ebp
8B EC             mov  ebp, esp
8B 45 08          mov  eax, [ebp+8]      ; canvas
8B 55 0C          mov  edx, [ebp+0Ch]    ; ← 颜色参数
85 C0             test eax, eax
74 20             jz   ...
8A 88 9B010000    mov  cl,  [eax+19Bh]
89 90 98010000    mov  [eax+198h], edx   ; ← 把颜色存进画布
```

TIM 画这些文字时传进来的就是**纯黑 `0xFF000000`**。所以只要把这条存储指令改成"先判断是不是纯黑，是就换成纯白"即可。

### 补丁内容（20 字节代码洞 + 6 字节改为 call）

`.text` 段末尾有 177 字节可执行 slack（`VirtualSize` 之后的 `SizeOfRawData` 区域，仍在 `max(VS,RS)` 的映射范围内），RVA `0x6E54F`。

原指令（文件偏移 `0x3011`，RVA `0x3C11`）：

```
89 90 98 01 00 00      mov [eax+198h], edx
```

改为：

```
E8 <rel32>              call 代码洞
90                      nop
```

代码洞（20 字节）：

```asm
81 FA 00 00 00 FF       cmp  edx, 0FF000000h
75 05                   jne  short +5
BA FF FF FF FF          mov  edx, 0FFFFFFFFh
89 90 98 01 00 00       mov  [eax+198h], edx
C3                      ret
```

两处跳转都是 `rel32`/`rel8` 相对寻址，**不需要重定位**，也不影响 DLL 的 `.reloc`。

### 施工注意

1. **必须先关掉 TIM**，否则 `arkGraphic.dll` 被映射锁住，写入报 `PermissionError`。
2. **僵尸进程会一直锁着这个 DLL**。实测有一个 20:39 起就没死透的 `TIM.exe`（ThreadCount=1、WorkingSet 0.2MB、
   `taskkill` 报"没有运行实例"），普通 `Stop-Process` 杀不掉，它持有文件锁。
   绕过办法：**先改名再换文件**（`Move-Item` 可以，因为镜像映射带 `FILE_SHARE_DELETE`）：

   ```powershell
   Copy-Item arkGraphic.dll arkGraphic.patched.dll      # 复制一份
   # 在副本上打补丁
   Move-Item arkGraphic.dll arkGraphic.dll.locked-<时间戳>
   Copy-Item arkGraphic.patched.dll arkGraphic.dll
   ```

   运行中的进程继续用旧映射，下次启动加载新 DLL。
3. 备份：`arkGraphic.dll.orig`（原始）放在同目录；`build.ps1 -Rollback` 会一并还原。

### 验证（真实屏幕，不是 PrintWindow）

| 区域 | 近白(>240) 行数 |
|---|---|
| 聊天正文（对方消息） | **206**（补丁前 0） |
| 左侧会话列表 | **319** |

### 第二个补丁：`GF.dll`（右侧成员名单 / 群公告正文 / 列表文字）

`arkGraphic.dll` 的补丁只管走**自己的绘图引擎**的文字。右侧群成员名单、群公告正文走的是**另一条路**：
直接用 GDI 画。Frida 钩 `gdi32!SetTextColor` 抓到调用点高度集中：

```
78 次  ff000000 (纯黑)  @ GF.dll+0x13050   ← 就是它
25 次  e6000000         @ GF.dll+0x13050
21 次  77000000         @ GF.dll+0x13050
```

对应 `GF.dll` RVA `0x1304A` 的 `call [SetTextColor]`：

```asm
0x13045: 89 45 C0           mov  [ebp-40h], eax
0x13048: 56                 push esi        ; esi = 颜色（黑）
0x13049: 50                 push eax        ; hdc
0x1304A: FF 15 68834554     call SetTextColor
```

**补丁**：把 `0x13045` 起的 5 字节（`89 45 C0 56 50`）改成 `E9 <rel32>`，
跳到 `.text` slack（RVA `0x1A72DB`，293 字节，已确认为**全零**）里的 14 字节代码洞：

```asm
89 45 C0                mov  [ebp-40h], eax   ; 照做被覆盖的那条
68 FF FF FF FF          push 0FFFFFFFFh       ; 颜色参数 = 纯白
50                      push eax              ; hdc
E9 <rel32>              jmp  0x1304A          ; 回到原来的 call
```

因为 `SetTextColor` **只用于文字**，这样强制成白色不会误伤任何背景。

⚠️ **这个补丁第一版把 TIM 搞崩了**（启动即失败），原因是：我图省事写成
`mov esi, 0FFFFFFFFh` —— 而 **`esi` 在那个函数后面还有别的用途**，改掉它是永久性的破坏。
正确做法是**不动任何寄存器**，自己 `push` 两个参数然后跳回原 `call`。




| 部位 | 亮文字行数 |
|---|---|
| 主窗口会话名 | ✅ |
| 聊天窗左侧列表 | ✅ 183/804 行 |
| 聊天窗消息正文（含对方） | ✅ 265/804 行 |
| 群成员名单 | ✅ 346/804 行（27 段） |
| 群公告 / 搜索框 | ✅ |


### 仍未解决

群聊右侧面板的**成员名单**和**群公告正文**仍是暗色。已排除：

* 不是 `ContactNodeCtrl` / `ChatMemberBoundComboList`——用纯红/绿/洋红探针改这几个皮肤，界面毫无变化
* 改后的 `Default.rdb` 里**已经没有任何深灰文字色**（原始有 46 条 `0xFF777777` 一类，全部被改亮）
* 群公告走的是 `GroupBulletinWebkitPanel`（**Webkit 面板，web 渲染**），`.gmd` 管不到

结论：那两处文字颜色是**代码里算的或 web 页面里定义的**，不是资源。
（不过这些文字最终由 `arkGraphic.dll` 补丁统一改成了白色，所以现在它们**是可读的**。）

## 精确指派某个面板的颜色（`gmdark.py` 的 `OVERRIDE` 表）

按亮度自动映射只能得到"差不多"的深色。要**指定某个面板的确切颜色**，在 `gmdark.py` 顶部的
`OVERRIDE` 里加一条 `(文件名, 属性名, 原值) -> 新值`：

```python
OVERRIDE = {
    ("unify.xml_RecentPage.gmd", "clrFrom", 0xFF161616): 0xFF2A2A2B,
    ("newchatframe_tim.xml_ChatFrameContent.gmd", "clrFrom", 0xFFF5F6F7): 0xFF1E1E1F,
    ("unify.xml_UnifyPanel.gmd", "clrFrom", 0xFF141414): 0xFF2F2F30,
}
```

要点：

* **必须带上"原值"**。同一属性名在一个文件里常有多条记录（例如 `UnifyPanel.gmd` 还有一个
  `0x0B000000` 的半透明叠加层），不带原值会把叠加层也改成不透明色。
* **TIM 的颜色字节序是 `0xAARRGGBB`**（不是 `AABBGGRR`）。要 `RGB(47,47,48)` 就写 `0xFF2F2F30`。
* 文件名取 `os.path.basename`，即 `unify.xml_RecentPage.gmd`。
* 当前实际指派（用户指定，实测误差均为 0）：

| 位置 | 皮肤 | 颜色 |
|---|---|---|
| 窗口标题栏 | `unify.xml_RecentPage.gmd` `clrFrom`（原 `0xFF161616`） | `RGB(42,42,43)` |
| 聊天内容区 | `newchatframe_tim.xml_ChatFrameContent.gmd` `clrFrom`（原 `0xFFF5F6F7`） | `RGB(30,30,31)` |
| 左侧会话列表 | `unify.xml_UnifyPanel.gmd` `clrFrom`（原 `0xFF141414`） | `RGB(47,47,48)` |

### 怎么找到"某个面板是哪个皮肤"

**按当前实测颜色反查**：先把目标区域截图的**精确 RGB 值**量出来（`ImageGrab` + 逐区域取众数），
再在 `src` 里搜"补丁后正好等于这个值的 `.gmd` 属性"。`0x14 / 0x16` 这类值来自
`transform()` 的公式 `nl = 0x14 + (255-L)*0x3C//255`，所以 `0x16` 对应**原始亮度 245**（如 `0xFFF5F6F7`）、
`0x14` 对应**原始纯白**。拿原始值去 `origp` 里精确搜索，候选通常只有个位数，一击即中。

（彩色探针法也有效，但要注意探针文件名必须保留原 basename，否则 `OVERRIDE` 表匹配不上——
我为此白绕过一次。）




