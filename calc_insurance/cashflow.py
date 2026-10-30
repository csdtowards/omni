#!/usr/bin/env python3
"""Generate the user-confirmed fixed-base pension cash-flow comparison.

Money is calculated with Decimal. Integer age-months define the timing:
the retirement-age snapshot includes all contributions and no pension yet;
the first pension appears one month later. Rendering is shared by the offline
HTML and SVG export, using the local Node.js runtime without dependencies.
"""

import argparse
import csv
import io
import json
import subprocess
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP
from pathlib import Path


D = Decimal
BASES = (7546, 12577, 37731)
YEARS = (15, 20, 25, 30, 35, 38)
PENSION_BASE = D(12577)
RETIREMENT_AGE = 60
DIVISOR = 139
MAX_AGE = 100
DEFAULT_END_AGE = 85
SCOPES = {'personal': ('个人缴费8%', D('.08')), 'combined': ('个人加单位24%', D('.24'))}
COLORS = {15: '#2563eb', 20: '#0d9488', 25: '#d97706', 30: '#b453c7', 35: '#dc4f55', 38: '#4f46b8'}
ROOT = Path(__file__).parent


def money(value):
    return str(value.quantize(D('.01'), rounding=ROUND_HALF_UP))


def age_label(age_month):
    years, months = divmod(age_month, 12)
    return f'{years}岁' + (f'{months}个月' if months else '')


@dataclass(frozen=True)
class Scenario:
    base: int
    years: int

    @property
    def id(self):
        return f'b{self.base}-y{self.years}'

    @property
    def start_month(self):
        return (RETIREMENT_AGE - self.years) * 12

    @property
    def account_balance(self):
        return D(self.base) * D('.08') * 12 * self.years

    @property
    def basic_pension(self):
        return (PENSION_BASE + self.base) / 2 * self.years * D('.01')

    @property
    def personal_pension(self):
        return self.account_balance / DIVISOR

    @property
    def pension(self):
        return self.basic_pension + self.personal_pension

    def monthly_cost(self, scope):
        return D(self.base) * SCOPES[scope][1]

    def total_cost(self, scope):
        return self.monthly_cost(scope) * 12 * self.years

    def break_even_months(self, scope):
        return int((self.total_cost(scope) / self.pension).to_integral_value(rounding=ROUND_CEILING))

    def snapshot(self, scope, age_month):
        if age_month < self.start_month:
            return None
        paid_months = min(age_month - self.start_month, self.years * 12)
        pension_months = max(0, age_month - RETIREMENT_AGE * 12)
        paid = self.monthly_cost(scope) * paid_months
        received = self.pension * pension_months
        return {'paid': paid, 'received': received, 'net': received - paid}

    def ui_data(self):
        costs = {}
        for scope in SCOPES:
            months = self.break_even_months(scope)
            costs[scope] = {
                'monthly': float(self.monthly_cost(scope)),
                'total': float(self.total_cost(scope)),
                'break_even_months': months,
                'break_even_age_month': RETIREMENT_AGE * 12 + months,
                'break_even_label': age_label(RETIREMENT_AGE * 12 + months),
                'continuous_zero_age': float(D(RETIREMENT_AGE) + self.total_cost(scope) / self.pension / 12),
            }
        return {
            'id': self.id, 'base': self.base, 'years': self.years,
            'start_age': RETIREMENT_AGE - self.years,
            'monthly_pension': float(self.pension),
            'basic_pension': float(self.basic_pension),
            'personal_pension': float(self.personal_pension),
            'account_balance': float(self.account_balance), 'costs': costs,
        }


def summary_csv(scenarios):
    f = io.StringIO(newline='')
    writer = csv.writer(f)
    writer.writerow([
        '方案', '月缴费基数_元', '缴费年限', '起缴年龄_岁', '月个人缴费_元', '月个人加单位缴费_元',
        '个人累计成本_元', '个人加单位累计成本_元', '个人账户余额_元', '基础养老金_元每月',
        '个人账户养老金_元每月', '养老金合计_元每月', '个人口径回正领金月数', '个人口径回正年龄',
        '个人加单位口径回正领金月数', '个人加单位口径回正年龄', '结果性质',
    ])
    for s in scenarios:
        writer.writerow([
            s.id, s.base, s.years, RETIREMENT_AGE - s.years,
            money(s.monthly_cost('personal')), money(s.monthly_cost('combined')),
            money(s.total_cost('personal')), money(s.total_cost('combined')), money(s.account_balance),
            money(s.basic_pension), money(s.personal_pension), money(s.pension),
            s.break_even_months('personal'), age_label(720 + s.break_even_months('personal')),
            s.break_even_months('combined'), age_label(720 + s.break_even_months('combined')),
            '固定基数固定费率零利息条件估算',
        ])
    return '\ufeff' + f.getvalue()


