#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tencent RDB (resource bundle) unpack / repack.

Format (from binbyu/rdbext + reverse engineering):
  struct rdb_header {           // 36 bytes, #pragma pack(4)
      char  flag[16];           // "531E98204F8542F0"
      int32 item_count;
      int64 header_size;        // == 36
      int64 item_name_size;     // bytes of the interleaved (name + index) table
  };
  then, for each item, consecutively:
      wchar_t name[];  // UTF-16LE, NUL terminated
      struct { int64 offset; int64 size; };   // offset relative to (header_size + item_name_size)
  then payload area.

Usage:
  python rdb.py list   <file.rdb>
  python rdb.py unpack <file.rdb> <outdir>
  python rdb.py pack   <outdir> <file.rdb> [--manifest orig.json]
"""
import os
import struct
import sys

MAGIC = b"531E98204F8542F0"
HEADER_SIZE = 36


def read_items(path):
    with open(path, "rb") as f:
        data = f.read()
    if data[:16] != MAGIC:
        raise ValueError("bad magic: %r" % data[:16])
    (count,) = struct.unpack_from("<i", data, 16)
    (header_size,) = struct.unpack_from("<q", data, 20)
    (name_size,) = struct.unpack_from("<q", data, 28)
    base = header_size + name_size
    items = []
    off = header_size
    for _ in range(count):
        end = off
        while data[end:end + 2] != b"\x00\x00":
            end += 2
        name = data[off:end].decode("utf-16-le")
        off = end + 2
        (coff,) = struct.unpack_from("<q", data, off)
        (csize,) = struct.unpack_from("<q", data, off + 8)
        off += 16
        items.append({"name": name, "offset": coff, "size": csize,
                      "data": data[base + coff: base + coff + csize]})
    return items, header_size, name_size, count, len(data)


def cmd_list(path):
    items, hs, ns, count, total = read_items(path)
    print("file=%s  bytes=%d  count=%d  header_size=%d  name_size=%d  databegin=%d"
          % (path, total, count, hs, ns, hs + ns))
    for it in items:
        print("  %-8d %s" % (it["size"], it["name"]))


def cmd_unpack(path, outdir):
    items, hs, ns, count, total = read_items(path)
    for it in items:
        dest = os.path.join(outdir, it["name"].replace("\\", os.sep))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(it["data"])
    print("unpacked %d items to %s" % (len(items), outdir))


def cmd_pack(src, dst, manifest=None):
    """Pack every file under src into an rdb. If manifest (a previously unpacked
    rdb) is given, the item list and order are taken from it so that the output
    keeps the exact same layout."""
    items = []
    if manifest:
        old, hs, ns, count, total = read_items(manifest)
        order = [(it["name"], it["size"]) for it in old]
        names = [n for n, _ in order]
    else:
        names = []
        for root, _dirs, files in os.walk(src):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, src)
                names.append(rel.replace(os.sep, "\\"))
        names.sort()
    for name in names:
        full = os.path.join(src, name.replace("\\", os.sep))
        with open(full, "rb") as f:
            items.append((name, f.read()))

    table = bytearray()
    blob = bytearray()
    for name, payload in items:
        table += name.encode("utf-16-le") + b"\x00\x00"
        table += struct.pack("<qq", len(blob), len(payload))
        blob += payload
    header = MAGIC + struct.pack("<iqq", len(items), HEADER_SIZE, len(table))
    assert len(header) == HEADER_SIZE
    with open(dst, "wb") as f:
        f.write(header)
        f.write(table)
        f.write(blob)
    print("packed %d items -> %s (%d bytes)" % (len(items), dst, len(header) + len(table) + len(blob)))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    cmd = sys.argv[1]
    if cmd == "list":
        cmd_list(sys.argv[2])
    elif cmd == "unpack":
        os.makedirs(sys.argv[3], exist_ok=True)
        cmd_unpack(sys.argv[2], sys.argv[3])
    elif cmd == "pack":
        man = None
        if "--manifest" in sys.argv:
            man = sys.argv[sys.argv.index("--manifest") + 1]
        cmd_pack(sys.argv[2], sys.argv[3], man)
    else:
        print(__doc__)
        sys.exit(2)
