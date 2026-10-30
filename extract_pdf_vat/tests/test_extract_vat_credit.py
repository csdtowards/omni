import contextlib
import csv
import importlib.util
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import extract_vat_credit as vat


ROOT = Path(__file__).resolve().parents[1]


class Page:
    """只模拟 pdfplumber 的字符坐标与表格边界，不模拟提取逻辑。"""

    def __init__(self):
        self.chars = []
        self.cells = []

    def add_text(self, text, x, top, width=6):
        for index, char in enumerate(text):
            self.chars.append({"text": char, "x0": x + index * width,
                               "x1": x + (index + 1) * width,
                               "top": top, "bottom": top + 10})

    def centered(self, text, center, top):
        self.add_text(text, center - len(text) * 3, top)

    def right_aligned(self, text, right, top):
        self.add_text(text, right - len(text) * 6, top)

    def find_tables(self):
        return [SimpleNamespace(cells=self.cells)] if self.cells else []

    def close(self):
        pass


def direct_page(value="27,767.80", tables=True, wrapped_header=False):
    page = Page()
    page.add_text("项目", 10, 10)
    page.centered("栏次", 250, 10)
    if wrapped_header:
        page.centered("一般项目", 375, 2)
        page.centered("本期数", 375, 17)
    else:
        page.centered("一般项目本期数", 375, 10)
    page.centered("即征即退项目本期数", 525, 10)
    page.add_text("期末留抵税额", 10, 40)
    page.add_text("0B08=0B05-0B06", 205, 40)
    page.right_aligned(value, 440, 40)
    page.right_aligned("999.99", 590, 40)
    if tables:
        page.cells = [(left, top, right, bottom)
                      for top, bottom in ((0, 30), (30, 60))
                      for left, right in ((0, 200), (200, 300), (300, 450), (450, 600))]
    return page


def grouped_page(value="32,975.52", tables=True):
    page = Page()
    page.centered("一般项目", 450, 5)
    page.centered("即征即退项目", 750, 5)
    for label, center in (("本月数", 375), ("本年累计", 525),
                          ("本月数", 675), ("本年累计", 825)):
        page.centered(label, center, 25)
    page.add_text("期末留抵税额", 10, 45)
    page.add_text("20＝17－18", 220, 45)
    for text, right in ((value, 440), ("888.88", 590), ("999.99", 740), ("--", 890)):
        page.right_aligned(text, right, 45)
    if tables:
        page.cells = [(0, 0, 200, 40), (200, 0, 300, 40),
                      (300, 0, 600, 20), (600, 0, 900, 20)]
        page.cells += [(left, 20, left + 150, 40) for left in (300, 450, 600, 750)]
        page.cells += [(0, 40, 200, 65), (200, 40, 300, 65)]
        page.cells += [(left, 40, left + 150, 65) for left in (300, 450, 600, 750)]
    return page


class ExtractionTests(unittest.TestCase):
    def test_both_formats_with_and_without_table_boundaries(self):
        for factory, amount, name in ((direct_page, "27767.80", "一般项目本期数"),
                                      (grouped_page, "32975.52", "一般项目/本月数")):
            for tables in (True, False):
                with self.subTest(format=factory.__name__, tables=tables):
                    results = vat.extract_page(factory(tables=tables), Path("form.pdf"), 3)
                    self.assertEqual(len(results), 1)
                    self.assertEqual(results[0].amount, amount)
                    self.assertEqual(results[0].column, name)
                    self.assertEqual(results[0].page, 3)
                    self.assertEqual(results[0].status, "ok")

    def test_wrapped_header_in_one_cell(self):
        result, = vat.extract_page(direct_page(wrapped_header=True), Path("form.pdf"), 1)
        self.assertEqual(result.amount, "27767.80")

    def test_wrapped_target_label_in_one_cell(self):
        page = direct_page()
        page.chars = [c for c in page.chars if not (c["x0"] < 200 and c["top"] == 40)]
        page.add_text("期末留抵", 10, 31)
        page.add_text("税额", 10, 46)
        # PDF 内容流不保证同一单元格的字符相邻，按页面扫描顺序重排。
        page.chars.sort(key=lambda c: (c["top"], c["x0"]))
        result, = vat.extract_page(page, Path("form.pdf"), 1)
        self.assertEqual(result.amount, "27767.80")

    def test_wrapped_target_without_header_reports_column_error(self):
        page = Page()
        page.add_text("期末留抵", 10, 31)
        page.add_text("税额", 10, 46)
        page.add_text("849.06", 350, 35)
        page.cells = [(0, 30, 200, 60), (300, 30, 450, 60)]
        result, = vat.extract_page(page, Path("form.pdf"), 1)
        self.assertEqual(result.status, "column_not_found")

    def test_missing_and_invalid_values_do_not_take_adjacent_columns(self):
        for factory in (direct_page, grouped_page):
            for tables in (True, False):
                for value, status, amount in (("", "missing_value", ""),
                                               ("——", "missing_value", ""),
                                               ("0.00", "ok", "0.00"),
                                               ("12,34.56", "invalid_value", "")):
                    with self.subTest(format=factory.__name__, tables=tables, value=value):
                        result, = vat.extract_page(factory(value, tables), Path("form.pdf"), 1)
                        self.assertEqual((result.status, result.amount), (status, amount))

    def test_table_detection_error_uses_coordinates(self):
        page = direct_page()
        with patch.object(page, "find_tables", side_effect=ValueError("broken grid")):
            result, = vat.extract_page(page, Path("form.pdf"), 1)
        self.assertEqual(result.amount, "27767.80")

    def test_unknown_header_is_reported(self):
        page = Page()
        page.add_text("期末留抵税额", 10, 40)
        page.right_aligned("123.45", 440, 40)
        result, = vat.extract_page(page, Path("form.pdf"), 1)
        self.assertEqual(result.status, "column_not_found")
        self.assertEqual(result.amount, "")

    def test_every_matching_page_is_returned(self):
        pdf = SimpleNamespace(pages=[Page(), direct_page("849.06"), grouped_page("17,400.70")])
        library = SimpleNamespace(open=lambda path: contextlib.nullcontext(pdf))
        with patch.object(vat, "_load_pdfplumber", return_value=library):
            results = vat.extract_pdf("form.pdf")
        self.assertEqual([(r.page, r.amount) for r in results], [(2, "849.06"), (3, "17400.70")])

    def test_no_text_and_no_target_have_distinct_status(self):
        text_page = Page()
        text_page.add_text("其他表格", 0, 0)
        for page, status in ((Page(), "unsupported_pdf"), (text_page, "not_found")):
            with self.subTest(status=status):
                library = SimpleNamespace(open=lambda path: contextlib.nullcontext(SimpleNamespace(pages=[page])))
                with patch.object(vat, "_load_pdfplumber", return_value=library):
                    result, = vat.extract_pdf("form.pdf")
                self.assertEqual(result.status, status)

    def test_one_file_error_does_not_stop_directory_processing(self):
        def open_pdf(path):
            if path.name == "a.pdf":
                raise ValueError("damaged or encrypted")
            return contextlib.nullcontext(SimpleNamespace(pages=[direct_page("0.00")]))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.pdf").touch()
            (root / "b.pdf").touch()
            with patch.object(vat, "_load_pdfplumber", return_value=SimpleNamespace(open=open_pdf)):
                results = vat.extract_directory(root)
        self.assertEqual([r.status for r in results], ["read_error", "ok"])
        self.assertEqual(results[1].amount, "0.00")


