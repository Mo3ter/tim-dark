#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重绘编译进 GF 皮肤文件（.gmd）里的颜色。

属性记录形如  "TD" .. <名称> <u32 n> <n 字节>；颜色时 n==4，
那 4 字节就是原始的小端 ARGB。我们**就地改写这 4 字节**（文件长度不变，
所以 TD 的长度/异或混淆依然成立）。

按属性名分类：

  * 表面色 surface（background / bkg / border / clrFrom / topground / material …）
        浅色表面变深，本来就深的表面不动
  * 文字色 text（color / normalColor / textColor / clrText …）
        深色文字变亮，本来就亮的文字不动
  * 其余，以及有饱和度的强调色（链接、红色、品牌蓝）一律不动

python gmdark.py <dir> [--only REGEX] [--dry]
"""
import colorsys
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gmdscan  # noqa: E402

SURFACE_RE = re.compile(
    r"(background|backgroundcolor|bkg|clrfrom|clrto|border|topground|material"
    r"|fill|shadow|splitline|frame|barcolor|linecolor)", re.I)
TEXT_RE = re.compile(r"(color|colour|clr)", re.I)
NOT_COLOR_RE = re.compile(r"(hiddencolor|maskcolor|keycolor|transparent|colorize|colorindex)", re.I)
TEXTFILE_RE = re.compile(r"(fonttext|font|text|label|title|nick|name|caption|hint|tip)", re.I)
# 这类皮肤存在的意义就是**根据周围亮度算出一个文字颜色**
# （GF::Util::Text::GetTextColor）。它们那个裸 ``color`` 是算式的**输入值**，
# 不是文字颜色本身：输入白色会算出**黑色**文字。所以必须喂它们深色，
# 框架才会算出白色文字。
AUTO_RE = re.compile(r"autocolor|autolight", re.I)

# 精确指派表，键 =(文件名, 属性名, 原值)。它在所有启发式规则**之前**生效，
# 这样就能把某个特定的面精确改成用户要求的颜色。值是小端原始值，
# TIM 存的字节序是 0xAARRGGBB。
OVERRIDE = {
    # 窗口标题栏      -> RGB(42,42,43)   (原值 0xFF161616)
    ("unify.xml_RecentPage.gmd", "clrFrom", 0xFF161616): 0xFF2A2A2B,
    # 聊天内容区      -> RGB(30,30,31)   (原值 0xFFF5F6F7)
    ("newchatframe_tim.xml_ChatFrameContent.gmd", "clrFrom", 0xFFF5F6F7): 0xFF1E1E1F,
    # 左侧会话列表    -> RGB(47,47,48)   (原值 0xFF141414)
    ("unify.xml_UnifyPanel.gmd", "clrFrom", 0xFF141414): 0xFF2F2F30,
}
# 后备规则：(文件名, 属性名) 不带原值 -> 该属性的所有记录
OVERRIDE_ANY = {}


def classify(name):
    n = name.lower()
    if NOT_COLOR_RE.search(n):
        return None
    if SURFACE_RE.search(n):
        return "surface"
    if TEXT_RE.search(n):
        return "text"
    return None


def lum(r, g, b):
    return (r * 299 + g * 587 + b * 114) // 1000


def transform(argb, kind):
    a = (argb >> 24) & 0xFF
    r = argb & 0xFF
    g = (argb >> 8) & 0xFF
    b = (argb >> 16) & 0xFF
    mx, mn = max(r, g, b), min(r, g, b)
    L = lum(r, g, b)
    if kind == "autobg":
        # GF::Util::Text::GetTextColor 的输入亮度 —— 喂深色，出白色
        return (a << 24) | 0x00141414
    if kind == "surface":
        if mx - mn > 26 or L < 128:
            return argb                  # saturated or already dark
        nl = 0x14 + (255 - L) * 0x3C // 255
        return (a << 24) | (nl << 16) | (nl << 8) | nl
    # 文字：在我们造出来的深色底上，只要不是接近白的颜色都会糊成一团。
    # 用户的要求很明确 —— 把文字改成白色。只有真正明亮的强调色
    # （链接蓝、警告红）保留色相好让链接还能认出来，
    # 其余一律变成纯 #FFFFFF。
    if mx - mn > 26 and L >= 140:
        return argb                      # bright brand accent, already readable
    if r == 255 and g == 255 and b == 255:
        return argb
    return (a << 24) | 0x00FFFFFF


def decide_kind(name, argb, fname=""):
    """Classify a property, taking its value (and its file) into account.

    A bare ``color`` is usually a *text* colour (black / grey) but on container
    controls it is the *fill* colour and is white.  A near-white bare colour is
    therefore a surface -- **unless** the skin itself is a text skin
    (``BottomBar_FontText`` and friends), where a white colour is white *text*
    on a dark bar and must stay light.
    """
    kind = classify(name)
    if AUTO_RE.search(fname or "") and name.lower() == "color":
        return "autobg"          # AutoColor input -> feed it a dark level
    if kind == "text" and name.lower() == "color":
        r, g, b = argb & 0xFF, (argb >> 8) & 0xFF, (argb >> 16) & 0xFF
        if lum(r, g, b) >= 230:
            if TEXTFILE_RE.search(fname or ""):
                return "text"
            return "surface"
    return kind


def patch_file(path, dry=False):
    done_offsets = set()
    with open(path, "rb") as f:
        buf = bytearray(f.read())
    changed = []
    for r in gmdscan.scan(bytes(buf)):
        name = r["text"]
        v = r["value"]
        if not name or v is None or len(v) != 4:
            continue
        if not all(32 <= ord(c) < 127 for c in name):
            continue
        off = r["offset"] + r["size"] + 4
        # TD 扫描器和紧凑扫描器可能落在同一处值的字节上。
        # 处理两遍会把颜色改坏（被提亮过的颜色会再被看到一次 ——
        # 此时已经"接近白" —— 于是又被压暗回去），
        # 所以每个值的偏移只处理一次。
        if off in done_offsets:
            continue
        done_offsets.add(off)
        old = struct.unpack("<I", bytes(buf[off:off + 4]))[0]
        # 明确指定的颜色优先于所有启发式规则。
        # (文件名, 属性名, 原值) 三元组优先，
        # 这样共用同一个属性名的半透明叠加层就不会被误改。
        bn = os.path.basename(path)
        ov = OVERRIDE.get((bn, name, old))
        if ov is None:
            ov = OVERRIDE_ANY.get((bn, name))
        if ov is not None:
            if ov != old:
                changed.append((name, old, ov))
                if not dry:
                    buf[off:off + 4] = struct.pack("<I", ov)
            continue
        # 输入框也包含文字属性，不能把整个 inputframe 的颜色都当作背景。
        # 背景/边框仍由属性名分类，AutoColor 的裸 color 仍作为亮度输入。
        kind = decide_kind(name, old, bn)
        if not kind:
            continue
        new = transform(old, kind)
        if new != old:
            changed.append((name, old, new))
            if not dry:
                buf[off:off + 4] = struct.pack("<I", new)
    if changed and not dry:
        with open(path, "wb") as f:
            f.write(buf)
    return changed


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    root = sys.argv[1]
    only = None
    if "--only" in sys.argv:
        only = re.compile(sys.argv[sys.argv.index("--only") + 1], re.I)
    dry = "--dry" in sys.argv
    files = 0
    total = 0
    for dp, _dn, fns in os.walk(root):
        for fn in fns:
            if not fn.lower().endswith(".gmd"):
                continue
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, root)
            if only and not only.search(rel):
                continue
            ch = patch_file(p, dry)
            if ch:
                files += 1
                total += len(ch)
                if dry:
                    for n, o, w in ch[:6]:
                        print("  %-24s 0x%08X -> 0x%08X   %s" % (n, o, w, rel))
    print("%s: %d files, %d colours" % ("would patch" if dry else "patched", files, total))


if __name__ == "__main__":
    main()
