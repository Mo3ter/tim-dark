#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_dll.py -- make TIM force its own text white, by patching two engine DLLs.

Why this is needed
==================

TIM 3.5 computes/uses text colours in code, not from its skin resources, in two
different drawing paths:

1. the GF/ark graphics engine (chat message body, session list, ...)
   ``arkGraphic.dll!arkCanvasSetColor(HGCANVAS*, tagARGB)`` is handed a literal
   ``0xFF000000`` every time it paints that text.

2. plain GDI (group member list, group bulletin body, ...)
   ``gdi32!SetTextColor`` is called from exactly one place inside ``GF.dll``
   (return address ``GF.dll+0x13050`` in 3.5.0.22149), again with black.

Editing ``.rdb`` resources cannot reach either value - see docs/TRAPS.md.

What this script does
=====================

Both patches use the same trick: overwrite a few bytes at the patched site with
a relative jump to a small code cave placed in the zero padding at the end of
the ``.text`` section ("slack"), run the original effect, and jump back.

* ``arkGraphic.dll``  site RVA 0x3C11 (the ``mov [eax+198h], edx`` store)
  cave: ``cmp edx,0FF000000h / jne +5 / mov edx,0FFFFFFFFh`` then the original
  store and ``ret``.

* ``GF.dll``          site RVA 0x13045 (``mov [ebp-40h],eax`` + the two pushes
  that set up ``call SetTextColor``)
  cave: redo the ``mov``, ``push 0FFFFFFFFh`` (colour), ``push eax`` (hdc),
  then ``jmp`` back to the untouched ``call``.
  NOTE: the cave must not touch any register - an earlier version did
  ``mov esi,0FFFFFFFFh`` and TIM refused to start, because ``esi`` is live
  after the call.

``SetTextColor`` is only ever used for text, so forcing it cannot damage
backgrounds.  Both jumps are relative, so no relocation table changes are
needed and the images stay position independent.

Usage
=====

    python patch_dll.py --tim-dir "C:\\software\\TIM" --status
    python patch_dll.py --tim-dir "C:\\software\\TIM" --apply
    python patch_dll.py --tim-dir "C:\\software\\TIM" --revert

TIM must be closed.  On Windows a *mapped* DLL cannot be written to, and TIM
leaves a zombie ``TIM.exe`` behind that keeps the mapping alive, so ``--apply``
falls back to rename-then-replace (image mappings carry FILE_SHARE_DELETE).
The pristine copies are kept next to the DLLs as ``*.dll.orig``.
"""
from __future__ import annotations

import argparse
import os
import shutil
import struct
import sys
import time

# ---------------------------------------------------------------- PE helpers


def parse_pe(data: bytes):
    """-> (image_base, sections)  sections = [(name, virtual_address, virtual_size, raw_offset, raw_size)]"""
    if data[:2] != b"MZ":
        raise ValueError("not a PE file")
    e = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e:e + 4] != b"PE\0\0":
        raise ValueError("not a PE file")
    nsec = struct.unpack_from("<H", data, e + 6)[0]
    optsize = struct.unpack_from("<H", data, e + 20)[0]
    image_base = struct.unpack_from("<I", data, e + 24 + 28)[0]
    soff = e + 24 + optsize
    sections = []
    for i in range(nsec):
        raw = data[soff + i * 40: soff + i * 40 + 40]
        name = raw[0:8].rstrip(b"\0").decode("latin1")
        vsize, vaddr, rsize, roff = struct.unpack_from("<IIII", raw, 8)
        sections.append((name, vaddr, vsize, roff, rsize))
    return image_base, sections


def rva_to_off(sections, rva):
    for _n, va, vs, ro, rs in sections:
        if va <= rva < va + max(vs, rs):
            return ro + (rva - va)
    return None


def off_to_rva(sections, off):
    for _n, va, vs, ro, rs in sections:
        if ro <= off < ro + rs:
            return va + (off - ro)
    return None


def text_section(sections):
    for s in sections:
        if s[0] == ".text":
            return s
    raise ValueError("no .text section")


def find_cave(sections, size):
    """Zero padding inside .text, past VirtualSize - mapped (raw size is larger)
    and executable, and never referenced by the loader."""
    _n, va, vs, ro, rs = text_section(sections)
    off = ro + vs
    if rs - vs < size:
        raise ValueError("not enough .text slack")
    return off, va + vs


# ------------------------------------------------------------------- patches

# (dll, description, site_rva, original bytes, cave length)
PATCHES = {
    "arkGraphic.dll": {
        "desc": "force chat/list text drawn by the GF engine to white",
        "site_rva": 0x3C11,          # mov [eax+198h], edx
        "orig": bytes.fromhex("899098010000"),
        "build_cave": lambda base, cave_rva, site_rva: _cave_ark(base, cave_rva, site_rva),
    },
    "GF.dll": {
        "desc": "force text drawn through gdi32!SetTextColor to white",
        "site_rva": 0x13045,         # mov [ebp-40h],eax / push esi / push eax
        "orig": bytes.fromhex("8945c05650"),
        "build_cave": lambda base, cave_rva, site_rva: _cave_gf(base, cave_rva, site_rva),
    },
}


def _cave_ark(base, cave_rva, site_rva):
    """arkGraphic: replace the colour store with a check-then-store, called."""
    cave_va = base + cave_rva
    # 81 FA imm32 (cmp edx, 0FF000000h)
    # 75 05       (jne +5)
    # BA imm32    (mov edx, 0FFFFFFFFh)
    # 89 90 ...   (original: mov [eax+198h], edx)
    # C3          (ret)
    body = (b"\x81\xFA" + struct.pack("<I", 0xFF000000) +
            b"\x75\x05" +
            b"\xBA" + struct.pack("<I", 0xFFFFFFFF) +
            bytes.fromhex("899098010000") +
            b"\xC3")
    # site: call cave ; nop
    site_va = base + site_rva
    rel = cave_va - (site_va + 5)
    patch = b"\xE8" + struct.pack("<i", rel) + b"\x90"
    return cave_va, body, site_va, patch


def _cave_gf(base, cave_rva, site_rva):
    """GF.dll: push white + hdc ourselves, then jump back to the original call."""
    cave_va = base + cave_rva
    site_va = base + site_rva
    # mov [ebp-40h], eax
    # push 0FFFFFFFFh
    # push eax
    # jmp site+5     (the untouched `call [SetTextColor]`)
    body = (b"\x89\x45\xC0" +
            b"\x68" + struct.pack("<I", 0xFFFFFFFF) +
            b"\x50")
    jmp_at = cave_va + len(body)
    rel_back = (site_va + 5) - (jmp_at + 5)
    body += b"\xE9" + struct.pack("<i", rel_back)
    # site: jmp cave (5 bytes, overwrites mov+push esi+push eax)
    patch = b"\xE9" + struct.pack("<i", cave_va - (site_va + 5))
    return cave_va, body, site_va, patch


# --------------------------------------------------------------------- I/O


def read(path):
    with open(path, "rb") as f:
        return f.read()


def replace_locked(src, dst):
    """Write `src` over `dst` even if `dst` is currently mapped by a running
    process: rename the locked file away, then drop the new one in place."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    try:
        shutil.copyfile(src, dst)
        return "replaced in place"
    except PermissionError:
        pass
    locked = dst + ".locked-" + stamp
    os.replace(dst, locked)
    shutil.copyfile(src, dst)
    return "renamed locked file to %s, installed new one" % os.path.basename(locked)


