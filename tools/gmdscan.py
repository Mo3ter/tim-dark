#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描一个 .gmd，列出所有属性记录及其原始值。

一条记录长这样：  "TD" 0101 <kind> <?> <strtype> <长度:u16> <载荷(长度)>，
载荷与 (0xFF ^ (长度 & 0xFF)) 异或。属性记录后面通常跟着
<u32 n> <n 个原始字节> 作为它的值（颜色时 n == 4）。

python gmdscan.py <文件> [--colors] [--props] [--hex]
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import td  # noqa: E402


NAME_OK = re.compile(rb"^[A-Za-z][A-Za-z0-9_]{2,31}$")


def scan_short(buf):
    """Records in the compact form <u8 tag> <u16 len> <payload>.

    The payload is XOR'd with (0xFF ^ (len & 0xFF)); we accept a position only
    when the decoded payload is a plausible ASCII property name.
    """
    out = []
    n = len(buf)
    for p in range(n - 3):
        ln = struct.unpack_from("<H", buf, p + 1)[0]
        if ln < 3 or ln > 32 or p + 3 + ln > n:
            continue
        key = 0xFF ^ (ln & 0xFF)
        plain = bytes(b ^ key for b in buf[p + 3:p + 3 + ln])
        if not NAME_OK.match(plain):
            continue
        after = p + 3 + ln
        val = None
        if after + 4 <= n:
            vn = struct.unpack_from("<I", buf, after)[0]
            if 0 < vn <= 64 and after + 4 + vn <= n:
                val = buf[after + 4:after + 4 + vn]
        out.append(dict(tag="td", kind=0, zero=0, strtype=0, length=ln, key=key,
                        payload=plain, text=plain.decode("latin1"), value=val,
                        offset=p, size=3 + ln))
    return out


def scan(buf):
    out = []
    for r in td.walk(buf):
        after = r["offset"] + r["size"]
        val = None
        if after + 4 <= len(buf):
            n = struct.unpack_from("<I", buf, after)[0]
            if 0 < n <= 64 and after + 4 + n <= len(buf):
                val = buf[after + 4:after + 4 + n]
                r["vallen"] = n
        r["value"] = val
        out.append(r)
    seen = {(r["offset"], r["size"]) for r in out}
    for r in scan_short(buf):
        if (r["offset"], r["size"]) in seen:
            continue
        out.append(r)
    out.sort(key=lambda r: r["offset"])
    return out


def fmt_val(v):
    if v is None:
        return ""
    if len(v) == 4:
        x = struct.unpack("<I", v)[0]
        return "u32=0x%08X  A=%d R=%d G=%d B=%d" % (x, (x >> 24) & 255, x & 255, (x >> 8) & 255, (x >> 16) & 255)
    if len(v) <= 16:
        return " ".join("%02x" % b for b in v)
    return "(%d bytes) %s" % (len(v), " ".join("%02x" % b for b in v[:16]))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    path = sys.argv[1]
    buf = open(path, "rb").read()
    recs = scan(buf)
    print("file=%s bytes=%d records=%d" % (path, len(buf), len(recs)))
    for r in recs:
        txt = r["text"] or ""
        printable = all(32 <= ord(c) < 127 or c in "\u4e00" for c in txt)
        if "--colors" in sys.argv and not (r["value"] and len(r["value"]) == 4):
            continue
        if "--props" in sys.argv and not printable:
            continue
        print("@%-7d k=%-2d t=0x%02x len=%-4d %-26s -> %s"
              % (r["offset"], r["kind"], r["strtype"], r["length"],
                 td.printable(txt)[:26], fmt_val(r["value"])))


if __name__ == "__main__":
    main()
