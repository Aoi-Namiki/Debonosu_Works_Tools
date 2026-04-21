# Debonosu Works 游戏汉化工具包使用指南

本工具包专为 `でぼの巣製作所`（Debonosu Works）游戏引擎设计，提供以下功能：
- **PAK 解包/封包**：提取/打包游戏资源包（`.pak` 文件）
- **SCB 字符串提取/写回**：编辑 Lua 5.1 脚本（`.scb` 文件）中的常量字符串

支持 **CP932 (Shift-JIS)** 与 **UTF-8** 编码自动检测，适用于日文游戏汉化。

---

## 工具列表

| 脚本 | 功能 | 输入 | 输出 |
|------|------|------|------|
| `Debonosu_Works_unpack.py` | 解包 `.pak` 文件 | `xxx.pak` | 文件夹（原始目录结构） |
| `Debonosu_Works_pack.py` | 打包文件夹为 `.pak` | 一个或多个文件夹 | `xxx.pak` |
| `Debonosu_Works_scb_extract_v2.py` | 提取 `.scb` 中的常量字符串 | `.scb` 文件或文件夹 | `.txt` 文件（○/● 格式） |
| `Debonosu_Works_scb_import_v2.py` | 将译文写回 `.scb` | `.scb` + 编辑过的 `.txt` | 新的 `.scb` 文件 |

---

## 一、PAK 解包与封包

### 1.1 解包 PAK（提取所有资源）

```bash
python Debonosu_Works_unpack.py game.pak ./extracted
```

- **输出**：`./extracted` 目录，包含所有原始文件（保持内部目录结构）。
- **支持格式**：仅 `.pak` 文件。
- **编码**：文件名自动按 CP932 解码。

### 1.2 封包 PAK（将文件夹打包为 PAK）

```bash
python Debonosu_Works_pack.py ./extracted new.pak
```

可同时指定多个输入目录：
```bash
python Debonosu_Works_pack.py ./dir1 ./dir2 ./dir3 combined.pak
```

- **输出**：`new.pak`，可直接被游戏读取。
- **注意**：输入目录的**直接子项**成为 PAK 的顶层条目（目录名本身不会出现在 PAK 中）。
- **压缩**：自动使用 Deflate 压缩，与原始游戏格式完全兼容。

---

## 二、SCB 字符串提取与写回

### 2.1 提取字符串（从 .scb 生成可编辑的 .txt）

#### 命令行模式（单文件）
```bash
python Debonosu_Works_scb_extract_v2.py script.scb -o script.txt --src-encoding auto
```

#### 批处理模式（零参数，处理 ./script 文件夹）
1. 将所有 `.scb` 文件放入 `./script` 文件夹（可含子目录）。
2. 直接双击 `extract_strings.py` 或在命令行无参数运行：
   ```bash
   python Debonosu_Works_scb_extract_v2.py
   ```
3. 提取结果自动输出到 `./txt` 文件夹，保持原目录结构，编码自动检测。

#### 输出格式示例
```
○00001○ 原日文文本
●00001○ 原日文文本

○00002○ 另一段文本
●00002○ 另一段文本
```
- `●` 行供编辑，`○` 行仅作参考。

### 2.2 写回字符串（将译文写回 .scb）

#### 命令行模式（单文件）
```bash
python Debonosu_Works_scb_import_v2.py script.scb script.txt new_script.scb --src-encoding auto --dst-encoding auto
```

#### 批处理模式（零参数）
1. 原始 `.scb` 文件放在 `./script` 文件夹。
2. 对应的译文 `.txt` 文件放在 `./txt` 文件夹（目录结构必须与 `./script` 一致）。
3. 直接双击 `patch_strings.py` 或在命令行无参数运行：
   ```bash
   python Debonosu_Works_scb_import_v2.py
   ```
4. 输出到 `./new_script/script` 文件夹，保持原目录结构，目标编码自动与源编码相同。

---

## 三、完整汉化工作流示例

假设目标游戏为 `game.pak`，需要汉化其中的脚本文件。

### 步骤 1：解包 PAK
```bash
python Debonosu_Works_unpack.py game.pak ./work
```
得到 `./work` 文件夹，其中包含所有资源文件（如 `script/level1.scb` 等）。

