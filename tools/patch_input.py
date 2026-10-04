"""TIM 3.4.8.22124 私有 riched20.dll 输入文字颜色补丁。

用法：python tools/patch_input.py --tim-dir X:\\SoftWare\\TIM --apply
支持 --status / --revert。安装前关闭 TIM。
"""
import argparse
import hashlib
import os
import shutil
import struct

from patch_dll import parse_pe, rva_to_off, replace_locked

RVA = 0x164D3
ORIGINAL = bytes.fromhex("8b5424048d81140100003b10751f")


def layout(data):
    _, sections = parse_pe(data)
    offset = rva_to_off(sections, RVA)
    section = next(s for s in sections if s[0] == ".text")
    _, va, vs, raw, size = section
    if size - vs < 32:
        raise ValueError("riched20.dll 没有足够的代码洞")
    cave_offset, cave_rva = raw + vs, va + vs
    patch = b"\xe8" + struct.pack("<i", cave_rva - (RVA + 5)) + b"\x90" * 5
    # call 压入了返回地址，所以原颜色参数从 [esp+4] 移到 [esp+8]。
    # 只把 RGB 为黑的 COLORREF 改白，保留其他字体颜色及原来的标志位。
    body = bytes.fromhex("8b5424089cf7c2ffffff007505baffffff009d8d8114010000c3")
    return offset, cave_offset, patch, body


def patch_bytes(data):
    offset, cave_offset, patch, body = layout(data)
    if offset is None or data[offset:offset + len(ORIGINAL)] != ORIGINAL:
        raise ValueError("riched20.dll 与验证过的 TIM 3.4.8.22124 指令不符，拒绝修改")
    if data[cave_offset:cave_offset + 32] != bytes(32):
        raise ValueError("代码洞非空，拒绝覆盖")
    result = bytearray(data)
    result[offset:offset + len(patch)] = patch
    result[cave_offset:cave_offset + len(body)] = body
    return bytes(result)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tim-dir", required=True)
    actions = ap.add_mutually_exclusive_group(required=True)
    for name in ("apply", "revert", "status"):
        actions.add_argument("--" + name, action="store_true")
    args = ap.parse_args()
    path = os.path.join(args.tim_dir, "Bin", "riched20.dll")
    backup = path + ".input-white.orig"
    with open(path, "rb") as f:
        data = f.read()
    offset, cave_offset, patch, body = layout(data)
    expected = patch + ORIGINAL[len(patch):]
    state = data[offset:offset + len(ORIGINAL)] if offset is not None else b""
    if args.status:
        print("riched20.dll input:", "PATCHED" if state == expected and
              data[cave_offset:cave_offset + len(body)] == body else
              "pristine" if state == ORIGINAL else "UNKNOWN")
        return
    if args.revert:
        if not os.path.exists(backup):
            raise SystemExit("没有输入颜色补丁备份")
        print(replace_locked(backup, path))
        return
    if state == expected and data[cave_offset:cave_offset + len(body)] == body:
        print("input text already white")
        return
    result = patch_bytes(data)
    if os.path.exists(backup):
        with open(backup, "rb") as f:
            if hashlib.sha256(f.read()).digest() != hashlib.sha256(data).digest():
                raise SystemExit("已有备份与当前原件不一致，拒绝覆盖")
    else:
        shutil.copyfile(path, backup)
    temp = path + ".input-white.tmp"
    with open(temp, "wb") as f:
        f.write(result)
    try:
        print(replace_locked(temp, path))
    finally:
        os.remove(temp)


if __name__ == "__main__":
    main()
