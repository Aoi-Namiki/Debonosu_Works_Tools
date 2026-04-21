import os
import sys
import struct
import zlib
from pathlib import Path

class DebonosuPAKUnpack:
    MAGIC = b'PAK\x00'

    @staticmethod
    def _deflate_decompress(data: bytes) -> bytes:
        decompressor = zlib.decompressobj(wbits=-15)
        return decompressor.decompress(data) + decompressor.flush()

    @staticmethod
    def unpack(pak_path: str, output_dir: str):
        with open(pak_path, 'rb') as f:
            data = f.read()

        if data[:4] != DebonosuPAKUnpack.MAGIC:
            raise ValueError("Not a valid Debonosu PAK file")

        index_offset = struct.unpack_from('<H', data, 4)[0]
        if struct.unpack_from('<H', data, 10)[0] != 0:
            raise ValueError("Invalid header at offset 10")

        info_size = struct.unpack_from('<I', data, index_offset)[0]
        root_count = struct.unpack_from('<i', data, index_offset + 8)[0]
        unpacked_size = struct.unpack_from('<I', data, index_offset + 12)[0]
        packed_size = struct.unpack_from('<I', data, index_offset + 16)[0]

        index_start = index_offset + info_size
        packed_index = data[index_start:index_start + packed_size]
        raw_index = DebonosuPAKUnpack._deflate_decompress(packed_index)
        if len(raw_index) != unpacked_size:
            print(f"Warning: unpacked index size mismatch ({len(raw_index)} vs {unpacked_size})")

        base_offset = index_start + packed_size
        reader = IndexReader(raw_index, base_offset)
        entries = reader.read_root(root_count)

        os.makedirs(output_dir, exist_ok=True)
        for entry in entries:
            out_path = os.path.join(output_dir, entry.name)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            compressed = data[entry.offset:entry.offset + entry.size]
            if entry.is_packed:
                decompressed = DebonosuPAKUnpack._deflate_decompress(compressed)
                if len(decompressed) != entry.unpacked_size:
                    print(f"Warning: size mismatch for {entry.name}")
                with open(out_path, 'wb') as f:
                    f.write(decompressed)
            else:
                with open(out_path, 'wb') as f:
                    f.write(compressed)
            print(f"Extracted: {entry.name}")


class IndexReader:
    def __init__(self, data: bytes, base_offset: int):
        self.data = data
        self.pos = 0
        self.base_offset = base_offset

    def read_int64(self) -> int:
        val = struct.unpack_from('<q', self.data, self.pos)[0]
        self.pos += 8
        return val

    def read_uint32(self) -> int:
        val = struct.unpack_from('<I', self.data, self.pos)[0]
        self.pos += 4
        return val

    def read_uint64(self) -> int:
        val = struct.unpack_from('<Q', self.data, self.pos)[0]
        self.pos += 8
        return val

    def read_name(self) -> str:
        name_bytes = []
        while True:
            b = self.data[self.pos]
            self.pos += 1
            if b == 0:
                break
            name_bytes.append(b)
        return bytes(name_bytes).decode('cp932', errors='replace')

    def read_dir(self, path: str, count: int, entries: list):
        for _ in range(count):
            offset = self.read_int64()
            unpacked = self.read_int64()
            packed = self.read_int64()
            flags = self.read_uint32()
            self.read_uint64()  # ctime
            self.read_uint64()  # atime
            self.read_uint64()  # mtime
            name = self.read_name()
            full_name = os.path.join(path, name).replace('\\', '/')

            if flags & 0x10:
                self.read_dir(full_name, int(unpacked), entries)
            else:
                entries.append(Entry(
                    name=full_name,
                    offset=self.base_offset + offset,
                    size=packed,
                    unpacked_size=unpacked,
                    is_packed=True
                ))

    def read_root(self, root_count: int) -> list:
        entries = []
        self.read_dir('', root_count, entries)
        return entries


class Entry:
    def __init__(self, name: str, offset: int, size: int, unpacked_size: int, is_packed: bool):
        self.name = name
        self.offset = offset
        self.size = size
        self.unpacked_size = unpacked_size
        self.is_packed = is_packed


def main():
    if len(sys.argv) != 3:
        print("Usage: python Debonosu_Works_unpack.py <input.pak> <output_directory>")
        sys.exit(1)

    pak_path = sys.argv[1]
    out_dir = sys.argv[2]

    try:
        DebonosuPAKUnpack.unpack(pak_path, out_dir)
        print("Unpacking completed.")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