### 步骤 2：提取脚本字符串
将 `./work/script` 文件夹复制到当前目录（或直接作为输入）：
```bash
python Debonosu_Works_scb_extract_v2.py ./work/script -o ./txt --src-encoding auto
```
生成 `./txt` 文件夹，内部结构与 `script` 相同，每个 `.scb` 对应一个 `.txt`。

### 步骤 3：翻译
使用任何文本编辑器打开 `./txt` 中的文件，**只修改以 `●` 开头的行**：
```
●00001● 翻译后的文本
```
支持转义：`\r`（回车）、`\n`（换行）。

### 步骤 4：写回脚本
```bash
python Debonosu_Works_scb_import_v2.py ./work/script ./txt ./work_new/script --src-encoding auto --dst-encoding auto
```
生成 `./work_new/script` 文件夹，内含修改后的 `.scb` 文件。

### 步骤 5：替换原脚本
将 `./work_new/script` 覆盖回 `./work/script`（或直接打包）。

### 步骤 6：重新打包 PAK
```bash
python Debonosu_Works_pack.py ./work new_game.pak
```
生成的 `new_game.pak` 可直接替换游戏原文件。

---

## 四、编码说明

| 参数值 | 含义 |
|--------|------|
| `shift_jis` / `cp932` | 强制使用日文 Shift-JIS 编码 |
| `utf-8` | 强制使用 UTF-8 编码 |
| `auto` | 自动检测（推荐） |

**自动检测逻辑**：  
- 尝试用 UTF-8 解码所有常量字符串，若全部成功且存在非 ASCII 字符 → UTF-8；否则 → Shift-JIS。

**写回时**：若 `--dst-encoding auto`，目标编码自动与源编码相同，避免乱码。

---

## 五、常见问题

**Q：解包后的文件有乱码？**  
A：PAK 内的文件名固定为 CP932，解包脚本已正确处理，若操作系统显示乱码请使用支持日文字符的文本查看器。

**Q：封包后的 PAK 游戏不识别？**  
A：确保输出文件后缀为 `.pak`，且输入目录结构与原始 PAK 一致（顶层直接子项）。可先解包原 PAK 后不做任何修改直接封包，对比文件哈希。

**Q：提取 SCB 时出现 `[SKIP]`？**  
A：该文件不是 Lua 5.1 格式或已损坏。检查是否为 Debonosu Works 的脚本文件。

**Q：写回时提示无法编码字符？**  
A：译文包含目标编码（通常为 CP932）不支持的字符。解决方法：  
- 改用 `--dst-encoding utf-8`（需确认游戏引擎支持）  
- 替换为编码支持的字符（如中文可尝试 GBK，但游戏不一定识别）

**Q：批处理模式下如何只处理特定文件？**  
A：使用命令行模式，指定具体文件路径即可。

---

## 六、命令行参数速查

### Debonosu_Works_scb_extract_v2.py
```
usage: Debonosu_Works_scb_extract_v2.py [-h] [-o OUT] [--src-encoding SRC_ENCODING] input

positional arguments:
  input                 .scb/.luac file or directory

optional arguments:
  -o OUT                output file (single) or directory (folder)
  --src-encoding        shift_jis / utf-8 / auto (default: shift_jis)
```

### Debonosu_Works_scb_import_v2.py
```
usage: Debonosu_Works_scb_import_v2.py [-h] [--src-encoding SRC_ENCODING]
                        [--dst-encoding DST_ENCODING]
                        input map output

positional arguments:
  input                 input .scb/.luac or directory
  map                   mapping txt (single) or directory of txt
  output                output file (single) or directory (folder)

optional arguments:
  --src-encoding        decode existing strings (default: shift_jis, use 'auto')
  --dst-encoding        encode new strings (default: shift_jis, use 'auto')
```

### Debonosu_Works_unpack.py
```
usage: python Debonosu_Works_unpack.py <input.pak> <output_directory>
```

### Debonosu_Works_pack.py
```
usage: python Debonosu_Works_pack.py input_dir1 [input_dir2 ...] output.pak
```

---

## 七、注意事项

- 所有工具均基于 **Python 3.6+**，无需额外依赖（使用标准库 `struct`, `zlib`, `pathlib`）。
- 解包/封包仅处理 PAK 格式，不涉及加密或其他容器。
- SCB 修改不进行反编译，只替换常量表中的字符串，安全可靠。
- 建议在处理前备份原始文件。