def annual_csv(scenarios):
    f = io.StringIO(newline='')
    writer = csv.writer(f)
    writer.writerow([
        '方案', '月缴费基数_元', '缴费年限', '成本口径', '年龄_岁', '时点',
        '本年度缴费现金流_元', '本年度养老金收入_元', '本年度净现金流_元',
        '累计缴费支出_元', '累计养老金收入_元', '累计净现金流_元',
    ])
    for s in scenarios:
        for scope, (label, _) in SCOPES.items():
            previous = {'paid': D(0), 'received': D(0), 'net': D(0)}
            for age in range(RETIREMENT_AGE - s.years, MAX_AGE + 1):
                current = s.snapshot(scope, age * 12)
                phase = '起缴时点' if age * 12 == s.start_month else '缴费结束' if age == 60 else '缴费期末' if age < 60 else '退休后年末'
                writer.writerow([
                    s.id, s.base, s.years, label, age, phase,
                    money(previous['paid'] - current['paid']), money(current['received'] - previous['received']),
                    money(current['net'] - previous['net']), money(current['paid']),
                    money(current['received']), money(current['net']),
                ])
                previous = current
    return '\ufeff' + f.getvalue()


def build_data(scenarios):
    return {
        'bases': list(BASES), 'years': list(YEARS), 'colors': COLORS,
        'retirement_age': RETIREMENT_AGE, 'pension_base': int(PENSION_BASE), 'divisor': DIVISOR,
        'min_age': 22, 'max_age': MAX_AGE, 'default_end_age': DEFAULT_END_AGE,
        'scopes': [{'id': key, 'label': label, 'rate': float(rate)} for key, (label, rate) in SCOPES.items()],
        'scenarios': [s.ui_data() for s in scenarios],
        'assumptions': [
            '三档月缴费基数全程固定为7,546、12,577、37,731元；35年、38年情景不使用历史基数。',
            '个人缴费8%，单位缴费16%，个人账户计入8%；第二种成本包含两者合计24%。',
            '60岁退休，计发月数139；养老金计发基数暂取12,577元/月，为用户确认的演算参数。',
            '不计记账利息、工资增长、养老金年度调整及折现，不含过渡性养老金。',
            '60岁时已缴完全部费用，尚未领取首月养老金；之后每月领金，模型持续计算至100岁。',
            '139仅用于计算月养老金，不表示领满139个月后停止领取。',
            '回正年龄为累计现金流首次非负的月末；起缴前不画线，年度值是整岁时点的累计额。',
        ],
    }


def html_document(data, script):
    encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    return '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>社保累计现金流与回正年龄</title>