class AmountAndOutputTests(unittest.TestCase):
    def test_decimal_normalization(self):
        cases = {"32,975.52": "32975.52", "0.00": "0.00", "１２３．４５": "123.45",
                 " 1, 234.50\n": "1234.50", "−1.5": "-1.50", "100": "100.00"}
        for raw, amount in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(vat.parse_amount(raw), amount)
        for raw in ("", "--", "——", "－"):
            self.assertIsNone(vat.parse_amount(raw))
        for raw in ("20=17-18", "12,34.56", "0.000.00", "1.234", "NaN"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                vat.parse_amount(raw)

    def test_recursion_case_insensitive_suffix_and_csv_bom(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "子目录").mkdir()
            (root / "a.pdf").touch()
            (root / "not.pdf.txt").touch()
            nested = root / "子目录" / "b.PDF"
            nested.touch()
            self.assertEqual(len(vat.find_pdfs(root)), 2)
            self.assertEqual(vat.find_pdfs(root, recursive=False), [root / "a.pdf"])
            output = root / "result.csv"
            vat.write_csv([vat.Result(str(nested), 1, "一般项目/本月数", "0.00")], output)
            self.assertTrue(output.read_bytes().startswith(b"\xef\xbb\xbf"))
            with output.open(encoding="utf-8-sig", newline="") as handle:
                row, = list(csv.DictReader(handle))
            self.assertEqual(row["期末留抵税额"], "0.00")
            self.assertEqual(row["文件路径"], str(nested))

    def test_empty_directory_writes_header_only(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(vat.main([directory]), 0)
            with (Path(directory) / "vat_credit_results.csv").open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.reader(handle))
        self.assertEqual(rows, [list(vat.CSV_FIELDS)])

    def test_cli_records_success_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "a.pdf"
            path.touch()
            for status, expected_code in (("ok", 0), ("read_error", 1)):
                result = vat.Result(str(path), 1, amount="0.00" if status == "ok" else "", status=status)
                with patch.object(vat, "_load_pdfplumber"), patch.object(vat, "extract_pdf", return_value=[result]):
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(vat.main([directory]), expected_code)


@unittest.skipUnless(importlib.util.find_spec("pdfplumber"), "未安装 pdfplumber，跳过真实 PDF 回归")
class SamplePDFTests(unittest.TestCase):
    def test_four_sample_pdfs(self):
        samples = [("*218D9926*.pdf", 3, "849.06"),
                   ("*4804AD73*.pdf", 3, "27767.80"),
                   ("增值税及附加税费申报表（一般纳税人适用）.pdf", 1, "32975.52"),
                   ("增值税及附加税费申报（一般纳税人适用）.pdf", 1, "17400.70")]
        paths = [(list(ROOT.glob(pattern)), page, amount) for pattern, page, amount in samples]
        if any(len(matches) != 1 for matches, _, _ in paths):
            self.skipTest("本目录缺少四份唯一的 PDF 样例")
        for matches, page, amount in paths:
            path, = matches
            with self.subTest(pdf=path.name):
                result, = vat.extract_pdf(path)
                self.assertEqual(result.status, "ok", result.message)
                self.assertEqual((result.page, result.amount), (page, amount))


if __name__ == "__main__":
    unittest.main()
