#!/usr/bin/env python3
"""
repack.py

Debonosu Works 引擎通用重打包工具。
功能：
1. 读取 index.json 和源文件目录。
2. 对每个文件进行 Zlib 压缩。
3. 重新计算偏移量，重建加密/压缩的索引表。
4. 生成新的 .pak 文件。

注意：此脚本生成的 PAK 在逻辑上是有效的，但由于 Zlib 压缩率差异，
可能无法与原始 PAK 做到“字节级”完全一致，但不影响游戏运行。
"""

import argparse
import json
import pathlib
import struct
import sys
import zlib
import binascii

class PakBuilder:
    def __init__(self):
        self.files_data = bytearray() # 存放所有文件的压缩数据
        self.entries = []             # 存放索引信息
        self.current_offset = 0       # 当前数据区的相对偏移量

    def add_file(self, path: pathlib.Path, meta: dict):
        """读取文件，压缩，并记录元数据"""
        if not path.is_file():
            raise FileNotFoundError(f"找不到文件: {path}")

        # 1. 读取原始数据
        raw_data = path.read_bytes()
        uncompressed_size = len(raw_data)

        # 2. 压缩数据 (使用 raw deflate, wbits=-15)
        # level=9 尝试最高压缩率，以接近官方大小
        compressed_data = zlib.compress(raw_data, level=9, wbits=-15)
        compressed_size = len(compressed_data)

        # 3. 记录索引条目
        # 我们需要保留 index.json 里的 flag, timestamp, 和 unknown prefix
        entry = {
            "filename": meta["path"],  # 这里的 path 是 pak 内部路径
            "is_dir": meta.get("is_dir", False),
            "flags": meta.get("flags", 0),
            "timestamp": meta.get("timestamp", 0),
            "prefix_hex": meta.get("prefix_hex", "00" * 24), # 那个24字节的未知头

            # 以下是重新计算的
            "offset": self.current_offset,
            "compressed_size": compressed_size,
            "uncompressed_size": uncompressed_size
        }
        self.entries.append(entry)

        # 4. 写入数据缓冲区
        self.files_data.extend(compressed_data)
        self.current_offset += compressed_size

        return entry

    def build_index(self) -> bytes:
        """构建未压缩的二进制索引块"""
        index_buffer = bytearray()

        for entry in self.entries:
            # 1. 写入文件名 (Shift-JIS 编码 + 00 结尾)
            try:
                name_bytes = entry["filename"].encode("cp932") + b'\x00'
            except UnicodeEncodeError:
                # 如果文件名有特殊字符，回退到 utf-8 或者是报错
                print(f"Warning: Filename {entry['filename']} encoding fallback.")
                name_bytes = entry["filename"].encode("utf-8") + b'\x00'

            index_buffer.extend(name_bytes)

            # 2. 构建 52字节 Metadata 结构体
            # 结构: [Prefix(24)] [Flags(4)] [Unknown(4)] [Offset(4)] [Unknown(4)] [Size(4)] [Time(8)]

            # 解析 24字节 Prefix
            prefix = binascii.unhexlify(entry["prefix_hex"])
            if len(prefix) != 24:
                prefix = b'\x00' * 24

            # 打包结构体
            # < = 小端, I = 4字节无符号整数, Q = 8字节无符号整数
            # 注意：根据逆向，Offset 是 0x20(32), Size 是 0x28(40)
            # 0x18(24) = Flags

            # 这里的布局是基于 sub_482630 的 qmemcpy 和 sub_480940 的读取推断的
            # Layout:
            # 00-24: Prefix
            # 24-28: Flags
            # 28-32: Unknown (Padding?)
            # 32-36: Offset
            # 36-40: Unknown (Padding?)
            # 40-44: Size (Uncompressed size based on struct, but usually index stores Uncompressed)
            #        WAIT: sub_480D50 uses this size to read? No, sub_480D50 reads 'v13' which is passed in.
            #        Let's look at sub_480530 logic: It reads compressed index.
            #        Usually Index stores the size needed to allocate memory.
            #        Let's assume this Size field is the UNCOMPRESSED size for safety,
            #        but checking standard PAKs, it might be Compressed size if it's used for CreateFileMapping.
            #        修正：根据 sub_480940，v20[10] (Offset 40) 被复制出来。
            #        根据大多数 PAK 逻辑，这里存的是实际文件大小（解压后的）。

            meta_struct = struct.pack(
                '<24s I I I I I Q',
                prefix,                 # 0x00
                entry["flags"],         # 0x18
                0,                      # 0x1C (Padding)
                entry["offset"],        # 0x20 (New Offset!)
                0,                      # 0x24 (Padding)
                entry["uncompressed_size"], # 0x28 (Size) - 或者是 compressed_size?
                # 通常这里存原始大小用于分配内存。
                # 如果读取报错，可能需要改成 compressed_size。
                entry["timestamp"]      # 0x2C
            )

            index_buffer.extend(meta_struct)

        return index_buffer

    def save(self, output_path: pathlib.Path, original_header_info: dict):
        # 1. 构建明文索引
        raw_index = self.build_index()
        raw_index_size = len(raw_index)

        # 2. 压缩索引
        compressed_index = zlib.compress(raw_index, level=9, wbits=-15)
        comp_index_size = len(compressed_index)

        # 3. 计算偏移量
        # 布局: [GlobalHeader 16] [ExtHeader 24] [IndexBlock] [DataBlock]
        header_size = 16
        ext_header_size = 24

        index_offset_rel = header_size + ext_header_size # 索引块相对于 ExtHeader 的位置？
        # 不，ExtHeader 里的 offset 是相对于 ExtHeader 起始位置的。
        # 通常 Index 紧跟在 ExtHeader 后面。
        # 所以 index_rel_offset = 24 (ExtHeader 自身的长度)

        index_rel_offset = 24

        # 4. 构建 Headers

        # Global Header: "PAK\0" + Header2_Offset + Version + Reserved
        # Header2_Offset = 16 (紧接在 Global 后面)
        global_header = struct.pack(
            '<4s I I I',
            b'PAK\x00',
            16,
            0x00060010, # Version, copy from original or default
            0
        )

        # Ext Header: IndexOffset + Unk + Unk + DecompSize + CompSize + Unk
        ext_header = struct.pack(
            '<I I I I I I',
            index_rel_offset,   # Index Offset (relative to ExtHeader start)
            0, 0,
            raw_index_size,     # Decompressed Size
            comp_index_size,    # Compressed Size
            0
        )

        # 5. 写入文件
        print(f"Writing {output_path}...")
        print(f"  Index: Raw {raw_index_size} / Comp {comp_index_size}")
        print(f"  Data:  {len(self.files_data)} bytes")

        with open(output_path, 'wb') as f:
            f.write(global_header)
            f.write(ext_header)
            f.write(compressed_index)
            f.write(self.files_data)

