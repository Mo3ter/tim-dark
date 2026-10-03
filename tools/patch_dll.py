#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""patch_dll.py —— 通过给两个引擎 DLL 打补丁，让 TIM 把自己的文字强制成白色。

为什么必须这么做
================

TIM 3.5 的文字颜色大部分**不在皮肤资源里**，而是代码里算出来/写死的，而且分成两条绘制路径：

1. GF/ark 绘图引擎（聊天正文、会话列表 …）
   每次画这些字时，传给
   ``arkGraphic.dll!arkCanvasSetColor(HGCANVAS*, tagARGB)`` 的都是字面量 ``0xFF000000``。

2. 普通 GDI（群成员名单、群公告正文 …）
   ``gdi32!SetTextColor`` 在 ``GF.dll`` 里**只有一个调用点**
   （3.5.0.22149 里返回地址是 ``GF.dll+0x13050``），传的同样是黑色。

改 ``.rdb`` 资源碰不到这两个值 —— 详见 docs/TRAPS.md。

这个脚本干了什么
================

两处补丁用的是同一招：把补丁点开头的几个字节改成**相对跳转**，跳进一段放在 ``.text`` 段末尾
**零填充区**（"slack"）里的小代码洞，做完原来的效果再跳回来。

* ``arkGraphic.dll``  补丁点 RVA 0x3C11（那条 ``mov [eax+198h], edx`` 存储指令）
  代码洞：``cmp edx,0FF000000h / jne +5 / mov edx,0FFFFFFFFh``，然后执行原来的存储并 ``ret``。

* ``GF.dll``          补丁点 RVA 0x13045（``mov [ebp-40h],eax`` 加后面两条为
  ``call SetTextColor`` 准备参数的 push）
  代码洞：补做那条 ``mov``，``push 0FFFFFFFFh``（颜色），``push eax``（hdc），
  然后 ``jmp`` 回那条**没有被改动**的 ``call``。
  注意：代码洞**绝对不能碰任何寄存器** —— 早期版本写了
  ``mov esi,0FFFFFFFFh``，结果 TIM 直接启动不了，因为 ``esi`` 在那条 call 之后还有用途。

``SetTextColor`` 只用于文字，所以在这里强制成白色不可能弄坏背景。
两处跳转都是相对寻址，不需要改重定位表，镜像保持位置无关。

用法
====

    python patch_dll.py --tim-dir "C:\\software\\TIM" --status
    python patch_dll.py --tim-dir "C:\\software\\TIM" --apply
    python patch_dll.py --tim-dir "C:\\software\\TIM" --revert

必须先关掉 TIM。Windows 上**已被映射的 DLL 无法写入**，而 TIM 强杀后会留下一个
僵尸 ``TIM.exe`` 一直持有映射，所以 ``--apply`` 会自动退回"先改名再放新文件"
（镜像映射带 FILE_SHARE_DELETE）。原始副本会以 ``*.dll.orig`` 的形式留在 DLL 旁边。
"""
from __future__ import annotations

import argparse
import os
import shutil
import struct
import sys
import time

# ---------------------------------------------------------------- PE 解析辅助


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


# ------------------------------------------------------------------- 补丁定义

# (dll, 说明, 补丁点 RVA, 原始字节, 代码洞长度)
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
    # 81 FA imm32 (cmp edx, 0FF000000h)   ; 比较颜色
    # 75 05       (jne +5)                ; 不是纯黑就跳过
    # BA imm32    (mov edx, 0FFFFFFFFh)   ; 换成纯白
    # 89 90 ...   (原来那条: mov [eax+198h], edx)
    # C3          (ret)
    body = (b"\x81\xFA" + struct.pack("<I", 0xFF000000) +
            b"\x75\x05" +
            b"\xBA" + struct.pack("<I", 0xFFFFFFFF) +
            bytes.fromhex("899098010000") +
            b"\xC3")
    # 补丁点: call 代码洞 ; nop
    site_va = base + site_rva
    rel = cave_va - (site_va + 5)
    patch = b"\xE8" + struct.pack("<i", rel) + b"\x90"
    return cave_va, body, site_va, patch


def _cave_gf(base, cave_rva, site_rva):
    """GF.dll: push white + hdc ourselves, then jump back to the original call."""
    cave_va = base + cave_rva
    site_va = base + site_rva
    # mov [ebp-40h], eax   ; 补上被覆盖的那条
    # push 0FFFFFFFFh      ; 颜色 = 纯白
    # push eax             ; hdc
    # jmp site+5     (那条没有被改动的 call [SetTextColor])
    body = (b"\x89\x45\xC0" +
            b"\x68" + struct.pack("<I", 0xFFFFFFFF) +
            b"\x50")
    jmp_at = cave_va + len(body)
    rel_back = (site_va + 5) - (jmp_at + 5)
    body += b"\xE9" + struct.pack("<i", rel_back)
    # 补丁点: jmp 代码洞（5 字节，覆盖 mov + push esi + push eax）
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

    # 只备份一次原始文件
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
