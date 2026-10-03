# Traps

Every item here cost real time. They are ordered roughly by how much damage they do
if you do not know about them.

## 1. `mask`, `topground` and `headcover` images are *multiply tints*

`*mask*.gft`, `*topground*.gft` and `*headcover*` are not ordinary white bitmaps.
Turning them dark multiplies the whole window's brightness by `24/255` — about one
eighth.

**Any colour experiment run while such an image is flipped is worthless.** This is
how a whole day was spent concluding "TIM ignores its own skin colours", which is
false. `skinpatch.py`'s `SKIP_RE`/`EXCLUDE_RE` must contain those names.

Symptom: a uniformly ~8× darker window, with colours still "sort of" present.

## 2. `.gmd` colours with `alpha == 0x00` are opaque

Early `transform()` had `if a == 0: return argb` — "transparent, skip". TIM uses
alpha 0 to mean *opaque* for many properties, so that line silently discarded a whole
family of text colours (`labelTextColor 0x00000000`, `labelexTextColor`, `labelColor`,
`lnnTextColor`, ...). Symptom: a handful of labels stay stubbornly black no matter
what you edit.

## 3. The scanner reports the same colour twice

Both the TD scanner and the compact scanner can land on the same 4 value bytes.
Applying the transform twice corrupts it: the first pass lightens a black text colour
to `0xE8E8E8`, the second pass then sees "near white" and classifies it as a *surface*
and darkens it again — `tabnode_blackfonttext.gmd` ended up at `0x191919`.

De-duplicate by the **absolute offset of the value**, not by `(offset, size)`.

## 4. `theme.xml` is not read at runtime

Setting `TextColor.Text` to pure red produced **zero red pixels** on screen.
The chat body colour comes from the code path described in FORMATS.md, not from the
palette. Do not spend time on `theme.xml` expecting visible results.

## 5. …and it is cached anyway, in `rdo.cache`

`%APPDATA%\Tencent\TIM\rdo.cache` is a **zlib** blob (`78 9C`) holding extracted
resource text, `theme.xml` among it. TIM does not refresh it when the `.rdb`
changes, so a stale copy silently wins.

Delete (or rename) `rdo.cache` and `loginrdo.cache` after every install. Doing so does
not log you out. `build.ps1` does it automatically.

## 6. Verify on the real screen, not with `PrintWindow`

* `PrintWindow` renders **brighter** than the actual screen, so "it looks readable in
  my capture" means nothing.
* Cropping the desktop to a window rect will happily include **your own window** on
  top of it — measurements were taken of the agent's own UI more than once.

Correct procedure: enumerate visible top-level windows with `ctypes`
(`IsWindowVisible` + `GetWindowThreadProcessId`), grab the screen with
`PIL.ImageGrab`, crop by that rect, then count bright pixels **per row in a specific
text region**. Whole-window `p95/max` is polluted by avatars and stickers.

Also: a forwarded-chat card is a different control from a normal message bubble. Its
colours being right says nothing about the message body.

## 7. TIM leaves zombie processes that lock the DLLs

After a force-kill, `TIM.exe` can linger with `ThreadCount=1` and a 0.2 MB working
set. `taskkill /F` answers *"There is no running instance of the task"* and
`Stop-Process -Force` does nothing, but the process still holds the image mapping —
so patching `arkGraphic.dll` / `GF.dll` fails with `PermissionError`.

Workaround: image mappings are opened with `FILE_SHARE_DELETE`, so **rename the locked
file and drop the new one in place**:

```powershell
Move-Item GF.dll GF.dll.locked-<stamp>
Copy-Item GF.patched.dll GF.dll
```

`patch_dll.py` does this automatically.

## 8. A code cave must not clobber registers

The first `GF.dll` patch replaced `push esi` with `mov esi, 0FFFFFFFFh`. TIM then
**refused to start at all** — `esi` is still live after the `call SetTextColor`.
The working version pushes its own arguments and jumps back to the untouched call,
touching no register.

If TIM does not start after a DLL patch, restore `*.dll.orig` first and re-read the
cave.

## 9. Login risk control

Restarting TIM many times in a row makes Tencent serve image CAPTCHAs, including a
"select the pictures containing the character 宏" type where the glyph is hidden in a
landscape. Clicking a tile only registers when you hit the **middle of the image** —
clicking near the top edge produces no checkmark and the CAPTCHA silently re-rolls.

## 10. Miscellaneous

* `gmdark.py`'s property-name regex must be `(color|colour|clr)`. Writing
  `(color|colour|clrtext)` leaves `clrHText` / `clrSelText` — the list-control text
  colours — completely untouched.
* A bare `color` whose value is near-white is usually a *container fill*, except on
  skins whose name says otherwise (`BottomBar_FontText` is white text on a dark bar).
  Decide by file name, not by value alone.
* `AutoColor` skins keep an *input level* in their bare `color`. Feeding it white makes
  TIM compute **black** text — the opposite of what you want.
* `build.ps1` must run `gmdark.py` over **all** of `Xtml.rdb`. Running it with
  `--only login` leaves the entire main window unthemed.
* Do not trust a patch script that "printed no error": a syntax error in a Python
  helper made several builds silently skip `theme.xml` entirely, and the conclusions
  drawn from them were wrong.