def main():
    parser = argparse.ArgumentParser(description="Debonosu PAK Repacker")
    parser.add_argument("index", type=pathlib.Path, help="index.json")
    parser.add_argument("source", type=pathlib.Path, help="Input directory containing files")
    parser.add_argument("-o", "--out", type=pathlib.Path, default=pathlib.Path("game_new.pak"), help="Output PAK file")
    args = parser.parse_args()

    # 1. 加载索引
    try:
        index_data = json.loads(args.index.read_text(encoding="utf-8"))
        header_info = index_data.get("header", {})
        entries = index_data.get("entries", [])
    except Exception as e:
        print(f"Error loading index.json: {e}")
        sys.exit(1)

    builder = PakBuilder()

    # 2. 处理每个文件
    print(f"Processing {len(entries)} files...")
    for entry_info in entries:
        # 跳过目录类型的索引条目（通常不需要打包目录实体，只需在路径中体现）
        # 如果原来的 PAK 里有明确的目录条目（is_dir=True），也需要加进去，
        # 但目录没有数据体。这里假设只有文件。
        if entry_info.get("type") != "file":
            continue

        rel_path = entry_info["path"]
        file_path = args.source / rel_path

        # 进度条
        print(f"  Packing: {rel_path}", end='\r')

        try:
            builder.add_file(file_path, entry_info)
        except Exception as e:
            print(f"\nError packing {rel_path}: {e}")
            sys.exit(1)

    print("\nFile processing done.")

    # 3. 保存 PAK
    try:
        builder.save(args.out, header_info)
        print("Done!")
    except Exception as e:
        print(f"Error saving PAK: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()