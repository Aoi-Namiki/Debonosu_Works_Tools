#!/usr/bin/env python3

import argparse
import json
import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple

def collect_strings_from_chunk(data: bytes) -> List[bytes]:
    def read_header(data: bytes):
        if data[:4] != b"\x1bLua":
            raise ValueError("not a Lua 5.1 chunk")
        if len(data) < 12:
            raise ValueError("header too short")
        _sig, _ver, _fmt, endi, isz, ssz, insz, nsz, _iflag = struct.unpack("4sBBBBBBBB", data[:12])
        endian_prefix = "<" if endi == 1 else ">"
        return endian_prefix, isz, ssz, insz, nsz

    def read_int(data, endian, size, pos):
        if size == 4:
            val = struct.unpack_from(endian + "i", data, pos)[0]
        elif size == 8:
            val = struct.unpack_from(endian + "q", data, pos)[0]
        else:
            raise ValueError("unsupported int size")
        return val, pos + size

    def read_size_t(data, endian, size, pos):
        if size == 4:
            val = struct.unpack_from(endian + "I", data, pos)[0]
        elif size == 8:
            val = struct.unpack_from(endian + "Q", data, pos)[0]
        else:
            raise ValueError("unsupported size_t size")
        return val, pos + size

    def read_lstring_raw(data, endian, size_t_size, pos):
        n, pos = read_size_t(data, endian, size_t_size, pos)
        if n == 0:
            return None, pos
        raw = data[pos:pos + n - 1]
        pos += n
        return bytes(raw), pos

    def collect_proto(data, endian, int_size, size_t_size, instr_size, number_size, pos, out_list):
        _, pos = read_lstring_raw(data, endian, size_t_size, pos)
        _, pos = read_int(data, endian, int_size, pos)
        _, pos = read_int(data, endian, int_size, pos)
        pos += 4
        sizecode, pos = read_int(data, endian, int_size, pos)
        pos += sizecode * instr_size
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
                s, pos = read_lstring_raw(data, endian, size_t_size, pos)
                if s is not None:
                    out_list.append(s)
                continue
            raise ValueError("unknown constant type")
        sizep, pos = read_int(data, endian, int_size, pos)
        for _ in range(sizep):
            pos = collect_proto(data, endian, int_size, size_t_size, instr_size, number_size, pos, out_list)
        sizelineinfo, pos = read_int(data, endian, int_size, pos)
        pos += sizelineinfo * int_size
        sizelocvars, pos = read_int(data, endian, int_size, pos)
        for _ in range(sizelocvars):
            _, pos = read_lstring_raw(data, endian, size_t_size, pos)
            pos += int_size * 2
        sizeupvalues, pos = read_int(data, endian, int_size, pos)
        for _ in range(sizeupvalues):
            _, pos = read_lstring_raw(data, endian, size_t_size, pos)
        return pos

    mv = memoryview(data)
    endian, int_size, size_t_size, instr_size, number_size = read_header(data)
    strings = []
    _ = collect_proto(mv, endian, int_size, size_t_size, instr_size, number_size, 12, strings)
    return strings

def detect_encoding_from_strings(strings: List[bytes]) -> str:
    if not strings:
        return 'shift_jis'
    utf8_ok = True
    has_non_ascii = False
    for s in strings:
        try:
            decoded = s.decode('utf-8', errors='strict')
            if any(ord(c) > 127 for c in decoded):
                has_non_ascii = True
        except UnicodeDecodeError:
            utf8_ok = False
            break
    if utf8_ok and has_non_ascii:
        return 'utf-8'
    else:
        return 'shift_jis'

