#!/usr/bin/env python3
import argparse
import pathlib
import struct
import sys
import zlib


class PakError(Exception):
    """ERROR"""


def read_header(pak_bytes: bytes):
    """
    读取并验证 PAK 头。
    - 偏移 0: "PAK\0"
    - 偏移 4: 扩展头偏移（在原程序里按 1 字节读，这里仍取 32 位方便处理）
    - 扩展头 24 字节: index 相对偏移、根节点数量、索引原始/压缩大小等。
    """
    if len(pak_bytes) < 16:
        raise PakError("文件长度不足 16 字节，无法包含 PAK 头")

    magic, raw_header, _r1, _r2 = struct.unpack_from("<4sIII", pak_bytes, 0)
    if magic != b"PAK\x00":
        raise PakError(f"魔数不匹配: {magic!r}")

    header_offset = raw_header & 0xFFFF
    candidates = [header_offset]
    if raw_header not in candidates:
        candidates.append(raw_header)

    for candidate in candidates:
        if candidate + 24 > len(pak_bytes):
            continue
        ext = pak_bytes[candidate : candidate + 24]
        idx_rel, unk1, root_count, idx_u, idx_c, unk2 = struct.unpack("<6I", ext)
        idx_off = candidate + idx_rel
        data_off = idx_off + idx_c
        if idx_u and idx_c and data_off <= len(pak_bytes):
            return {
                "header_offset": candidate,
                "index_rel": idx_rel,
                "root_count": root_count,
                "index_uncompressed": idx_u,
                "index_compressed": idx_c,
                "index_offset": idx_off,
                "data_offset": data_off,
                "unknown1": unk1,
                "unknown2": unk2,
            }

    raise PakError("未找到合法的扩展头")


def parse_entries(index_data: bytes, start: int, count: int, prefix: pathlib.Path):
    """
    递归解析索引。
    - 每个条目：offset(int64) + usize(int64) + csize(int64) + flags(uint32) + time(24 bytes) + Shift-JIS 名字\0
    - flags & 0x10 表示目录，usize 存放子项数量；否则为文件，offset/usize/csize 为文件参数。
    """
    pos = start
    entries = []

    for _ in range(count):
        if pos + 52 > len(index_data):
            raise PakError("索引数据不足，读条目头失败")

        offset, usize, csize, flags, time_bytes = struct.unpack_from("<QQQI24s", index_data, pos)
        name_end = index_data.find(b"\x00", pos + 52)
        if name_end == -1:
            raise PakError("文件名未找到结尾的 0 字节")

        name = index_data[pos + 52 : name_end].decode("shift_jis", errors="replace")
        pos = name_end + 1

        attrs = flags
        path = prefix / name if prefix != pathlib.Path() else pathlib.Path(name)

        if attrs & 0x10:
            child_count = usize
            entries.append({"type": "dir", "path": path, "child_count": child_count, "attributes": attrs, "time_bytes": time_bytes})
            pos, child_entries = parse_entries(index_data, pos, child_count, path)
            entries.extend(child_entries)
        else:
            entries.append(
                {
                    "type": "file",
                    "path": path,
                    "offset": offset,
                    "compressed_size": csize,
                    "uncompressed_size": usize,
                    "attributes": attrs,
                    "time_bytes": time_bytes,
                }
            )

    return pos, entries


def extract_file(pak_bytes: bytes, entry, base_offset: int, out_dir: pathlib.Path):
    """按索引信息切出数据段，必要时用 raw DEFLATE 解压，再落盘。"""
    abs_off = base_offset + entry["offset"]
    csize = entry["compressed_size"]
    usize = entry["uncompressed_size"]

    if abs_off + csize > len(pak_bytes):
        raise PakError(f"{entry['path']}: 读取范围越界 (offset {abs_off}, size {csize})")

    payload = pak_bytes[abs_off : abs_off + csize]

    if csize != usize:
        try:
            payload = zlib.decompress(payload, wbits=-15)
        except zlib.error as exc:
            raise PakError(f"{entry['path']}: 解压失败: {exc}") from exc

    if len(payload) != usize:
        raise PakError(
            f"{entry['path']}: 解压后尺寸不一致，期望 {usize} 实际 {len(payload)}"
        )

    target = out_dir / entry["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)


def main():
    parser = argparse.ArgumentParser(description="Extract .pak file contents")
    parser.add_argument("pak", type=pathlib.Path, help="input .pak file path")
    parser.add_argument("out", type=pathlib.Path, help="output directory path")
    args = parser.parse_args()

    if args.pak.suffix.lower() != '.pak':
        print("Error: Input file must have a .pak extension", file=sys.stderr)
        sys.exit(1)

    pak_bytes = args.pak.read_bytes()
    meta = read_header(pak_bytes)

    index_blob = pak_bytes[meta["index_offset"] : meta["index_offset"] + meta["index_compressed"]]
    index_data = zlib.decompress(index_blob, wbits=-15)
    if len(index_data) != meta["index_uncompressed"]:
        raise PakError(
            f"索引尺寸不符，期望 {meta['index_uncompressed']} 实际 {len(index_data)}"
        )

    _, entries = parse_entries(index_data, 0, meta["root_count"], pathlib.Path())
    files = [e for e in entries if e["type"] == "file"]
    dirs = [e for e in entries if e["type"] == "dir"]

    print(f"Header offset: 0x{meta['header_offset']:X}")
    print(f"Index: off=0x{meta['index_offset']:X}, compressed={meta['index_compressed']}, uncompressed={meta['index_uncompressed']}")
    print(f"Data section starts at 0x{meta['data_offset']:X}")
    print(f"Entries: {len(files)} files, {len(dirs)} directories")

    for entry in files:
        extract_file(pak_bytes, entry, meta["data_offset"], args.out)

    print(f"Done. Extracted to {args.out}")


if __name__ == "__main__":
    try:
        main()
    except PakError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
