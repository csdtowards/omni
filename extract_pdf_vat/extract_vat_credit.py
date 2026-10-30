#!/usr/bin/env python3
"""批量提取增值税申报表中的一般项目期末留抵税额。Python 3.10+。"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Iterable


TARGET = "期末留抵税额"
DIRECT_HEADER = "一般项目本期数"
GROUP_HEADER = "一般项目"
MONTH_HEADER = "本月数"
TOTAL_HEADER = "本年累计"
CSV_FIELDS = ("文件路径", "页码", "匹配列", "期末留抵税额", "状态", "说明")
BBox = tuple[float, float, float, float]


@dataclass(frozen=True)
class Result:
    file_path: str
    page: int | None = None
    column: str = ""
    amount: str = ""
    status: str = "ok"
    message: str = ""

    def csv_row(self) -> tuple:
        return (self.file_path, self.page, self.column, self.amount,
                self.status, self.message)


@dataclass(frozen=True)
class Cell:
    bbox: BBox
    text: str

    @property
    def cx(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2

    @property
    def cy(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text))


def parse_amount(text: str) -> str | None:
    """返回无千位分隔符、两位小数的金额；缺失返回 None，格式错误抛异常。"""
    value = normalize(text).replace("−", "-")
    if not value or all(char in "-—–―﹘" for char in value):
        return None
    if not re.fullmatch(r"[+-]?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]{1,2})?", value):
        raise ValueError(f"单元格内容不是唯一有效金额：{text!r}")
    value = value.replace(",", "")
    with localcontext() as context:
        context.prec = max(28, len(value) + 2)
        return format(Decimal(value).quantize(Decimal("0.01")), ".2f")


def _inside(x: float, y: float, bbox: BBox) -> bool:
    return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]


def _lines(chars: list[dict]) -> list[list[dict]]:
    """按字符垂直中心聚合；所有坐标均使用 PDF 顶部为原点的坐标系。"""
    lines: list[list[dict]] = []
    centers: list[float] = []
    for char in sorted(chars, key=lambda c: ((c["top"] + c["bottom"]) / 2, c["x0"])):
        cy = (char["top"] + char["bottom"]) / 2
        if lines and abs(cy - centers[-1]) <= 3:
            line = lines[-1]
            centers[-1] = (centers[-1] * len(line) + cy) / (len(line) + 1)
            line.append(char)
        else:
            lines.append([char])
            centers.append(cy)
    return [sorted(line, key=lambda c: c["x0"]) for line in lines]


def _text(chars: list[dict], bbox: BBox) -> str:
    selected = [c for c in chars if _inside(
        (c["x0"] + c["x1"]) / 2, (c["top"] + c["bottom"]) / 2, bbox)]
    return "\n".join("".join(c["text"] for c in line) for line in _lines(selected))


def _matches(lines: list[list[dict]], label: str) -> list[Cell]:
    matches = []
    for line in lines:
        text = ""
        source = []
        for char in line:
            part = normalize(char["text"])
            text += part
            source.extend([char] * len(part))
        start = 0
        while (index := text.find(label, start)) >= 0:
            selected = source[index:index + len(label)]
            bbox = (min(c["x0"] for c in selected), min(c["top"] for c in selected),
                    max(c["x1"] for c in selected), max(c["bottom"] for c in selected))
            matches.append(Cell(bbox, label))
            start = index + len(label)
    return matches


def _table_header(cells: list[Cell], target: Cell) -> tuple[Cell, str] | None:
    above = [c for c in cells if c.bbox[3] <= target.bbox[1] + 1]
    direct = [c for c in above if normalize(c.text) == DIRECT_HEADER]
    if direct:
        return max(direct, key=lambda c: c.cy), DIRECT_HEADER
    pairs = []
    for group in above:
        if normalize(group.text) != GROUP_HEADER:
            continue
        for child in above:
            if (normalize(child.text) == MONTH_HEADER
                    and group.bbox[0] <= child.cx <= group.bbox[2]
                    and child.bbox[1] >= group.bbox[3] - 1):
                pairs.append((group, child))
    if pairs:
        _, child = max(pairs, key=lambda pair: (pair[0].cy, -pair[1].cy))
        return child, f"{GROUP_HEADER}/{MONTH_HEADER}"
    return None


def _coordinate_header(lines: list[list[dict]], target: Cell) -> tuple[BBox, str] | None:
    """无可用表格边界时，从同一表头行中相邻列的中心推导列范围。"""
    direct = [c for c in _matches(lines, DIRECT_HEADER) if c.bbox[3] < target.bbox[1]]
    for header in sorted(direct, key=lambda c: c.cy, reverse=True):
        peers = [c for c in _matches(lines, "即征即退项目本期数")
                 if abs(c.cy - header.cy) <= 3 and c.cx > header.cx]
        if peers:
            gap = min(c.cx for c in peers) - header.cx
            return (header.cx - gap / 2, target.bbox[1],
                    header.cx + gap / 2, target.bbox[3]), DIRECT_HEADER

    groups = [c for c in _matches(lines, GROUP_HEADER) if c.bbox[3] < target.bbox[1]]
    months = _matches(lines, MONTH_HEADER)
    totals = _matches(lines, TOTAL_HEADER)
    for group in sorted(groups, key=lambda c: c.cy, reverse=True):
        max_gap = max(40, (group.bbox[3] - group.bbox[1]) * 4)
        children = [c for c in months + totals
                    if group.bbox[3] <= c.cy < min(target.bbox[1], group.bbox[3] + max_gap)]
        for month in sorted((c for c in children if c.text == MONTH_HEADER), key=lambda c: c.cy):
            right = [c for c in children if c.text == TOTAL_HEADER
                     and abs(c.cy - month.cy) <= 3 and c.cx > month.cx]
            if not right:
                continue
            total = min(right, key=lambda c: c.cx)
            if month.cx <= group.cx <= total.cx:
                gap = total.cx - month.cx
                return (month.cx - gap / 2, target.bbox[1],
                        month.cx + gap / 2, target.bbox[3]), f"{GROUP_HEADER}/{MONTH_HEADER}"
    return None


def _value_result(path: Path, page: int, column: str, text: str) -> Result:
    try:
        amount = parse_amount(text)
    except ValueError as error:
        return Result(str(path), page, column, status="invalid_value", message=str(error))
    if amount is None:
        return Result(str(path), page, column, status="missing_value", message="目标单元格为空或横线")
    return Result(str(path), page, column, amount)


def extract_page(page, path: Path, page_number: int) -> list[Result]:
    chars = page.chars
    lines = _lines(chars)
    labels = _matches(lines, TARGET)
    # 文字顺序可能按单元格排列，保留对跨行标签的检测机会。
    page_text = normalize("".join(c["text"] for c in chars))
    if not labels and not all(char in page_text for char in TARGET):
        return []
    hits: list[tuple[Cell, Result]] = []
    table_targets = []
    try:
        tables = page.find_tables()
    except Exception:
        # 表格检测失败仍可使用同页文字坐标，不退回到整行正则取数。
        tables = []
    for table in tables:
        cells = [Cell(tuple(bbox), _text(chars, bbox)) for bbox in table.cells]
        for target in (c for c in cells if TARGET in normalize(c.text)):
            table_targets.append(target)
            header = _table_header(cells, target)
            if header is None:
                continue
            column, name = header
            values = [c for c in cells if _inside(column.cx, target.cy, c.bbox)
                      and c.bbox[0] >= target.bbox[2] - 1]
            if len(values) == 1:
                hits.append((target, _value_result(path, page_number, name, values[0].text)))
    targets = labels + [cell for cell in table_targets
                        if not any(_inside(label.cx, label.cy, cell.bbox) for label in labels)]
    for target in targets:
        if any(_inside(target.cx, target.cy, cell.bbox) for cell, _ in hits):
            continue
        header = _coordinate_header(lines, target)
        if header is None:
            result = Result(str(path), page_number, status="column_not_found",
                            message="找到目标行，但无法确定一般项目的目标列")
        else:
            bbox, name = header
            if bbox[0] < target.bbox[2]:
                result = Result(str(path), page_number, name, status="column_not_found",
                                message="推导出的列与行名称重叠，无法可靠提取")
            else:
                result = _value_result(path, page_number, name, _text(chars, bbox))
        hits.append((target, result))
    return [result for _, result in sorted(hits, key=lambda hit: (hit[0].cy, hit[0].cx))]


def _load_pdfplumber():
    try:
        import pdfplumber
    except ImportError as error:
        raise RuntimeError(
            "缺少 PDF 解析依赖。请在项目目录运行 uv sync，"
            "再使用 uv run python extract_vat_credit.py；"
            "或激活 venv 后运行 python -m pip install -r requirements.txt"
        ) from error
    return pdfplumber


def extract_pdf(path: str | Path) -> list[Result]:
    """读取单个 PDF；每个匹配行返回一条记录，文件错误也返回状态记录。"""
    pdfplumber = _load_pdfplumber()
    path = Path(path).expanduser().resolve()
    results = []
    has_text = False
    try:
        with pdfplumber.open(path) as pdf:
            for page_number, page in enumerate(pdf.pages, 1):
                try:
                    has_text = has_text or bool(page.chars)
                    results.extend(extract_page(page, path, page_number))
                except Exception as error:
                    results.append(Result(str(path), page_number, status="read_error",
                                          message=f"{type(error).__name__}: {error}"))
                finally:
                    page.close()
    except Exception as error:
        results.append(Result(str(path), status="read_error",
                              message=f"{type(error).__name__}: {error}"))
    if not results:
        status = "not_found" if has_text else "unsupported_pdf"
        message = "未找到期末留抵税额行" if has_text else "无可提取文字，可能是扫描件；本程序不支持 OCR"
        results.append(Result(str(path), status=status, message=message))
    return results


def find_pdfs(directory: str | Path, recursive: bool = True) -> list[Path]:
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"目录不存在或不是目录：{root}")
    paths = root.rglob("*") if recursive else root.iterdir()
    return sorted((p for p in paths if p.is_file() and p.suffix.lower() == ".pdf"),
                  key=lambda p: str(p.relative_to(root)).casefold())


def extract_directory(directory: str | Path, recursive: bool = True) -> list[Result]:
    return [result for path in find_pdfs(directory, recursive) for result in extract_pdf(path)]


def write_csv(results: Iterable[Result], output: str | Path) -> None:
    with Path(output).open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_FIELDS)
        writer.writerows(result.csv_row() for result in results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", nargs="?", default=".", help="PDF 所在目录，默认当前目录")
    parser.add_argument("--no-recursive", action="store_true", help="仅扫描指定目录的当前层")
    parser.add_argument("-o", "--output", type=Path, help="CSV 输出路径，默认放在 PDF 目录下")
    args = parser.parse_args(argv)
    root = Path(args.directory).expanduser().resolve()
    output = (args.output.expanduser() if args.output else root / "vat_credit_results.csv").resolve()
    if output.suffix.lower() != ".csv":
        parser.error("输出文件必须使用 .csv 扩展名")
    try:
        paths = find_pdfs(root, recursive=not args.no_recursive)
        if paths:
            _load_pdfplumber()
        results = []
        for path in paths:
            for result in extract_pdf(path):
                results.append(result)
                location = f"第 {result.page} 页" if result.page else "页码未知"
                value = result.amount if result.status == "ok" else f"[{result.status}] {result.message}"
                print(f"{path.relative_to(root)} | {location} | {result.column or '-'} | {value}")
        write_csv(results, output)
    except (ValueError, OSError, RuntimeError) as error:
        print(f"错误：{error}", file=sys.stderr)
        return 2
    failed = sum(r.status != "ok" for r in results)
    print(f"扫描 {len(paths)} 个 PDF，成功提取 {len(results) - failed} 项，异常 {failed} 项。")
    print(f"CSV：{output}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
