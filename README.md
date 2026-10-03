# tim-dark — a real, resource-level dark theme for TIM 3.5

Make the Windows **TIM 3.5** client dark **for real** — not with an overlay, not with an
injected colour filter, but by rewriting TIM's own skin resources and patching two
drawing calls in its graphics engine.

No process is injected, nothing runs alongside TIM, and every change is reversible
with one command.

```
   stock TIM                              tim-dark
   ─────────                              ────────
   white panels, black text      ──►      dark panels, white text
   no skinning API                        .rdb repacked + 2 code caves
```

> Screenshots are intentionally not included: a TIM window shows other people's
> avatars, nicknames and messages. Run it on your own account and see.

---

## What it does

| Layer | Change | Why it is needed |
|---|---|---|
| `Res.rdb` / `Xtml.rdb` / `Themes\Default.rdb` | every surface colour and bitmap repainted to a dark palette; all text set to pure `#FFFFFF` | TIM's skin system is plain files in `.rdb` containers — this part is "normal" theming |
| `arkGraphic.dll` | one `mov` patched to a code cave | the chat body / session list text colour is **computed in code** and is not in any skin |
| `GF.dll` | one `call` patched to a code cave | the group member list, group bulletin and other text is drawn through **GDI** with a hardcoded black |

Two commands:

```powershell
.\build.ps1 -Backup            # once: keep a pristine copy of TIM's 4 .rdb files
.\build.ps1 -Install           # build -> install -> patch DLLs -> clear cache -> restart TIM
.\build.ps1 -Rollback          # put everything back exactly as it was
```

Requirements: Python 3 (with Pillow), PowerShell 5+, TIM 3.5.0.22149 installed.
Administrator rights are needed to write into `C:\Program Files\...` if that is
where TIM lives.

---

## Why this project exists (the short version)

TIM 3.5 is a legacy C++/GF-framework application. Every "dark mode" attempt you
will find online falls into one of two camps:

* **an overlay** that draws an inverted copy of the window on top of it — it makes
  text readable but breaks clicks, screenshots and full-screen apps, and it is
  not dark mode, it is a filter;
* **repainting the skin bitmaps only** — the window turns dark and every label
  turns into black-on-black.

Doing it properly means understanding three things, each of which cost real time
to work out:

1. **where TIM keeps its skin** — `.rdb` containers with a very simple index;
2. **that most text colours are not in the skin at all** — they are either
   `AutoColor` *inputs* or hardcoded in the engine;
3. **that TIM caches extracted resources** and will happily ignore your edits.

The details of all three are in [`docs/FORMATS.md`](docs/FORMATS.md) and
[`docs/TRAPS.md`](docs/TRAPS.md). If you only read one thing, read the traps.

---

## Repository layout

```
build.ps1              one-shot build / install / rollback
tools/
  rdb.py               unpack & repack .rdb containers (byte-identical round trip)
  gmdscan.py           scan a compiled .gmd skin for name/value records
  gmdark.py            repaint the colours inside .gmd skins (+ explicit OVERRIDE table)
  makedark.py          dark palette for appframework/config/theme.xml
  skinpatch.py         recolour the bitmap skins (.gft/.png), chrome-flip + night-shift
  patch_dll.py         the two engine patches, with status/apply/revert
docs/
  FORMATS.md           .rdb / .gft / .gmd file formats, reverse engineered
  TRAPS.md             every dead end, in the order they were walked into
  CN-NOTES.md          the original working notes (Chinese, very detailed)
```

---

## How the two DLL patches work

Both use relative jumps into a small code cave placed in the **zero padding at the
end of `.text`** — that area is still mapped (the raw size is larger than the
virtual size) and executable, and no relocation entry is needed because every
jump is relative.

### `arkGraphic.dll` — the GF/ark drawing engine

```asm
; arkCanvasSetColor(HGCANVAS *canvas, tagARGB colour)
8B 55 0C             mov  edx, [ebp+0Ch]      ; colour argument
89 90 98 01 00 00    mov  [eax+198h], edx     ; <-- patched site (RVA 0x3C11)

; becomes
E8 xx xx xx xx       call cave
90                   nop

; cave
81 FA 00 00 00 FF    cmp  edx, 0FF000000h
75 05                jne  short skip
BA FF FF FF FF       mov  edx, 0FFFFFFFFh
89 90 98 01 00 00    mov  [eax+198h], edx     ; original effect
C3                   ret
```

### `GF.dll` — the text that goes through GDI

`gdi32!SetTextColor` is called from exactly one place in `GF.dll` (return address
`GF.dll+0x13050`). Hook it with Frida and you see the colours:

```
78 ×  ff000000   @ GF.dll+0x13050
25 ×  e6000000   @ GF.dll+0x13050
21 ×  77000000   @ GF.dll+0x13050
```

