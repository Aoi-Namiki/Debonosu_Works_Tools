import os
import struct
import zlib
from typing import List, Optional, Callable, Tuple

class DebonosuPAK:
    MAGIC = b'PAK\x00'

    class _Node:
        def __init__(self, path: str, is_dir: bool):
            self.path = path
            self.name = os.path.basename(path)
            self.is_dir = is_dir
            self.children: List['DebonosuPAK._Node'] = []
            self.child_count = 0
            self.file_offset = 0
            self.size = 0
            self.compressed_size = 0

    @staticmethod
    def _build_tree(root_dirs: List[str]) -> List[_Node]:
        top_nodes = []
        for root in root_dirs:
            if not os.path.isdir(root):
                continue
            try:
                entries = os.scandir(root)
            except (PermissionError, FileNotFoundError):
                continue
            for entry in entries:
                node = DebonosuPAK._Node(entry.path, entry.is_dir())
                node.name = entry.name
                top_nodes.append(node)
                if entry.is_dir():
                    stack = [(node, entry.path)]
                    while stack:
                        parent, cur_path = stack.pop()
                        try:
                            sub_entries = os.scandir(cur_path)
                        except PermissionError:
                            continue
                        for sub_entry in sub_entries:
                            child = DebonosuPAK._Node(sub_entry.path, sub_entry.is_dir())
                            child.name = sub_entry.name
                            parent.children.append(child)
                            if sub_entry.is_dir():
                                stack.append((child, sub_entry.path))
        return top_nodes

    @staticmethod
    def _count_children(nodes: List[_Node]):
        def _count(node: DebonosuPAK._Node):
            if not node.is_dir:
                return
            node.child_count = len(node.children)
            for child in node.children:
                _count(child)
        for node in nodes:
            _count(node)

    @staticmethod
    def _deflate_raw(data: bytes, level: int = 6) -> bytes:
        compressor = zlib.compressobj(level=level, method=zlib.DEFLATED, wbits=-15)
        return compressor.compress(data) + compressor.flush()

    @staticmethod
    def _build_index_and_data(top_nodes: List[_Node]) -> Tuple[bytes, bytes]:
        index_data = bytearray()
        file_data = bytearray()
        file_offset = 0

        def write_cstring(s: str):
            index_data.extend(s.encode('cp932'))
            index_data.append(0)

        def process_node(node: DebonosuPAK._Node, parent_path: str = ''):
            nonlocal file_offset
            if node.is_dir:
                index_data.extend(struct.pack('<QQQI', 0, node.child_count, 0, 0x10))
                index_data.extend(b'\x00' * 24)
                write_cstring(node.name)
                for child in node.children:
                    process_node(child, os.path.join(parent_path, node.name) if parent_path else node.name)
            else:
                with open(node.path, 'rb') as f:
                    raw = f.read()
                compressed = DebonosuPAK._deflate_raw(raw)
                node.size = len(raw)
                node.compressed_size = len(compressed)
                node.file_offset = file_offset
                index_data.extend(struct.pack('<QQQI', file_offset, node.size, node.compressed_size, 0))
                index_data.extend(b'\x00' * 24)
                write_cstring(node.name)
                file_data.extend(compressed)
                file_offset += node.compressed_size

        DebonosuPAK._count_children(top_nodes)
        for top_node in top_nodes:
            process_node(top_node)
        return bytes(index_data), bytes(file_data)

    @staticmethod
    def pack(input_dirs: List[str], output_path: str, progress_callback: Optional[Callable] = None):
        print(f"Start packing {len(input_dirs)} directories -> {output_path}")
        top_nodes = DebonosuPAK._build_tree(input_dirs)
        if not top_nodes:
            print("Warning: no valid files/folders found, pack may be empty.")
        index_raw, file_data = DebonosuPAK._build_index_and_data(top_nodes)

        compressed_index = DebonosuPAK._deflate_raw(index_raw)

        INFO_OFFSET = 0x10
        INFO_BLOCK_SIZE = 20
        root_count = len(top_nodes)
        unpacked_size = len(index_raw)
        packed_size = len(compressed_index)

        info_block = struct.pack('<IIIII',
                                 INFO_BLOCK_SIZE,
                                 0,
                                 root_count,
                                 unpacked_size,
                                 packed_size)

        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(output_path, 'wb') as f:
            header = bytearray(16)
            header[0:4] = DebonosuPAK.MAGIC
            struct.pack_into('<H', header, 4, INFO_OFFSET)
            f.write(header)

            f.write(info_block)

            f.write(compressed_index)

            f.write(file_data)

        total_files = sum(1 for node in top_nodes for _ in DebonosuPAK._walk_files(node))
        if progress_callback:
            progress_callback(total_files, total_files)
        print(f"Packing completed! Output file: {output_path}")
        print(f"Top node count: {root_count}")
        print(f"Total files: {total_files}")

    @staticmethod
    def _walk_files(node: _Node):
        if not node.is_dir:
            yield node
        else:
            for child in node.children:
                yield from DebonosuPAK._walk_files(child)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python Debonosu_Works_pack.py input_dir1 [input_dir2 ...] output.pak")
        sys.exit(1)

    output = sys.argv[-1]
    input_dirs = sys.argv[1:-1]

    if not output.lower().endswith('.pak'):
        print("Error: output file must have .pak extension")
        sys.exit(1)

    def progress(current, total):
        print(f"\rProgress: {current}/{total}", end="")

    DebonosuPAK.pack(input_dirs, output, progress)
    print("\nPacking finished")
