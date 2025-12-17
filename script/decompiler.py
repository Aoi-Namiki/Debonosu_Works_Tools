#!/usr/bin/env python3
"""
批量反编译 .scb（Lua 5.1 字节码）为可读 Lua。
依赖同目录下的 unluac.jar；保持输入目录的相对路径结构，输出为 .lua。
"""
import argparse
import subprocess
from pathlib import Path


def run_unluac(jar: Path, src: Path) -> str:
    """调用 unluac 反编译单个文件，返回 stdout 文本（UTF-8）。"""
    result = subprocess.run(
        ["java", "-jar", str(jar), str(src)],
        check=True,
        capture_output=True,
    )
    return result.stdout.decode("shift_jis", errors="replace")


def main():
    parser = argparse.ArgumentParser(description="批量反编译 .scb -> .lua")
    parser.add_argument("input_dir", type=Path, help="包含 .scb 的输入目录")
    parser.add_argument("output_dir", type=Path, help="输出目录（会创建相对路径结构）")
    parser.add_argument(
        "--jar",
        type=Path,
        default=Path(__file__).parent / "unluac.jar",
        help="unluac.jar 路径（默认同目录）",
    )
    parser.add_argument(
        "--encoding",
        default="shift_jis",
        help="--decode 时使用的文本编码（默认 shift_jis）",
    )
    parser.add_argument(
        "--raw-escapes",
        action="store_true",
        help="不还原 \\ddd 转义（默认会按 --encoding 解码为可读文本）",
    )
    args = parser.parse_args()

    jar = args.jar.resolve()
    if not jar.is_file():
        raise SystemExit(f"找不到 unluac.jar: {jar}")

    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    if not input_dir.is_dir():
        raise SystemExit(f"输入目录不存在: {input_dir}")

    scb_files = sorted(input_dir.rglob("*.scb"))
    if not scb_files:
        raise SystemExit("未找到任何 .scb 文件")

    for src in scb_files:
        rel = src.relative_to(input_dir)
        dst = output_dir / rel.with_suffix(".lua")
        try:
            text = run_unluac(jar, src)
            if not args.raw_escapes:
                # unluac 输出里 \ddd 使用十进制转义；按十进制还原为原始字节，再按编码解码。
                def decode_decimal_escapes(src_text: str, encoding: str) -> str:
                    buf = bytearray()
                    i = 0
                    while i < len(src_text):
                        ch = src_text[i]
                        if ch == "\\" and i + 1 < len(src_text):
                            j = i + 1
                            digits = ""
                            while j < len(src_text) and len(digits) < 3 and src_text[j].isdigit():
                                digits += src_text[j]
                                j += 1
                            if digits:
                                buf.append(int(digits))
                                i = j
                                continue
                            # 保留常见转义为字面形式，避免把 \n 变成真换行导致字符串破坏
                            nxt = src_text[i + 1]
                            if nxt == "n":
                                buf.extend(b"\\n")
                                i += 2
                                continue
                            if nxt == "r":
                                buf.extend(b"\\r")
                                i += 2
                                continue
                            if nxt == "t":
                                buf.extend(b"\\t")
                                i += 2
                                continue
                            if nxt == "\\":
                                buf.extend(b"\\\\")
                                i += 2
                                continue
                        # 其他字符按原样写入单字节
                        buf.extend(ch.encode("latin-1", errors="replace"))
                        i += 1
                    return buf.decode(encoding, errors="replace")

                text = decode_decimal_escapes(text, args.encoding)

            # 统一换行，避免 \r\r\n 造成“空一行”。
            text = text.replace("\r\n", "\n").replace("\r", "\n")

            dst.parent.mkdir(parents=True, exist_ok=True)
            with dst.open("w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            print(f"[OK] {rel} -> {dst.relative_to(output_dir)}")
        except subprocess.CalledProcessError as exc:
            print(f"[FAIL] {rel}: {exc}")


if __name__ == "__main__":
    main()
