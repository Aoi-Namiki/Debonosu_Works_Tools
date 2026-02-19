#!/usr/bin/env python3
"""
将 map.json 的字符串映射写入 Lua 5.1 chunk (.scb/.luac) 的常量表（不反编译/重编译）。
支持单文件或文件夹（保留目录结构写入输出目录）。
"""

import argparse
import json
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def read_header(data: bytes) -> tuple:
    if data[:4] != b"\x1bLua":
        raise ValueError("not a Lua 5.1 chunk (missing \\x1bLua)")
    if len(data) < 12:
        raise ValueError("header too short")
    _sig, _ver, _fmt, endi, isz, ssz, insz, nsz, _iflag = struct.unpack("4sBBBBBBBB", data[:12])
    endian_prefix = "<" if endi == 1 else ">"
    return endian_prefix, isz, ssz, insz, nsz


def read_int(data: memoryview, endian: str, size: int, pos: int) -> tuple:
    if size == 4:
        val = struct.unpack_from(endian + "i", data, pos)[0]
    elif size == 8:
        val = struct.unpack_from(endian + "q", data, pos)[0]
    else:
        raise ValueError("unsupported int size")
    return val, pos + size


def write_int(buf: bytearray, endian: str, size: int, val: int) -> None:
    if size == 4:
        buf.extend(struct.pack(endian + "i", val))
        return
    if size == 8:
        buf.extend(struct.pack(endian + "q", val))
        return
    raise ValueError("unsupported int size")


def read_size_t(data: memoryview, endian: str, size: int, pos: int) -> tuple:
    if size == 4:
        val = struct.unpack_from(endian + "I", data, pos)[0]
    elif size == 8:
        val = struct.unpack_from(endian + "Q", data, pos)[0]
    else:
        raise ValueError("unsupported size_t size")
    return val, pos + size


def write_size_t(buf: bytearray, endian: str, size: int, val: int) -> None:
    if size == 4:
        buf.extend(struct.pack(endian + "I", val))
        return
    if size == 8:
        buf.extend(struct.pack(endian + "Q", val))
        return
    raise ValueError("unsupported size_t size")


def read_lstring(data: memoryview, endian: str, size_t_size: int, pos: int) -> tuple:
    n, pos = read_size_t(data, endian, size_t_size, pos)
    if n == 0:
        return None, pos
    raw = data[pos : pos + n]
    pos += n
    return bytes(raw[:-1]), pos


def write_lstring(buf: bytearray, endian: str, size_t_size: int, s: Optional[bytes]) -> None:
    if s is None:
        write_size_t(buf, endian, size_t_size, 0)
        return
    write_size_t(buf, endian, size_t_size, len(s) + 1)
    buf.extend(s)
    buf.append(0)


def patch_const_string(raw: bytes, idx: int, mapping: Dict[int, str], src_enc: str, dst_enc: str) -> bytes:
    new = mapping.get(idx)
    if new is None:
        return raw
    # 计算当前常量的“导出格式”文本，用于判断是否未修改
    try:
        cur_text = raw.decode(src_enc, errors="strict")
    except Exception:
        cur_text = raw.decode(src_enc, errors="replace")
    cur_disp = cur_text.replace("\r", "\\r").replace("\n", "\\n")
    if new == cur_disp:
        return raw  # 未改动，保持原字节
    new_text = new.replace("\\r", "\r").replace("\\n", "\n")
    return new_text.encode(dst_enc, errors="strict")


def process_proto(
    data: memoryview,
    endian: str,
    int_size: int,
    size_t_size: int,
    instr_size: int,
    number_size: int,
    pos: int,
    mapping: Dict[int, str],
    src_enc: str,
    dst_enc: str,
    out: bytearray,
    counter: List[int],
) -> int:
    name, pos = read_lstring(data, endian, size_t_size, pos)
    write_lstring(out, endian, size_t_size, name)

    a, pos = read_int(data, endian, int_size, pos)
    b, pos = read_int(data, endian, int_size, pos)
    write_int(out, endian, int_size, a)
    write_int(out, endian, int_size, b)

    out.extend(data[pos : pos + 4])
    pos += 4

    sizecode, pos = read_int(data, endian, int_size, pos)
    write_int(out, endian, int_size, sizecode)
    out.extend(data[pos : pos + sizecode * instr_size])
    pos += sizecode * instr_size

    sizek, pos = read_int(data, endian, int_size, pos)
    write_int(out, endian, int_size, sizek)
    for _ in range(sizek):
        t = data[pos]
        out.append(t)
        pos += 1
        if t == 0:
            continue
        if t == 1:
            out.extend(data[pos : pos + 1])
            pos += 1
            continue
        if t == 3:
            out.extend(data[pos : pos + number_size])
            pos += number_size
            continue
        if t == 4:
            s, pos = read_lstring(data, endian, size_t_size, pos)
            if s is not None:
                counter[0] += 1
                s = patch_const_string(s, counter[0], mapping, src_enc, dst_enc)
            write_lstring(out, endian, size_t_size, s)
            continue
        raise ValueError("unknown constant type")

    sizep, pos = read_int(data, endian, int_size, pos)
    write_int(out, endian, int_size, sizep)
    for _ in range(sizep):
        pos = process_proto(
            data,
            endian,
            int_size,
            size_t_size,
            instr_size,
            number_size,
            pos,
            mapping,
            src_enc,
            dst_enc,
            out,
            counter,
        )

    sizelineinfo, pos = read_int(data, endian, int_size, pos)
    write_int(out, endian, int_size, sizelineinfo)
    out.extend(data[pos : pos + sizelineinfo * int_size])
    pos += sizelineinfo * int_size

    sizelocvars, pos = read_int(data, endian, int_size, pos)
    write_int(out, endian, int_size, sizelocvars)
    for _ in range(sizelocvars):
        s, pos = read_lstring(data, endian, size_t_size, pos)
        write_lstring(out, endian, size_t_size, s)
        a, pos = read_int(data, endian, int_size, pos)
        b, pos = read_int(data, endian, int_size, pos)
        write_int(out, endian, int_size, a)
        write_int(out, endian, int_size, b)

    sizeup, pos = read_int(data, endian, int_size, pos)
    write_int(out, endian, int_size, sizeup)
    for _ in range(sizeup):
        s, pos = read_lstring(data, endian, size_t_size, pos)
        write_lstring(out, endian, size_t_size, s)
    return pos


