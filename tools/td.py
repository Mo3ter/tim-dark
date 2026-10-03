#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Decoder/encoder for Tencent's GF "TD" resource serialisation (.gmd / .txd).

Container grammar (reverse engineered, validated against font.gmd,
tabnode_blackfonttext.gmd, loginmainwnd.gmd, Timwp.xml.txd, pluginlist.tpc.txd):

    record := "TD" 0x01 0x01 <kind:u8> <zero:u8> <strtype:u8> <len:u16le> <payload>
              payload := plaintext XOR key,  key = 0xFF ^ (len & 0xFF)

    kind     : 1..7 (record class)
    strtype  : 0x0b ANSI string, 0x08 UTF-16LE string, others are numeric blobs
    "TA" introduces a sibling table record with the same key derivation.

Usage:
  python td.py dump   <file> [max records]
  python td.py strings <file>
"""
import os
import re
import struct
import sys

MAGIC_TD = b"TD\x01\x01"
MAGIC_TA = b"TA\x01\x01"


def decode_record(buf, pos):
    """Return (kind, strtype, raw_payload, text) for the record at pos, or None."""
    if pos + 9 > len(buf) or buf[pos:pos + 4] not in (MAGIC_TD, MAGIC_TA):
        return None
    kind = buf[pos + 4]
    zero = buf[pos + 5]
    strtype = buf[pos + 6]
    (length,) = struct.unpack_from("<H", buf, pos + 7)
    if pos + 9 + length > len(buf):
        return None
    payload = buf[pos + 9:pos + 9 + length]
    key = 0xFF ^ (length & 0xFF)
    plain = bytes(b ^ key for b in payload)
    if strtype == 0x08:
        try:
            text = plain.decode("utf-16-le", "replace")
        except Exception:
            text = None
    else:
        try:
            text = plain.decode("gbk", "replace")
            if sum(1 for c in text if c == "\ufffd") > len(text) // 3:
                text = plain.decode("latin1", "replace")
        except Exception:
            text = None
    return dict(tag=buf[pos:pos + 2].decode(), kind=kind, zero=zero, strtype=strtype,
                length=length, key=key, payload=payload, text=text, size=9 + length)


def encode_record(tag, kind, strtype, plaintext_bytes):
    length = len(plaintext_bytes)
    key = 0xFF ^ (length & 0xFF)
    payload = bytes(b ^ key for b in plaintext_bytes)
    return (tag.encode() + b"\x01\x01" + bytes([kind, 0, strtype])
            + struct.pack("<H", length) + payload)


def walk(buf, maxrec=100000):
    pos = 0
    out = []
    while pos < len(buf) and len(out) < maxrec:
        r = decode_record(buf, pos)
        if r:
            r["offset"] = pos
            out.append(r)
            pos += r["size"]
        else:
            pos += 1
    return out


def printable(s):
    return "".join(c if 32 <= ord(c) < 127 else ("." if ord(c) < 32 else c) for c in s)


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    mode = sys.argv[1]
    path = sys.argv[2]
    buf = open(path, "rb").read()
    recs = walk(buf)
    if mode == "strings":
        seen = set()
        for r in recs:
            if r["text"] and r["text"] not in seen:
                seen.add(r["text"])
                print("%-5s k=%d t=0x%02x len=%-4d %s" % (r["tag"], r["kind"], r["strtype"], r["length"], printable(r["text"])))
        return
    print("file=%s bytes=%d records=%d" % (path, len(buf), len(recs)))
    printed = 0
    last_end = 0
    for r in recs:
        if r["offset"] > last_end:
            gap = buf[last_end:r["offset"]]
            print("   [gap %d bytes] %s" % (len(gap), " ".join("%02x" % b for b in gap[:48])))
        print("@%-7d %-3s kind=%d t=0x%02x len=%-5d key=0x%02x  %s"
              % (r["offset"], r["tag"], r["kind"], r["strtype"], r["length"], r["key"],
                 printable(r["text"] or "")))
        last_end = r["offset"] + r["size"]
        printed += 1
        if printed > int(sys.argv[3] if len(sys.argv) > 3 else 100000):
            break
    if last_end < len(buf):
        gap = buf[last_end:]
        print("   [tail %d bytes] %s" % (len(gap), " ".join("%02x" % b for b in gap[:64])))


if __name__ == "__main__":
    main()
