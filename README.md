# DebonosuWorks PAK Tools (神乐花莚谭)
Tools to list, extract, repack, and decompile the `*.pak` format, tested on `神乐花莚谭` (Debonosu Works engine).

## Requirements
- Python 3.8+ (standard library only)
- Java (for script decompiling via `unluac.jar`)

## Usage
- Extract everything and dump index (index.json is required for repack):
  ```bash
  python depress.py game.pak -o extracted --dump-index index.json
  ```
- Decompile scripts with Shift-JIS decoding:
  ```bash
  python script/decompiler.py --decode --encoding shift_jis --jar script/unluac.jar extracted/script decompiled
  ```
- Repack (not byte-identical; suitable for修改后重新打包):
  ```bash
  python compress.py index.json extracted -o game_new.pak
  ```

## Notes
- Index block is raw DEFLATE; each entry is a 52-byte header plus a null-terminated Shift-JIS name. Directories have attribute `0x10` and store child count in field 2.
- `script/unluac.jar` is required for decompiling; you can override path via `--jar`.
- The provided `compress.py` rebuilds a valid PAK but compression ratios differ from the original, so output bytes will not be identical. Use it to repack after edits; if you need byte-perfect matching, an exact-mode repacker is not included here.
