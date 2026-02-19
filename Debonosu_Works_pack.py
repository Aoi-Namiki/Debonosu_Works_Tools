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
        """构建多根目录树，每个输入目录的内容（直接子项）作为顶层节点"""
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
                    # 递归构建该子目录的子树
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
        """计算每个目录的直接子项数量"""
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
        """原始 Deflate 压缩（无头无尾）"""
        compressor = zlib.compressobj(level=level, method=zlib.DEFLATED, wbits=-15)
        return compressor.compress(data) + compressor.flush()

    @staticmethod
    def _build_index_and_data(top_nodes: List[_Node]) -> Tuple[bytes, bytes]:
        """构建索引和文件数据"""
        index_data = bytearray()
        file_data = bytearray()
        file_offset = 0

        def write_cstring(s: str):
            index_data.extend(s.encode('cp932'))
            index_data.append(0)

        def process_node(node: DebonosuPAK._Node, parent_path: str = ''):
            nonlocal file_offset
            if node.is_dir:
                # 目录条目
                index_data.extend(struct.pack('<QQQI', 0, node.child_count, 0, 0x10))
                index_data.extend(b'\x00' * 24)  # 时间戳占位
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
                # 文件条目
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
        print(f"开始打包 {len(input_dirs)} 个目录的内容 -> {output_path}")
        top_nodes = DebonosuPAK._build_tree(input_dirs)
        if not top_nodes:
            print("警告：没有找到任何有效文件/文件夹，打包可能为空。")
        index_raw, file_data = DebonosuPAK._build_index_and_data(top_nodes)

        # 压缩索引
        compressed_index = DebonosuPAK._deflate_raw(index_raw)

        INFO_OFFSET = 0x10
        INFO_BLOCK_SIZE = 20  # 索引信息块大小（5个uint32）
        root_count = len(top_nodes)  # 顶层节点数（直接子项个数）
        unpacked_size = len(index_raw)
        packed_size = len(compressed_index)

        # 索引信息块：info_size, unknown(0), root_count, unpacked_size, packed_size
        info_block = struct.pack('<IIIII',
                                 INFO_BLOCK_SIZE,  # info_size
                                 0,                # 未知字段
                                 root_count,
                                 unpacked_size,
                                 packed_size)

        # 确保输出目录存在
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(output_path, 'wb') as f:
            # 文件头16字节
            header = bytearray(16)
            header[0:4] = DebonosuPAK.MAGIC
            struct.pack_into('<H', header, 4, INFO_OFFSET)  # index_offset
            # header[6:16] 默认为0，满足偏移10-11为0的要求
            f.write(header)

            # 索引信息块（从 INFO_OFFSET 开始）
            f.write(info_block)

            # 压缩索引数据
            f.write(compressed_index)

            # 文件数据
            f.write(file_data)

        total_files = sum(1 for node in top_nodes for _ in DebonosuPAK._walk_files(node))
        if progress_callback:
            progress_callback(total_files, total_files)
        print(f"打包完成！输出文件: {output_path}")
        print(f"顶层节点数: {root_count}")
        print(f"文件总数: {total_files}")

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
        print("用法: python Debonosu_Works_pack.py 输入路径1 [输入路径2 ...] 输出路径\\test.pak")
        sys.exit(1)

    # 最后一个参数为输出路径，其余为输入路径
    output = sys.argv[-1]
    input_dirs = sys.argv[1:-1]

    # 检查输出文件后缀是否为 .pak
    if not output.lower().endswith('.pak'):
        print("错误：输出文件必须以 .pak 为后缀")
        sys.exit(1)

    def progress(current, total):
        print(f"\r进度: {current}/{total}", end="")

    DebonosuPAK.pack(input_dirs, output, progress)
    print("\n打包完成")