<style>
.comparison-section{margin-bottom:26px}.comparison-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:0 0 12px}.comparison-head h2{margin:0}.comparison-card{overflow:auto;border-radius:15px;border:1px solid #dfe6df;background:white}.comparison-card svg{display:block;width:100%;height:auto;min-width:760px}
:root{color-scheme:light;font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;color:#172b3a;background:#f5f6f2}*{box-sizing:border-box}body{margin:0}main{max-width:1540px;margin:auto;padding:40px 28px 60px}.eyebrow{font-size:12px;letter-spacing:.18em;color:#4a6b62;font-weight:700}h1{font-size:clamp(26px,4vw,42px);letter-spacing:-.04em;margin:10px 0 12px}h2{font-size:21px;margin:0 0 12px}.intro{color:#52636e;line-height:1.8;max-width:960px;margin:0}.assumption-bar{margin:20px 0;background:#e8eee8;border:1px solid #dce6dc;border-radius:12px;padding:14px 18px;line-height:1.9;font-size:14px}.controls{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;margin:24px 0 18px}.legend{display:flex;gap:8px;flex-wrap:wrap}.legend button,button,select{font:inherit;border:1px solid #d5ddd7;border-radius:8px;background:white;color:#233e48;padding:9px 12px;cursor:pointer}.legend button{font-size:13px}.legend button[aria-pressed=false]{opacity:.38}.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}button:focus-visible,select:focus-visible{outline:3px solid #5f8ec5;outline-offset:2px}.tools{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.tools label{font-size:13px;color:#52636e}.primary{background:#234d42;color:#fff;border-color:#234d42}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.chart-card{background:white;border:1px solid #dfe6df;border-radius:15px;overflow:hidden;min-width:0}.chart-card svg{display:block;width:100%;height:auto;touch-action:pan-y}.note{margin:16px 0 30px;line-height:1.8;font-size:13px;color:#52636e}.details{margin-top:28px;padding:24px;background:white;border:1px solid #dfe6df;border-radius:15px}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px;white-space:nowrap}th,td{padding:11px 12px;border-bottom:1px solid #e8ede8;text-align:right}th:first-child,td:first-child{text-align:left}th{font-weight:600;color:#4b626c;background:#f7f9f6}tbody tr:hover{background:#f3f7f1}.download-row{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0}.assumptions{font-size:14px;line-height:1.85;color:#52636e;padding-left:20px}.tooltip{position:fixed;z-index:10;pointer-events:none;background:rgba(20,40,47,.97);color:#fff;border-radius:11px;padding:13px 16px;min-width:240px;font-size:12px;box-shadow:0 6px 28px #0002;line-height:1.85}.tooltip strong{display:block;font-size:13px;margin-bottom:6px}.tooltip .tiprow{display:flex;justify-content:space-between;gap:24px}.tooltip em{font-style:normal;color:#c9d8d1}footer{margin-top:22px;color:#697c80;font-size:12px;line-height:1.8}@media(max-width:1050px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:680px){main{padding:24px 12px}.grid{grid-template-columns:1fr}.details{padding:16px 10px}.tools{width:100%}.tooltip{min-width:220px}}
</style></head><body><main>
<div class="eyebrow">社保 · 累计收支</div><h1>从缴费到领金，何时回到零？</h1>
<p class="intro">三档固定月缴费基数，六种缴费年限。缴费阶段向下累计支出，60岁后逐月加上养老金。上排只计个人8%的成本，下排计个人加单位24%的成本。</p>
<div class="assumption-bar">计发基数演算值 <b>12,577元/月</b> · 60岁退休 · 计发月数139 · 不计利息与年度调整<br>本图为已确认参数下的简化估算；养老金按固定月额持续计入，139只作为计发除数。</div>
<div class="controls"><div class="legend" id="legend" aria-label="筛选缴费年限"></div><div class="tools"><label for="end-age">展示至</label><select id="end-age"><option value="80">80岁</option><option value="85" selected>85岁</option><option value="90">90岁</option><option value="100">100岁</option></select><button id="download-svg" class="primary">下载当前总览图</button></div></div>
<section id="base-comparison" class="comparison-section"><div class="comparison-head"><h2>7,546元与37,731元 · 个人加单位成本同轴对比</h2><button id="download-comparison">下载两档对比图</button></div><div id="comparison-chart" class="comparison-card" aria-label="两档基数个人加单位成本同轴对比"></div><p class="note">颜色表示缴费年限；实线为7,546元基数，虚线为37,731元基数。两档使用同一金额轴，可直接比较累计成本和退休后的累计净收入。上方的年限筛选及展示年龄同时作用于这张图。</p></section>
<div id="charts" class="grid" aria-label="六幅累计现金流图"></div>
<p class="note">实线为累计现金流，横向零线为累计收支平衡；60岁虚线右侧为领取阶段。回正年龄按首次累计非负的月末计算。同一基数下，缴费年限增加会同时提高成本和养老金，因此回正年龄相同。相同基数的上下两图使用相同纵轴范围。</p>
<section class="details"><h2>18个方案的金额与回正年龄</h2><p class="intro">金额单位：元。个人加单位成本包含个人部分；两种成本口径使用相同的月养老金。表格随年限筛选同步更新。</p><div class="download-row"><button id="download-summary">下载方案汇总CSV</button><button id="download-annual">下载年度明细CSV</button></div><div class="table-wrap"><table><thead><tr><th>月缴费基数</th><th>缴费年限</th><th>起缴年龄</th><th>个人累计成本</th><th>个人加单位累计成本</th><th>月养老金</th><th>个人口径回正年龄</th><th>合计口径回正年龄</th></tr></thead><tbody id="summary-body"></tbody></table></div></section>
<section class="details"><h2>计算口径</h2><ul id="assumptions" class="assumptions"></ul><p class="intro">月养老金＝(12,577＋固定月缴费基数)÷2×缴费年限×1%＋固定月缴费基数×8%×12×缴费年限÷139。累计现金流＝累计养老金收入－所选口径的累计缴费成本。</p></section>
<footer>年度明细覆盖各方案起缴年龄至100岁。图中折线连接月末累计值，未作平滑处理。金额显示时四舍五入，内部按未舍入金额计算。固定基数与费率是演算假设，实际退休资格及待遇以核定为准。</footer>
<noscript><p>交互图需要启用JavaScript。可打开同目录中的“社保累计现金流.svg”查看静态总览。</p></noscript>
</main><div id="tooltip" class="tooltip" hidden></div>
<script id="cashflow-data" type="application/json">''' + encoded + '''</script><script>''' + script + '''</script></body></html>'''


def write_report(scenarios, out):
    lines = [
        '# 固定基数社保累计现金流', '',
        '已生成18个方案、两种成本口径的36条曲线。', '',
        '- 交互图：[社保累计现金流.html](社保累计现金流.html)',
        '- 静态总览：[社保累计现金流.svg](社保累计现金流.svg)',
        '- 两档同轴对比：[两档基数合计成本对比.svg](两档基数合计成本对比.svg)，7546元实线、37731元虚线，均按个人加单位24%成本；共12条曲线。',
        '- 方案汇总：[现金流方案汇总.csv](现金流方案汇总.csv)',
        '- 年度明细：[现金流年度明细.csv](现金流年度明细.csv)', '',
        '## 回正年龄', '',
        '同一基数下，六种年限的成本与养老金均同比增加，因而回正月份相同。', '',
        '| 固定月缴费基数 | 个人8%口径 | 个人加单位24%口径 |',
        '|---:|---:|---:|',
    ]
    for base in BASES:
        s = next(s for s in scenarios if s.base == base)
        labels = [f'{age_label(720+s.break_even_months(scope))}（领金第{s.break_even_months(scope)}个月）' for scope in SCOPES]
        lines.append('| ' + ' | '.join([str(base), *labels]) + ' |')
    lines.extend([
        '', '## 方案金额', '',
        '| 月缴费基数 | 年限 | 个人累计成本（元） | 个人加单位累计成本（元） | 基础养老金（元/月） | 个人账户养老金（元/月） | 月养老金合计（元） |',
        '|---:|---:|---:|---:|---:|---:|---:|',
    ])
    for s in scenarios:
        lines.append('| ' + ' | '.join([str(s.base), str(s.years), money(s.total_cost('personal')), money(s.total_cost('combined')), money(s.basic_pension), money(s.personal_pension), money(s.pension)]) + ' |')
    lines.extend(['', '## 口径与时点', ''])
    lines.extend('- ' + item for item in build_data(scenarios)['assumptions'])
    lines.extend([
        '', '公式：月养老金＝(12577＋月缴费基数)÷2×缴费年限×1%＋月缴费基数×8%×12×缴费年限÷139。', '',
        '累计现金流在60岁时为负的全部缴费成本；到60岁1个月计入首月养老金。年度CSV记录整岁时点，年度现金流为相邻时点之差；首行是起缴瞬间，现金流为0。', '',
        '本次以全程固定基数测算；此前的历史基数16种情景继续保留在原文件中。养老金演算值不是已核实的官方计发基数。', '',
        '复现：`python3 cashflow.py`。Python只使用标准库；生成SVG使用已安装的Node.js和本地渲染脚本。打开HTML或SVG无需Node.js或网络。', '',
    ])
    (out / '现金流测算说明.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'output')
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    scenarios = [Scenario(base, years) for base in BASES for years in YEARS]
    summary = summary_csv(scenarios)
    annual = annual_csv(scenarios)
    data = build_data(scenarios)
    data['downloads'] = {'summary': summary, 'annual': annual}
    script_path = ROOT / 'cashflow_ui.js'
    script = script_path.read_text(encoding='utf-8')
    encoded = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    renderer = "const fs=require('fs');const charts=require(process.argv[1]);const data=JSON.parse(fs.readFileSync(0,'utf8'));const options={endAge:data.default_end_age,years:data.years};process.stdout.write(JSON.stringify({overview:charts.overviewSvg(data,options),comparison:charts.comparisonSvg(data,options)}));"
    rendered = subprocess.run(['node', '-e', renderer, str(script_path)], input=encoded, text=True, capture_output=True, check=True)
    figures = json.loads(rendered.stdout)
    (out / '社保累计现金流.svg').write_text(figures['overview'], encoding='utf-8')
    (out / '两档基数合计成本对比.svg').write_text(figures['comparison'], encoding='utf-8')
    (out / '社保累计现金流.html').write_text(html_document(data, script), encoding='utf-8')
    (out / '现金流方案汇总.csv').write_text(summary, encoding='utf-8', newline='')
    (out / '现金流年度明细.csv').write_text(annual, encoding='utf-8', newline='')
    # A compact numerical source for chart checks; downloadable CSV stays embedded in HTML.
    (out / '现金流图表数据.json').write_text(json.dumps({k: v for k, v in data.items() if k != 'downloads'}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    write_report(scenarios, out)
    print(json.dumps({'scenarios': len(scenarios), 'curves': len(scenarios) * len(SCOPES), 'comparison_curves': 12, 'default_end_age': DEFAULT_END_AGE, 'data_end_age': MAX_AGE, 'output': str(out)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
