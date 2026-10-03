#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dark-mode repainter for TIM skin bitmaps (.gft / .png / .bmp / .jpg).

Two transforms, both hue preserving:

  chrome  -- flips the lightness of *achromatic* pixels only (white backgrounds
             become dark grey, black glyphs become light grey) and leaves every
             saturated pixel alone, so logos / emoji / accent art survive.
  night   -- multiplies lightness by a factor (for photographic art such as the
             login illustration or the wallpaper skins).

Usage
  python skinpatch.py scan  <dir> [<dir> ...]
  python skinpatch.py apply <dir> [<dir> ...] [--only REGEX] [--dry]
"""
import io
import os
import re
import struct
import sys

from PIL import Image

PNG_SIG = b"\x89PNG\r\n\x1a\n"
IMG_EXT = (".gft", ".png", ".bmp", ".jpg", ".jpeg", ".gif")

FLOOR, CEIL = 24, 238      # output range of the chrome flip


# --------------------------------------------------------------------------- GFT
def gft_split(data):
    """-> (header_bytes, png_bytes) or (None, None) if it isn't a TGF wrapper."""
    if data[:3] != b"TGF":
        return None, None
    if data[0x14:0x18] == b"NINE":
        off = struct.unpack_from("<I", data, 0x10)[0]
    else:
        off = data.find(PNG_SIG)
    if off <= 0 or data[off:off + 8] != PNG_SIG:
        off = data.find(PNG_SIG)
    if off <= 0:
        return None, None
    return data[:off], data[off:]


def gft_join(header, png_bytes):
    return header + png_bytes


# ------------------------------------------------------------------- transforms
def _chroma_extremes(px):
    return max(px[0], px[1], px[2]), min(px[0], px[1], px[2])


def chrome_flip(img, sat_thresh=26):
    """Invert lightness of near-grey pixels; keep saturated ones."""
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            mx, mn = (r, g, b)[0], min(r, g, b)
            mx = max(r, g, b)
            if mx - mn > sat_thresh:
                continue
            lum = (r * 299 + g * 587 + b * 114) // 1000
            nl = FLOOR + (255 - lum) * (CEIL - FLOOR) // 255
            if mx != mn:                       # keep a hint of the original cast
                d = (r - lum, g - lum, b - lum)
                px[x, y] = (max(0, min(255, nl + d[0])),
                            max(0, min(255, nl + d[1])),
                            max(0, min(255, nl + d[2])), a)
            else:
                px[x, y] = (nl, nl, nl, a)
    return img


def night_shift(img, factor=0.40, lift=0):
    img = img.convert("RGBA")
    r, g, b, a = img.split()
    def f(v):
        return min(255, int(lift + v * factor))
    r = r.point(f); g = g.point(f); b = b.point(f)
    return Image.merge("RGBA", (r, g, b, a))


# ------------------------------------------------------------------- statistics
def stats_of(img):
    im = img.convert("RGBA")
    small = im.copy()
    small.thumbnail((64, 64))
    px = list(small.getdata())
    opaque = [p for p in px if p[3] > 32]
    if not opaque:
        return dict(n=0, achro=0.0, mean_l=0.0, mean_a=0.0)
    achro = sum(1 for p in opaque if max(p[:3]) - min(p[:3]) <= 26) / len(opaque)
    mean_l = sum((p[0] * 299 + p[1] * 587 + p[2] * 114) / 1000 for p in opaque) / len(opaque)
    mean_a = sum(p[3] for p in opaque) / len(opaque)
    return dict(n=len(opaque), achro=achro, mean_l=mean_l, mean_a=mean_a)


def load_png_bytes(path, data):
    if path.lower().endswith(".gft"):
        header, png = gft_split(data)
        if png is None:
            return None, None, None
        return header, png, True
    return None, data, False


def encode(img, is_gft):
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ------------------------------------------------------------------------ main
def iter_files(roots):
    for root in roots:
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                if fn.lower().endswith(IMG_EXT):
                    yield os.path.join(dirpath, fn)


def cmd_scan(roots):
    print("%-9s %-58s %5s %5s %6s %5s" % ("size", "path", "W", "H", "achro", "meanL"))
    for f in iter_files(roots):
        data = open(f, "rb").read()
        header, png, is_gft = load_png_bytes(f, data)
        if png is None:
            print("SKIP (no png payload):", f)
            continue
        try:
            im = Image.open(io.BytesIO(png))
            im.load()
        except Exception as e:
            print("SKIP (decode):", f, e)
            continue
        s = stats_of(im)
        print("%-9d %-58s %5d %5d %6.2f %5.0f"
              % (len(data), os.path.relpath(f, roots[0])[:58], im.size[0], im.size[1], s["achro"], s["mean_l"]))


NIGHT_RE = re.compile(
    r"(login_left_bg|tim_bg|animated_login|morning\.|noon\.|afternoon\.|night\.jpg"
    r"|loading\.gif|QRLogin\\qr_failed)", re.I)
SKIP_RE = re.compile(
    r"(defalut_head|default_head|qqface|emoji|face_|/face|avatar|head_bkg_highlight"
    r"|mask|topground|headcover)", re.I)
# Paths whose *colours* are compiled into .gmd files we now patch as well, so
# nothing needs to be excluded any more.  Kept as an escape hatch.
EXCLUDE_RE = re.compile(r"(nothing_matches_this)", re.I)


def decide(path, base, s):
    rel = path.replace("\\", "/")
    if SKIP_RE.search(rel):
        return None
    if s["n"] == 0:
        return None
    if NIGHT_RE.search(rel):
        return "night"
    if EXCLUDE_RE.search(rel):
        return None
    if base.lower().endswith((".jpg", ".jpeg")):
        return "night"
    # monochrome chrome: white panels, grey frames, black glyphs -> flip
    if s["achro"] >= 0.5:
        return "chrome"
    # colourful art that is much too light for a dark UI -> dim it
    if s["mean_l"] >= 200:
        return "night"
    return None


def cmd_apply(roots, only=None, dry=False, force=None):
    changed = 0
    for f in iter_files(roots):
        base = os.path.basename(f)
        rel = os.path.relpath(f, roots[0])
        if only and not re.search(only, rel, re.I):
            continue
        data = open(f, "rb").read()
        header, png, is_gft = load_png_bytes(f, data)
        if png is None:
            continue
        try:
            im = Image.open(io.BytesIO(png))
            im.load()
        except Exception:
            continue
        s = stats_of(im)
        kind = force or decide(f, base, s)
        if not kind:
            continue
        if kind == "chrome":
            out = chrome_flip(im)
        else:
            out = night_shift(im)
        newpng = encode(out, is_gft)
        if is_gft:
            newdata = gft_join(header, newpng)
        else:
            newdata = newpng
        if dry:
            print("would %-6s %-60s %d -> %d bytes" % (kind, rel, len(data), len(newdata)))
        else:
            with open(f, "wb") as fh:
                fh.write(newdata)
            print("%-6s %-60s %d -> %d" % (kind, rel, len(data), len(newdata)))
        changed += 1
    print("total changed:", changed)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    args = [a for a in sys.argv[2:] if not a.startswith("--")]
    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]
    force = None
    if "--force" in sys.argv:
        force = sys.argv[sys.argv.index("--force") + 1]
    if cmd == "scan":
        cmd_scan(args)
    elif cmd == "apply":
        cmd_apply(args, only=only, dry="--dry" in sys.argv, force=force)
    else:
        print(__doc__)
