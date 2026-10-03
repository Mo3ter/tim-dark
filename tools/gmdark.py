#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Repaint the colours compiled into GF skin files (.gmd).

Property records look like  "TD" .. <name> <u32 n> <n bytes>;  for colours n==4 and
the bytes are a raw little-endian ARGB.  We rewrite those 4 bytes in place (the
file length never changes, so the TD length/key obfuscation stays valid).

Classification is by property name:

  * surface  (background / bkg / border / clrFrom / topground / material ...)
        light surfaces become dark, dark surfaces are left alone
  * text     (color / normalColor / textColor / clrText / ...)
        dark text becomes light, light text is left alone
  * everything else, saturated accents (links, reds, brand blues) are untouched

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
# Skins whose whole point is to *compute* a text colour from the surrounding
# light level (GF::Util::Text::GetTextColor).  Their bare ``color`` is that
# INPUT, not the literal text colour: a white input yields BLACK text.  These
# must be fed a dark value so the framework computes white text.
AUTO_RE = re.compile(r"autocolor|autolight", re.I)

# Exact overrides, keyed by (file base name, property name, old value).  Checked
# before any heuristic so a specific surface can be given exactly the colour the
# user asked for.  Values are raw little-endian, TIM stores 0xAARRGGBB.
OVERRIDE = {
    # window frame / title bar  -> RGB(42,42,43)   (was 0xFF161616)
    ("unify.xml_RecentPage.gmd", "clrFrom", 0xFF161616): 0xFF2A2A2B,
    # chat content area         -> RGB(30,30,31)   (was 0xFFF5F6F7)
    ("newchatframe_tim.xml_ChatFrameContent.gmd", "clrFrom", 0xFFF5F6F7): 0xFF1E1E1F,
    # left session list         -> RGB(47,47,48)   (was 0xFF141414)
    ("unify.xml_UnifyPanel.gmd", "clrFrom", 0xFF141414): 0xFF2F2F30,
}
# fall back: (file, property) with no old value -> every record of that property
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
        # input level for GF::Util::Text::GetTextColor -- dark in, white out
        return (a << 24) | 0x00141414
    if kind == "surface":
        if mx - mn > 26 or L < 128:
            return argb                  # saturated or already dark
        nl = 0x14 + (255 - L) * 0x3C // 255
        return (a << 24) | (nl << 16) | (nl << 8) | nl
    # text: on the dark surfaces we create, anything that is not essentially
    # white reads as mud.  The requirement is explicit -- make the text white.
    # Only genuinely bright accents (link blue, warning red) keep their hue so
    # links stay recognisable; everything else becomes pure #FFFFFF.
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
    is_input = 'inputframe' in path.lower()
    done_offsets = set()
    buf = bytearray(open(path, "rb").read())
    changed = []
    for r in gmdscan.scan(bytes(buf)):
        name = r["text"]
        v = r["value"]
        if not name or v is None or len(v) != 4:
            continue
        if not all(32 <= ord(c) < 127 for c in name):
            continue
        off = r["offset"] + r["size"] + 4
        # The TD scanner and the compact scanner can both land on the same value
        # bytes.  Processing them twice corrupts the colour (a lightened colour
        # would be seen again -- now "near white" -- and darkened back), so each
        # value offset is handled exactly once.
        if off in done_offsets:
            continue
        done_offsets.add(off)
        old = struct.unpack("<I", bytes(buf[off:off + 4]))[0]
        # an explicit, user-requested colour wins over every heuristic.  The exact
        # (file, property, old value) triple is preferred, so translucent overlays
        # that share a property name are left alone.
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
        kind = 'surface' if (is_input and classify(name)) else decide_kind(name, old, os.path.basename(path))
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
