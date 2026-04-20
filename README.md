# でぼの巣製作所(Debonosu Works)脚本汉化工具

专用于 `でぼの巣製作所`（Debonosu Works）游戏引擎（Lua 5.1）的 `.scb` 脚本文件。  
可提取所有常量字符串进行翻译，再将译文写回，支持 **CP932（Shift-JIS）** 与 **UTF-8** 编码自动检测。

## 文件说明
| 脚本 | 功能 |
|------|------|
| `Debonosu_Works_scb_extract_v2.py` | 提取 `.scb` 中的字符串，生成可编辑的 `.txt` 文件 |
| `Debonosu_Works_scb_import_v2.py` | 读取修改后的 `.txt`，将新字符串写回 `.scb` |

## 快速上手

### 1. 提取字符串
**命令行**（单文件）：
```bash
python Debonosu_Works_scb_extract_v2.py script.scb -o script.txt --src-encoding auto
```
**双击运行**（零参数，批量处理）：
- 将所有 `.scb` 放入 `./script` 文件夹（可含子目录）
- 双击 `Debonosu_Works_scb_extract_v2.py`
- 提取结果自动输出到 `./txt`，保持原目录结构，编码自动检测

### 2. 编辑译文
用任意文本编辑器打开生成的 `.txt` 文件，**只修改以 `●` 开头的行**：
```
○00001○ 原日文文本
●00001● 翻译后的文本    ← 修改这一行
```
- 支持转义：`\r` 表示回车，`\n` 表示换行
- 其他行（`○` 行、空行）请勿改动

### 3. 写回脚本
**命令行**（单文件）：
```bash
python Debonosu_Works_scb_import_v2.py script.scb script.txt new_script.scb --src-encoding auto --dst-encoding auto
```
**双击运行**（零参数，批量处理）：
- 原始 `.scb` 放在 `./script`
- 对应的译文 `.txt` 放在 `./txt`（目录结构必须与 `./script` 一致）
- 双击 `Debonosu_Works_scb_import_v2.py`
- 写回结果输出到 `./new_script/script`，编码自动与原文件保持一致

## 目录结构示例（批量处理）
```
项目文件夹/
├─ script/               ← 原始 .scb
│  ├─ level1.scb
│  └─ sub/
│     └─ data.scb
├─ txt/                  ← 提取的译文 .txt
│  ├─ level1.txt
│  └─ sub/
│     └─ data.txt
├─ Debonosu_Works_scb_extract_v2.py
├─ Debonosu_Works_scb_import_v2.py
└─ 运行后生成 →
    new_script/
    └─ script/           ← 汉化后的 .scb
       ├─ level1.scb
       └─ sub/
          └─ data.scb
```

## 注意事项
- 仅支持 **Lua 5.1** 生成的 `.scb` 文件（Debonosu Works 标准格式）
- 编码参数设为 `auto` 即可自动检测 CP932 或 UTF-8，推荐使用
- 批量处理时，确保 `./script` 与 `./txt` 的目录结构完全一致
- 若写回时遇到无法编码的字符，脚本会报错并跳过该文件，请检查译文是否包含目标编码不支持的字符