def detect_encoding_for_file(path: Path) -> str:
    data = path.read_bytes()
    strings = collect_strings_from_chunk(data)
    return detect_encoding_from_strings(strings)

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
    try:
        cur_text = raw.decode(src_enc, errors="strict")
    except Exception:
        cur_text = raw.decode(src_enc, errors="replace")
    cur_disp = cur_text.replace("\r", "\\r").replace("\n", "\\n")
    if new == cur_disp:
        return raw
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
        obj = e.object
        start = e.start
        end = e.end
        bad_char = obj[start:end]
        print(f"[FAIL] {in_path.name}: 无法编码字符 '{bad_char}' 使用编码 {e.encoding}")
        with open("Errors.log", "a", encoding="utf-8") as log:
            log.write(f"{in_path.name}: 无法编码字符 '{bad_char}' 使用编码 {e.encoding}\n")
        return
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(bytes(out))

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
            if txt.startswith(" "):
                txt = txt[1:]
            mapping[idx] = txt
        except Exception:
            continue
    return mapping

def main() -> None:
    ap = argparse.ArgumentParser(description="import map.json into Lua 5.1 chunk constant strings")
    ap.add_argument("input", type=Path, help="input .scb/.luac or directory")
    ap.add_argument("map", type=Path, help="mapping txt (single) or directory of txt (folder); use ●INDEX● newtext")
    ap.add_argument("output", type=Path, help="output file (single) or output directory (folder)")
    ap.add_argument("--src-encoding", default="shift_jis", help="decode existing strings with this encoding (default shift_jis, use 'auto' to auto-detect)")
    ap.add_argument("--dst-encoding", default="shift_jis", help="encode new strings with this encoding (default shift_jis, use 'auto' to use same as src-encoding)")
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
                if txt.startswith(" "):
                    txt = txt[1:]
                mapping[idx] = txt
            except Exception:
                continue
        return mapping

    in_path = args.input
    out_path = args.output
    map_dir = args.map if args.map.is_dir() else None

    src_auto = (args.src_encoding == "auto")
    dst_auto = (args.dst_encoding == "auto")

    if in_path.is_file():
        if map_dir:
            raise SystemExit("Single .scb import requires a mapping file, not a directory")
        if src_auto:
            src_enc = detect_encoding_for_file(in_path)
        else:
            src_enc = args.src_encoding
        if dst_auto:
            dst_enc = src_enc
        else:
            dst_enc = args.dst_encoding
        mapping = load_mapping(args.map)
        patch_file(in_path, out_path, mapping, src_enc, dst_enc)
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
            if src_auto:
                src_enc = detect_encoding_for_file(scb)
            else:
                src_enc = args.src_encoding
            if dst_auto:
                dst_enc = src_enc
            else:
                dst_enc = args.dst_encoding

            if map_dir:
                map_txt = (map_dir / rel).with_suffix(rel.suffix + ".txt")
                if not map_txt.exists():
                    print(f"[SKIP] {rel}: mapping not found")
                    continue
                mapping_cur = load_mapping(map_txt)
            else:
                mapping_cur = mapping_all
            patch_file(scb, dst, mapping_cur, src_enc, dst_enc)
            print(f"[OK] {rel} -> {dst}")
        except Exception as exc:
            print(f"[FAIL] {rel}: {exc}")

def default_batch_patch():
    script_dir = Path("./script")
    txt_dir = Path("./txt")
    out_dir = Path("./new_script/script")
    if not script_dir.exists():
        print("Error: ./script directory not found")
        return
    if not txt_dir.exists():
        print("Error: ./txt directory not found")
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    for scb in script_dir.rglob("*.scb"):
        rel = scb.relative_to(script_dir)
        txt_path = (txt_dir / rel).with_suffix(".txt")
        if not txt_path.exists():
            print(f"[SKIP] {rel}: mapping not found")
            continue
        dst = out_dir / rel
        src_enc = detect_encoding_for_file(scb)
        dst_enc = src_enc
        mapping = load_mapping(txt_path)
        patch_file(scb, dst, mapping, src_enc, dst_enc)
        print(f"[OK] {rel} -> {dst}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) == 1:
        default_batch_patch()
    else:
        main()