def patch_file(in_path: Path, out_path: Path, mapping: Dict[int, str], src_enc: str, dst_enc: str) -> None:
    data = in_path.read_bytes()
    # 如果没有映射条目，直接拷贝原文件
    if not mapping:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(data)
        return

    endian, int_size, size_t_size, instr_size, number_size = read_header(data)
    mv = memoryview(data)
    out = bytearray()
    out.extend(data[:12])
    try:
        _ = process_proto(
            mv,
            endian,
            int_size,
            size_t_size,
            instr_size,
            number_size,
            12,
            mapping,
            src_enc,
            dst_enc,
            out,
            [-1],
        )
    except UnicodeEncodeError as e:
        # 提取无法编码的具体字符
        obj = e.object
        start = e.start
        end = e.end
        bad_char = obj[start:end]  # 无法编码的字符片段
        print(f"[FAIL] {in_path.name}: 无法编码字符 '{bad_char}' 使用编码 {e.encoding}")
        # 跳过此文件，不写入输出
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(bytes(out))


def main() -> None:
    ap = argparse.ArgumentParser(description="import map.json into Lua 5.1 chunk constant strings")
    ap.add_argument("input", type=Path, help="input .scb/.luac or directory")
    ap.add_argument("map", type=Path, help="mapping txt (single) or directory of txt (folder); use ●INDEX● newtext")
    ap.add_argument("output", type=Path, help="output file (single) or output directory (folder)")
    ap.add_argument("--src-encoding", default="shift_jis", help="decode existing strings with this encoding")
    ap.add_argument("--dst-encoding", default="shift_jis", help="encode new strings with this encoding")
    args = ap.parse_args()

    def load_mapping(path: Path) -> Dict[int, str]:
        data = path.read_bytes()
        text = None
        for enc in ("utf-8", "utf-8-sig", "shift_jis", "cp936"):
            try:
                text = data.decode(enc)
                break
            except Exception:
                continue
        if text is None:
            text = data.decode("utf-8", errors="replace")

        mapping: Dict[int, str] = {}
        for line in text.splitlines():
            if not line.startswith("●"):
                continue
            try:
                head, txt = line[1:].split("●", 1)
                idx = int(head)
                # 提取后的格式是「●00000● 文本」，仅移除分隔用的单个空格，其余空格原样保留
                if txt.startswith(" "):
                    txt = txt[1:]
                mapping[idx] = txt
            except Exception:
                continue
        return mapping

    in_path = args.input
    out_path = args.output
    map_dir = args.map if args.map.is_dir() else None

    if in_path.is_file():
        if map_dir:
            raise SystemExit("Single .scb import requires a mapping file, not a directory")
        mapping = load_mapping(args.map)
        patch_file(in_path, out_path, mapping, args.src_encoding, args.dst_encoding)
        return

    if not in_path.is_dir():
        raise SystemExit(f"Input not found: {in_path}")

    if not out_path:
        raise SystemExit("Folder input requires output directory")
    out_path.mkdir(parents=True, exist_ok=True)
    mapping_all = None
    if map_dir is None:
        if not args.map.is_file():
            raise SystemExit(f"Map path invalid: {args.map}")
        mapping_all = load_mapping(args.map)

    for scb in sorted(in_path.rglob("*.scb")):
        rel = scb.relative_to(in_path)
        dst = out_path / rel
        try:
            if map_dir:
                map_txt = (map_dir / rel).with_suffix(rel.suffix + ".txt")
                if not map_txt.exists():
                    print(f"[SKIP] {rel}: mapping not found")
                    continue
                mapping_cur = load_mapping(map_txt)
            else:
                mapping_cur = mapping_all
            patch_file(scb, dst, mapping_cur, args.src_encoding, args.dst_encoding)
            print(f"[OK] {rel} -> {dst}")
        except Exception as exc:
            print(f"[FAIL] {rel}: {exc}")


if __name__ == "__main__":
    main()