```asm
; RVA 0x13045
89 45 C0             mov  [ebp-40h], eax
56                   push esi                 ; colour
50                   push eax                 ; hdc
FF 15 68 83 45 54    call [SetTextColor]

; becomes: jump to the cave, which pushes white itself and jumps back to the call
E9 xx xx xx xx       jmp cave

; cave
89 45 C0             mov  [ebp-40h], eax      ; redo the overwritten instruction
68 FF FF FF FF       push 0FFFFFFFFh          ; colour = white
50                   push eax                 ; hdc
E9 xx xx xx xx       jmp  back to the call
```

`SetTextColor` only ever affects text, so forcing white here cannot damage a
background — which is exactly why this is safer than "whiten everything that is
dark".

> ⚠️ The cave **must not touch any register**. The first version of this patch did
> `mov esi, 0FFFFFFFFh` to be clever, and TIM refused to start: `esi` is still
> live after the call. Push the arguments instead.

---

## Adjusting the palette

Panel colours are not guessed from brightness — specific surfaces are assigned
exact colours in an override table at the top of `tools/gmdark.py`:

```python
OVERRIDE = {
    # (file basename, property, old value): new value   -- TIM stores 0xAARRGGBB
    ("unify.xml_RecentPage.gmd", "clrFrom", 0xFF161616): 0xFF2A2A2B,   # title bar  42 42 43
    ("newchatframe_tim.xml_ChatFrameContent.gmd", "clrFrom", 0xFFF5F6F7): 0xFF1E1E1F,  # content 30 30 31
    ("unify.xml_UnifyPanel.gmd", "clrFrom", 0xFF141414): 0xFF2F2F30,   # left list  47 47 48
}
```

The **old value must be part of the key**: the same property name often appears
several times in one file (`UnifyPanel.gmd` also carries a `0x0B000000` translucent
overlay that must be left alone).

### Finding which skin paints a given panel

1. measure the region's **exact RGB** from a real screen capture;
2. search the built `src/` for a `.gmd` property whose patched value equals it;
3. `0x14`/`0x16` come from `nl = 0x14 + (255 - L) * 0x3C / 255`, so `0x16` implies an
   original brightness of 245 (`0xFFF5F6F7`) and `0x14` implies pure white — search the
   *pristine* dump for that original value and you will get a handful of candidates.

---

## Legal

This repository contains **no Tencent code, data or assets**. It is a set of Python
and PowerShell scripts that operate on the copy of TIM already installed on your own
machine. The patches modify that local installation, and `build.ps1 -Rollback`
restores it.

TIM and QQ are trademarks of Tencent. This project is not affiliated with Tencent.

## License

MIT — see [LICENSE](LICENSE).

---

# 中文说明

把 Windows 版 **TIM 3.5** 真正改成深色 —— **不是覆盖层、不是注入滤镜**，而是重写 TIM 自己的皮肤资源，
并给它图形引擎里两处绘制调用打二进制补丁。**不注入进程、不常驻后台，一条命令可完整还原。**

```powershell
.\build.ps1 -Backup     # 首次：备份 TIM 的 4 个原始 .rdb
.\build.ps1 -Install    # 构建 → 安装 → 打 DLL 补丁 → 清缓存 → 重启 TIM
.\build.ps1 -Rollback   # 全部还原
```

**为什么必须打 DLL 补丁**：TIM 的文字颜色大部分**不在皮肤资源里**——
聊天正文/会话列表的颜色由代码写死成纯黑丢给绘图引擎，群成员名单/群公告则走 GDI 的
`SetTextColor`。所以只改资源会得到"深色底 + 黑字"。两处补丁各自把一个字节序列改成相对跳转，
跳到 `.text` 末尾零填充区的代码洞里，强制白色后跳回 —— 全部相对寻址，不需要重定位表。

**踩过的坑**（详见 [`docs/TRAPS.md`](docs/TRAPS.md)，至少有 8 个会让你白干几小时）：

* `mask` / `topground` / `headcover` 是**乘算色调图**，当白底翻黑会让整窗亮度 ×24/255，
  在那期间做的任何颜色测试都是假的；
* `.gmd` 颜色里 **alpha=0x00 表示"不透明"**，不是透明；
* 扫描器会对**同一处颜色重复命中**，同一变换跑两遍会互相抵消 —— 必须按值偏移去重；
* `theme.xml` **运行时根本不被读取**，而且它还被缓存在 `%APPDATA%\Tencent\TIM\rdo.cache` 里；
* 验证必须用**真实屏幕**截图，`PrintWindow` 偏亮且容易把自己的窗口框进去量错；
* TIM 会留下**僵尸进程**一直锁着 DLL，导致补丁写不进去。
