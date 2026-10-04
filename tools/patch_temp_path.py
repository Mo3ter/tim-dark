"""Common.dll 的 QQTempSys 路径初始化补丁计划，仅供启动器写入内存。"""
import hashlib
import struct

from patch_dll import parse_pe, rva_to_off, text_section

SHA256 = "af0bdc49ad6b53a9a07a74f8390464f31d358fdf7efd24857e1b1896a9bd5696"
SITE = 0x78082
CACHE = 0x29436C


def runtime_plan(data, directory):
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError("Common.dll 不是验证过的 TIM 3.4.8.22124 原件，拒绝修改")
    base, sections = parse_pe(data)
    _, va, vs, raw, size = text_section(sections)
    offset = rva_to_off(sections, SITE)
    expected = b"\xa1" + struct.pack("<I", base + CACHE)
    if offset is None or data[offset:offset + 5] != expected:
        raise ValueError("Common.dll 临时目录初始化指令不符")
    encoded = (directory + "\0").encode("utf-16-le")
    if len(encoded) // 2 > 260:
        raise ValueError("实际 AppData 路径超过 MAX_PATH")
    # API 已写入缓存缓冲区；在计算字符串长度与追加 QQTempSys 前覆盖根目录。
    # 两处绝对缓存地址由启动器按实际模块基址填写，其余均为相对定位。
    code = (bytes.fromhex("9c5156578b3d") + bytes(4)
            + bytes.fromhex("e8000000005e83c617b9")
            + struct.pack("<I", len(encoded) // 2)
            + bytes.fromhex("fcf366a55f5e599da1") + bytes(4) + b"\xc3")
    assert len(code) == 38
    body = code + encoded
    cave = raw + vs
    if len(body) > size - vs or data[cave:cave + len(body)] != bytes(len(body)):
        raise ValueError("Common.dll 代码洞不足或非空")
    patch = b"\xe8" + struct.pack("<i", va + vs - (SITE + 5))
    return {"site": SITE, "cache": CACHE, "cave": va + vs,
            "patch": list(patch), "body": list(body)}
