# PDF 期末留抵税额提取

批量查找增值税申报表的“期末留抵税额”行，提取“一般项目本期数”，或“一般项目”下的“本月数”。支持文字型 PDF，不支持扫描件或图片 OCR。

## 安装

需要 Python 3.10 或更新版本。以下命令均在本项目目录运行。

### 使用 uv（推荐）

安装 [uv](https://docs.astral.sh/uv/getting-started/installation/) 后运行：

```bash
# 安装依赖，自动创建或使用项目的 .venv，无需激活环境或安装 pip
uv sync

# 扫描指定目录及其子目录
uv run python extract_vat_credit.py "/path/to/pdfs"

# 仅扫描当前层，并指定 CSV 输出路径
uv run python extract_vat_credit.py "/path/to/pdfs" --no-recursive -o result.csv
```

也可以直接运行第二条命令，`uv run` 会自动同步依赖。依赖声明在 `pyproject.toml` 中；首次同步会生成 `uv.lock`。如需使用系统的 Python 3，可运行 `uv sync --python python3`。

### 使用标准 venv

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python extract_vat_credit.py "/path/to/pdfs"
```

Windows 激活命令为 `.venv\Scripts\activate`；如系统使用 `python` 命令，将示例中的 `python3` 替换为 `python`。Linux 若缺少 venv/pip，需先安装对应发行版的 Python venv/pip 组件。

## 使用

以下直接调用 Python 的示例需要先激活 `.venv`；使用 uv 时，将 `python3` 替换为 `uv run python`，无需激活环境。

```bash
# 指定目录，默认包含全部子目录
python3 extract_vat_credit.py "/path/to/pdfs"

# 不传目录则扫描当前目录及其子目录
python3 extract_vat_credit.py

# 只扫描指定目录的当前层，显式指定 CSV 路径
python3 extract_vat_credit.py "/path/to/pdfs" --no-recursive -o result.csv
```

扩展名不区分大小写，包括 `.pdf` 和 `.PDF`。中文路径及包含空格的路径请加引号。程序读取全部页面，保留原始 PDF。

默认输出为指定 PDF 目录下的 `vat_credit_results.csv`。`-o` 的相对路径以运行命令时的工作目录为基准，父目录须已存在；重复运行会覆盖同名 CSV。

CSV 使用带 BOM 的 UTF-8 编码，可用 Excel 打开，包含：文件绝对路径、页码（从 1 开始）、匹配列、期末留抵税额、状态、说明。终端逐文件显示结果并输出处理数量。金额去除千位分隔符并保留两位小数，例如 `32,975.52` 输出为 `32975.52`；`0.00` 是有效金额。一个 PDF 出现多条匹配行时逐条输出，不自动合计或去重。

程序优先按表格单元格和合并表头定位。无法识别表格边界时，尝试利用同页表头及相邻列坐标确定金额范围；不会直接取目标行中的第一个数字。

| 状态 | 含义 |
| --- | --- |
| `ok` | 成功提取 |
| `missing_value` | 目标单元格为空或横线，金额留空 |
| `invalid_value` | 单元格不是唯一有效金额，金额留空并保留原因 |
| `column_not_found` | 找到目标行，但无法可靠确定目标列 |
| `not_found` | 有文字，但没有找到目标行 |
| `unsupported_pdf` | 无可提取文字，可能为扫描件 |
| `read_error` | PDF 损坏、加密或页面读取失败 |

单个文件或页面出错后继续处理其他文件。退出码 `0` 表示处理完成且没有异常记录（空目录也返回 `0` 并生成仅含表头的 CSV），`1` 表示结果包含异常记录，`2` 表示参数、依赖或输出文件错误。

也可在 Python 中调用：

```python
from extract_vat_credit import extract_pdf, extract_directory, write_csv

results = extract_pdf("申报表.pdf")  # list[Result]
results = extract_directory("/path/to/pdfs", recursive=True)
write_csv(results, "result.csv")
for result in results:
    print(result.file_path, result.page, result.amount, result.status)
```

## 验证

```bash
# uv
uv run python -m unittest discover -s tests -v

# 或激活 venv 后运行
python -m unittest discover -s tests -v
```

测试覆盖两种表头、无表格边界的坐标定位、金额规范化、零金额与空值、递归扫描和大小写扩展名、文件异常、CSV 编码。安装依赖后，还会用本目录的 4 份 PDF 验证以下金额；没有依赖或没有对应样例时，真实 PDF 回归测试会明确显示为跳过。

| 样例 | 页码 | 金额 |
| --- | ---: | ---: |
| 文件名含 `218D9926` | 3 | 849.06 |
| 文件名含 `4804AD73` | 3 | 27767.80 |
| 增值税及附加税费申报表（一般纳税人适用）.pdf | 1 | 32975.52 |
| 增值税及附加税费申报（一般纳税人适用）.pdf | 1 | 17400.70 |

默认针对上述两类表格。无文字层、无法解密、表头缺失或文字坐标严重错乱的文件可能无法识别，应依据状态和页码核对原件。