def status(dll_path):
    data = read(dll_path)
    base, sections = parse_pe(data)
    name = os.path.basename(dll_path)
    spec = PATCHES[name]
    site_off = rva_to_off(sections, spec["site_rva"])
    if site_off is None:
        return "?? site RVA not found"
    got = data[site_off:site_off + len(spec["orig"])]
    if got[:1] in (b"\xE8", b"\xE9"):
        return "PATCHED"
    if got == spec["orig"]:
        return "pristine"
    return "UNKNOWN (%s)" % got.hex()


def apply_one(dll_path, dry=False):
    name = os.path.basename(dll_path)
    spec = PATCHES[name]
    data = bytearray(read(dll_path))
    base, sections = parse_pe(data)
    site_off = rva_to_off(sections, spec["site_rva"])
    if site_off is None:
        raise SystemExit("%s: site RVA 0x%X not found" % (name, spec["site_rva"]))
    have = bytes(data[site_off:site_off + len(spec["orig"])])
    if have[:1] in (b"\xE8", b"\xE9"):
        return "already patched"
    if have != spec["orig"]:
        raise SystemExit(
            "%s: unexpected bytes at RVA 0x%X: %s (expected %s).\n"
            "This TIM build is probably not 3.5.0.22149."
            % (name, spec["site_rva"], have.hex(), spec["orig"].hex()))

    cave_off, cave_rva = find_cave(sections, 32)
    cave_va, body, site_va, patch = spec["build_cave"](base, cave_rva, spec["site_rva"])
    if len(body) > 32:
        raise SystemExit("%s: cave too large" % name)

    # keep a pristine copy once
    orig = dll_path + ".orig"
    if not os.path.exists(orig):
        shutil.copyfile(dll_path, orig)

    if dry:
        return "would patch: cave@0x%X, site bytes %s" % (cave_rva, patch.hex())

    data[cave_off:cave_off + len(body)] = body
    data[site_off:site_off + len(patch)] = patch
    tmp = dll_path + ".patched.tmp"
    with open(tmp, "wb") as f:
        f.write(bytes(data))
    how = replace_locked(tmp, dll_path)
    os.remove(tmp)
    return "patched (%s)" % how


def revert_one(dll_path):
    orig = dll_path + ".orig"
    if not os.path.exists(orig):
        return "no backup"
    how = replace_locked(orig, dll_path)
    return "reverted (%s)" % how


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tim-dir", required=True, help=r'TIM install dir, e.g. "C:\software\TIM"')
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--revert", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    bin_dir = os.path.join(args.tim_dir, "Bin")
    if not os.path.isdir(bin_dir):
        raise SystemExit("no Bin directory under " + args.tim_dir)

    for name in PATCHES:
        p = os.path.join(bin_dir, name)
        if not os.path.exists(p):
            print("  %-18s missing" % name)
            continue
        if args.apply:
            print("  %-18s %s" % (name, apply_one(p, args.dry_run)))
        elif args.revert:
            print("  %-18s %s" % (name, revert_one(p)))
        else:
            print("  %-18s %s" % (name, status(p)))


if __name__ == "__main__":
    main()
