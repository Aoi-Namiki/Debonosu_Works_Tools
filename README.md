# DebonosuWorks PAK Tools (神乐花莚谭)
Tools to list, extract, repack, and decompile the `*.pak` format, tested on `神乐花莚谭` (Debonosu Works engine).

## Requirements
- Python 3.8+ (standard library only)
- Java (for script decompiling via `unluac.jar`)

### Optional: 32-bit virtualenv for lua5.1.dll
Create once (PowerShell):
```powershell
py -3.13-32 -m venv .venv32
```
Use it by calling the venv python directly (no activation needed):
```powershell
.\.venv32\Scripts\python.exe - <<'PY'
import struct
print("bits", struct.calcsize('P')*8)
PY
```
For all commands below, replace `python` with `.\.venv32\Scripts\python.exe` to ensure 32-bit.

## Usage
- Extract and dump index (index.json is required for repack):
  ```bash
  .\.venv32\Scripts\python.exe depress.py game.pak -o extracted --dump-index index.json
  ```
- Decompile scripts (Shift-JIS, no post-decode by default):
  ```bash
  .\.venv32\Scripts\python.exe script/decompiler.py --jar script/unluac.jar extracted/script decompiled
  ```
- Repack (not byte-identical):
  ```bash
  .\.venv32\Scripts\python.exe compress.py index.json extracted -o game_new.pak
  ```
- Compile Lua 5.1 (uses `script/lua5.1.dll`, default encoding shift_jis):
  - Single:
    ```bash
    .\.venv32\Scripts\python.exe script/compiler.py decompiled\example.lua -o recompiled\example.scb
    ```
  - Folder:
    ```bash
    .\.venv32\Scripts\python.exe script/compiler.py decompiled
    ```
  - Folder → specific output dir:
    ```bash
    .\.venv32\Scripts\python.exe script/compiler.py decompiled -o recompile
    ```
- String-only workflow (Shift-JIS by default; per-file mapping `*.scb.txt`, order preserved):
  - Single extract → `*.scb.txt`:
    ```bash
    .\.venv32\Scripts\python.exe script/extract.py extracted/script/_cmdlist.scb -o outputtext\_cmdlist.scb.txt --src-encoding shift_jis
    ```
  - Folder extract → mirror structure under `outputtext`:
    ```bash
    .\.venv32\Scripts\python.exe script/extract.py extracted/script -o outputtext --src-encoding shift_jis
    ```
  - Edit format (one blank line between pairs; `\r`/`\n` are kept as literals):
    ```
    ○00000○ original text
    ●00000● translated text
    ```
  - Single import (uses matching `*.scb.txt`):
    ```bash
    .\.venv32\Scripts\python.exe script/import.py extracted/script/_cmdlist.scb outputtext\_cmdlist.scb.txt importtext/_cmdlist.scb --src-encoding shift_jis --dst-encoding shift_jis
    ```
  - Folder import (reads every `*.scb.txt` in `outputtext`, writes to `importtext`):
    ```bash
    .\.venv32\Scripts\python.exe script/import.py extracted/script outputtext importtext --src-encoding shift_jis --dst-encoding shift_jis
    ```
  - Notes:
    - Mapping lines use `●00000● text` (one blank line between pairs); `\r`/`\n` stay literal.
    - Missing mapping file → that `.scb` is skipped; empty mapping → original bytes are copied.
    - No-text-change roundtrip is byte-identical (0 diff) with the current scripts.

## Notes
- Index block is raw DEFLATE; each entry is a 52-byte header plus a null-terminated Shift-JIS name. Directories have attribute `0x10` and store child count in field 2.
- `script/unluac.jar` is required for decompiling; you can override path via `--jar`.
- The provided `compress.py` rebuilds a valid PAK but compression ratios differ from the original, so output bytes will not be identical. Use it to repack after edits; if you need byte-perfect matching, an exact-mode repacker is not included here.

## Tools
- [unluac](https://github.com/scratchminer/unluac/releases/tag/v2023.03.22) (lua5.1 decompiler jar tool)
