"""旧版 TIM 3.4.8 图片路径磁盘补丁的状态检查与还原。

只修改 TIM 的 KernelUtil.dll，不修改 Windows 目录入口或其他应用。
磁盘安装已停用；关闭 TIM 后还原备份，再使用 launch_tim.py 启动。
"""
import argparse
import pathlib
import struct

from patch_dll import parse_pe, rva_to_off, text_section, replace_locked

SITE = 0x100B23
ORIGINAL = bytes.fromhex("85c00f8401010000")


def layout(data):
    _, sections = parse_pe(data)
    _, va, vs, raw, size = text_section(sections)
    return rva_to_off(sections, SITE), raw + vs, va + vs, size - vs


def build(data, directory):
    offset, cave_offset, cave_rva, available = layout(data)
    if offset is None or data[offset:offset + len(ORIGINAL)] != ORIGINAL:
        raise ValueError("KernelUtil.dll 的指令与已验证版本不符")
    encoded = (directory + "\0").encode("utf-16-le")
    if len(encoded) // 2 > 260:
        raise ValueError("实际 AppData 路径超过 MAX_PATH")
    # 在 SHGetSpecialFolderPathW 返回后重写原来的栈内路径缓冲区。
    # 保存 esi/edi/ecx；call/pop 获取相对数据地址，无新增重定位。
    code = (bytes.fromhex("5657518dbd64fcffffe8000000005e8d7618b9")
            + struct.pack("<I", len(encoded) // 2)
            + bytes.fromhex("fcf366a5595f5eb80100000085c0c3"))
    assert len(code) == 38
    body = code + encoded
    if len(body) > available or data[cave_offset:cave_offset + len(body)] != bytes(len(body)):
        raise ValueError("KernelUtil.dll 代码洞不够或已有其他内容")
    patch = b"\xe8" + struct.pack("<i", cave_rva - (SITE + 5)) + b"\x90" * 3
    result = bytearray(data)
    result[offset:offset + len(patch)] = patch
    result[cave_offset:cave_offset + len(body)] = body
    return bytes(result)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tim-dir", required=True)
    ap.add_argument("--appdata-dir")
    actions = ap.add_mutually_exclusive_group(required=True)
    for action in ("apply", "status", "revert"):
        actions.add_argument("--" + action, action="store_true")
    args = ap.parse_args()
    if args.apply:
        raise SystemExit("磁盘补丁可能触发 TIM 的 crsignv 文件检查；请先 --revert，再使用 launch_tim.py")
    dll = pathlib.Path(args.tim_dir) / "Bin" / "KernelUtil.dll"
    backup = dll.with_name(dll.name + ".paste-path.orig")
    data = dll.read_bytes()
    offset, cave_offset, cave_rva, _ = layout(data)
    patch = b"\xe8" + struct.pack("<i", cave_rva - (SITE + 5)) + b"\x90" * 3
    state = data[offset:offset + 8] if offset is not None else b""
    if args.status:
        print("KernelUtil.dll paste path:", "PATCHED" if state == patch else
              "pristine" if state == ORIGINAL else "UNKNOWN")
        return
    if args.revert:
        if not backup.exists():
            raise SystemExit("没有图片路径补丁备份")
        if backup.read_bytes()[offset:offset + 8] != ORIGINAL:
            raise SystemExit("备份不是验证过的原始 DLL")
        print(replace_locked(str(backup), str(dll)))
        return


if __name__ == "__main__":
    main()
