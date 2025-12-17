#!/usr/bin/env python3
"""
从 Lua 5.1 chunk (.scb/.luac) 中提取常量字符串，不反编译/重编译。
支持单文件（输出到 stdout 或 -o）和文件夹（按结构写入每个 .txt）。
输出格式示例：
○00000○ 原文
●00000● 原文（便于编辑替换）
"""

import argparse
import struct
from pathlib import Path
from typing import List, Optional


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


def read_size_t(data: memoryview, endian: str, size: int, pos: int) -> tuple:
    if size == 4:
        val = struct.unpack_from(endian + "I", data, pos)[0]
    elif size == 8:
        val = struct.unpack_from(endian + "Q", data, pos)[0]
    else:
        raise ValueError("unsupported size_t size")
    return val, pos + size


def read_lstring(data: memoryview, endian: str, size_t_size: int, pos: int) -> tuple:
    n, pos = read_size_t(data, endian, size_t_size, pos)
    if n == 0:
        return None, pos, None, 0
    raw_pos = pos
    raw = data[pos : pos + n]
    pos += n
    return bytes(raw[:-1]), pos, raw_pos, n - 1  # exclude null terminator


def process_proto(
    data: memoryview,
    endian: str,
    int_size: int,
    size_t_size: int,
    instr_size: int,
    number_size: int,
    pos: int,
    out: List[str],
    encoding: str,
    counter: List[int],
) -> int:
    _, pos, _, _ = read_lstring(data, endian, size_t_size, pos)  # source name
    _, pos = read_int(data, endian, int_size, pos)  # line_defined
    _, pos = read_int(data, endian, int_size, pos)  # last_line_defined
    pos += 4  # nups,numparams,is_vararg,maxstacksize
    sizecode, pos = read_int(data, endian, int_size, pos)
    pos += sizecode * instr_size  # instructions
    sizek, pos = read_int(data, endian, int_size, pos)
    for _ in range(sizek):
        t = data[pos]
        pos += 1
        if t == 0:
            continue
        if t == 1:
            pos += 1
            continue
        if t == 3:
            pos += number_size
            continue
        if t == 4:
            s, pos, raw_pos, raw_len = read_lstring(data, endian, size_t_size, pos)
            if s is not None:
                counter[0] += 1
                try:
                    text = s.decode(encoding, errors="strict")
                except Exception:
                    text = s.decode(encoding, errors="replace")
                # 将换行转义为 \r \n，保持单行便于编辑
                text_disp = text.replace("\r", "\\r").replace("\n", "\\n")
                out.append(f"○{counter[0]:05d}○ {text_disp}")
                out.append(f"●{counter[0]:05d}● {text_disp}")
            continue
        raise ValueError("unknown constant type")
    sizep, pos = read_int(data, endian, int_size, pos)
    for _ in range(sizep):
        pos = process_proto(
            data, endian, int_size, size_t_size, instr_size, number_size, pos, out, encoding, counter
        )
    sizelineinfo, pos = read_int(data, endian, int_size, pos)
    pos += sizelineinfo * int_size
    sizelocvars, pos = read_int(data, endian, int_size, pos)
    for _ in range(sizelocvars):
        _, pos, _, _ = read_lstring(data, endian, size_t_size, pos)
        pos += int_size * 2
    sizeupvalues, pos = read_int(data, endian, int_size, pos)
    for _ in range(sizeupvalues):
        _, pos, _, _ = read_lstring(data, endian, size_t_size, pos)
    return pos


def main() -> None:
    ap = argparse.ArgumentParser(description="extract constant strings from Lua 5.1 chunk (.scb/.luac)")
    ap.add_argument("input", type=Path, help=".scb/.luac file or directory")
    ap.add_argument("-o", "--out", type=Path, help="output file (for single input) or output directory (for folder)")
    ap.add_argument("--src-encoding", default="shift_jis", help="decode strings with this encoding (default shift_jis)")
    args = ap.parse_args()

    in_path = args.input
    if in_path.is_file():
        data = in_path.read_bytes()
        endian, int_size, size_t_size, instr_size, number_size = read_header(data)
        mv = memoryview(data)
        strings: List[str] = []
        _ = process_proto(
            mv,
            endian,
            int_size,
            size_t_size,
            instr_size,
            number_size,
            12,
            strings,
            args.src_encoding,
            [-1],
        )
        blocks = ["\n".join(strings[i : i + 2]) for i in range(0, len(strings), 2)]
        lines = "\n\n".join(blocks)
        if args.out:
            out_path = args.out
            if out_path.suffix.lower() != ".txt":
                out_path = out_path.with_suffix(out_path.suffix + ".txt")
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(lines, encoding="utf-8", newline="\n")
        else:
            print(lines)
        return

    if not in_path.is_dir():
        raise SystemExit(f"Input not found: {in_path}")
    if args.out is None:
        raise SystemExit("Folder input requires -o/--out as output directory for per-file .txt")
    out_dir = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    for scb in sorted(in_path.rglob("*.scb")):
        data = scb.read_bytes()
        try:
            endian, int_size, size_t_size, instr_size, number_size = read_header(data)
        except Exception as exc:
            print(f"[SKIP] {scb}: {exc}")
            continue
        mv = memoryview(data)
        strings: List[str] = []
        _ = process_proto(
            mv,
            endian,
            int_size,
            size_t_size,
            instr_size,
            number_size,
            12,
            strings,
            args.src_encoding,
            [-1],
        )
        rel = scb.relative_to(in_path)
        dst = (out_dir / rel).with_suffix(rel.suffix + ".txt")  # e.g. foo.scb.txt
        dst.parent.mkdir(parents=True, exist_ok=True)
        blocks = ["\n".join(strings[i : i + 2]) for i in range(0, len(strings), 2)]
        dst.write_text("\n\n".join(blocks), encoding="utf-8", newline="\n")
        print(f"[OK] {rel} -> {dst}")


if __name__ == "__main__":
    main()
