#!/usr/bin/env python3
"""Shanghai pension scenario calculator. Missing historical inputs stay missing.

All monetary calculations use Decimal. Annual account interest uses explicit
weights supplied with the historical policy data; this module does not invent
a historical interest convention or assume monthly compound interest.
"""

import argparse
import csv
import json
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path


YEARS = (15, 20, 25, 30)
INDICES = (Decimal('0.6'), Decimal('1'), Decimal('2'), Decimal('3'))
RATE_FIELDS = ('employee_rate', 'employer_rate', 'account_credit_rate')
MONTH_FIELDS = (
    'month', 'reference_base', *RATE_FIELDS, 'status', 'source', 'note',
    'lower_base', 'upper_base', 'base_status', 'base_source',
)
INTEREST_FIELDS = (
    'year', 'annual_rate', 'opening_balance_weight',
    *(f'month_{m:02d}_weight' for m in range(1, 13)),
    'status', 'source', 'note',
)
VALID_STATUSES = {'verified', 'forecast', 'user_provided', 'derived_user_provided', 'assumption'}


def months_between(start, end):
    y, m = map(int, start.split('-'))
    ey, em = map(int, end.split('-'))
    if not 1 <= m <= 12 or not 1 <= em <= 12:
        raise ValueError('月份必须在1至12之间')
    while (y, m) <= (ey, em):
        yield f'{y:04d}-{m:02d}'
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def start_month(retirement_month, years):
    y, m = map(int, retirement_month.split('-'))
    return f'{y - years + (m == 12):04d}-{1 if m == 12 else m + 1:02d}'


def dec(value, label, minimum=Decimal('0'), maximum=None):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f'{label}必须是有效数字') from None
    if not result.is_finite() or result < minimum:
        raise ValueError(f'{label}超出允许范围')
    if maximum is not None and result > maximum:
        raise ValueError(f'{label}超出允许范围')
    return result


def load_csv(path, key, expected):
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != list(expected):
            raise ValueError(f'{path.name}列名不符合模板')
        rows = {}
        for row in reader:
            value = row[key]
            if value in rows:
                raise ValueError(f'{path.name}存在重复记录：{value}')
            rows[value] = row
    return rows


def complete(row, fields, label, issues):
    if row is None:
        issues.add(f'{label}：缺少记录')
        return False
    missing = [field for field in fields if row.get(field, '') in ('', None)]
    if row.get('status') not in VALID_STATUSES:
        missing.append('status（须为已核验、用户提供、据用户数据推算或预测）')
    if not str(row.get('source', '')).strip():
        missing.append('source')
    if row.get('status') in {'forecast', 'assumption'} and not str(row.get('note', '')).strip():
        missing.append('note（预测或假设依据）')
    if missing:
        issues.add(f'{label}：缺少或未核验 ' + '、'.join(missing))
        return False
    return True


def verified_month(row, label, issues):
    if row is None:
        issues.add(f'{label}：缺少记录')
        return None
    base_row = {
        **row,
        'status': row.get('base_status') or row.get('status'),
        'source': row.get('base_source') or row.get('source'),
    }
    base_ok = complete(base_row, ('reference_base',), label + '缴费基数', issues)
    rates_ok = complete(row, RATE_FIELDS, label + '缴费费率', issues)
    if not base_ok or not rates_ok:
        return None
    values = {'reference_base': dec(row['reference_base'], label + ' reference_base')}
    if values['reference_base'] == 0:
        raise ValueError(f'{label}缴费基数基准必须大于0')
    for field in RATE_FIELDS:
        values[field] = dec(row[field], label + ' ' + field, maximum=Decimal('1'))
    if values['account_credit_rate'] > values['employee_rate'] + values['employer_rate']:
        raise ValueError(f'{label}个人账户计入额超过养老保险缴费合计，请核对历史规则')
    for field in ('lower_base', 'upper_base'):
        values[field] = None if row.get(field, '') in ('', None) else dec(row[field], label + ' ' + field)
    if values['lower_base'] is not None and values['upper_base'] is not None:
        if values['lower_base'] > values['upper_base']:
            raise ValueError(f'{label}缴费基数下限超过上限')
    return values


def contribution_base(row, index):
    amount = row['reference_base'] * index
    if row.get('lower_base') is not None:
        amount = max(amount, row['lower_base'])
    if row.get('upper_base') is not None:
        amount = min(amount, row['upper_base'])
    return amount


def account_interest(row, year, end_month, opening, additions, issues):
    fields = ('annual_rate', 'opening_balance_weight', *(
        f'month_{m:02d}_weight' for m in additions
    ))
    label = f'{year}年个人账户利息'
    if not complete(row, fields, label, issues):
        return None
    rate = dec(row['annual_rate'], label + '利率', maximum=Decimal('1'))
    opening_weight = dec(row['opening_balance_weight'], label + '期初权重', maximum=Decimal('1'))
    if opening_weight > Decimal(end_month) / 12 + Decimal('0.000000000001'):
        raise ValueError(f'{label}：期初余额计息期间超过退休前月份')
    weighted = opening * opening_weight
    for month, amount in additions.items():
        weight = dec(row[f'month_{month:02d}_weight'], label + f'{month}月权重', maximum=Decimal('1'))
        maximum = Decimal(end_month - month + 1) / 12
        if weight > maximum + Decimal('0.000000000001'):
            raise ValueError(f'{label}：{month}月新增资金计息期间超过剩余月份')
        weighted += amount * weight
    return weighted * rate


def simulate_account(monthly, interest, retirement_month, index, issues):
    if any(row is None for _, row in monthly):
        return None, []
    balance = Decimal('0')
    annual = []
    retirement_year, retirement_m = map(int, retirement_month.split('-'))
    for year in sorted({int(month[:4]) for month, _ in monthly}):
        additions = {
            int(month[5:]): contribution_base(row, index) * row['account_credit_rate']
            for month, row in monthly if int(month[:4]) == year
        }
        end_month = retirement_m if year == retirement_year else 12
        earnings = account_interest(interest.get(str(year)), year, end_month, balance, additions, issues)
        if earnings is None:
            return None, []
        added = sum(additions.values(), Decimal('0'))
        closing = balance + added + earnings
        annual.append({'year': year, 'opening': balance, 'credited': added, 'interest': earnings, 'closing': closing})
        balance = closing
    return balance, annual


def calculate(config, monthly_rows, interest_rows):
    if config.get('age_at_retirement') != 60 or config.get('insurance_type') != 'enterprise_employee':
        raise ValueError('本模型仅实现已确认的60岁企业职工情景')
    retirement = config['retirement_month']
    date.fromisoformat(retirement + '-01')
    base_input = config['pension_base']
    issues = set()
    base_row = {
        'amount': base_input.get('monthly_amount'),
        'period': base_input.get('reference_period'),
        'status': base_input.get('status'),
        'source': base_input.get('source'),
        'note': base_input.get('note'),
    }
    base = None
    if complete(base_row, ('amount', 'period'), '养老金计发基数', issues):
        if base_row['status'] != 'verified' and not (
            base_row['status'] == 'assumption' and config.get('allow_assumed_pension_base')
        ):
            raise ValueError('养老金计发基数须为已核验值，或明确获准使用的估算参数')
        base = dec(base_row['amount'], '养老金计发基数')
        if base == 0:
            raise ValueError('养老金计发基数必须大于0')
    divisor = dec(config['payout_months'], '个人账户计发月数')
    if divisor == 0:
        raise ValueError('个人账户计发月数必须大于0')
    if config.get('payout_months_status') != 'verified':
        issues.add('60岁适用计发月数139：当前作为待核验计算假设')
    if config.get('retirement_eligibility_status') != 'verified':
        issues.add('退休资格与起领时间：须核对弹性提前退休条件，不视为已确认可退休')
    full_calendar = list(months_between(start_month(retirement, max(YEARS)), retirement))
    for year in sorted({int(month[:4]) for month in full_calendar}):
        end_month = int(retirement[5:]) if year == int(retirement[:4]) else 12
        additions = {int(month[5:]): Decimal('0') for month in full_calendar if int(month[:4]) == year}
        account_interest(interest_rows.get(str(year)), year, end_month, Decimal('0'), additions, issues)
    results = []
    details = []
    for years in YEARS:
        start = start_month(retirement, years)
        calendar = list(months_between(start, retirement))
        if len(calendar) != years * 12:
            raise ValueError('缴费月份数量与年限不符')
        monthly = [(month, verified_month(monthly_rows.get(month), month, issues)) for month in calendar]
        monthly_complete = all(row is not None for _, row in monthly)
        has_forecast = any(
            monthly_rows.get(m, {}).get('status') == 'forecast' or monthly_rows.get(m, {}).get('base_status') == 'forecast'
            for m in calendar
        )
        has_forecast |= any(
            interest_rows.get(str(y), {}).get('status') == 'forecast'
            for y in range(int(start[:4]), int(retirement[:4]) + 1)
        )
        for index in INDICES:
            effective_index = index
            if monthly_complete:
                effective_index = sum((contribution_base(row, index) / row['reference_base'] for _, row in monthly), Decimal('0')) / len(monthly)
            coefficient = (1 + effective_index) / 2 * Decimal(years) * Decimal('0.01')
            basic = None if base is None else base * coefficient
            employee = employer = total_paid = None
            if monthly_complete:
                employee = sum((contribution_base(row, index) * row['employee_rate'] for _, row in monthly), Decimal('0'))
                employer = sum((contribution_base(row, index) * row['employer_rate'] for _, row in monthly), Decimal('0'))
                total_paid = employee + employer
            account, annual = simulate_account(monthly, interest_rows, retirement, index, issues)
            personal_pension = None if account is None else account / divisor
            total_pension = None if basic is None or personal_pension is None else basic + personal_pension
            results.append({
                'years': years, 'index': index, 'start_month': start,
                'end_month': retirement, 'months': len(calendar),
                'employee_paid': employee, 'employer_paid': employer, 'total_paid': total_paid,
                'account_balance': account, 'basic_coefficient': coefficient,
                'effective_index': effective_index if monthly_complete else None,
                'basic_pension': basic, 'personal_pension': personal_pension,
                'total_pension': total_pension, 'includes_forecast': has_forecast,
            })
            details.extend({'years': years, 'index': index, **row} for row in annual)
    return results, details, sorted(issues)


def money(value):
    return '' if value is None else str(value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))


def percent(value):
    return format(value * 100, '.6f').rstrip('0').rstrip('.') + '%'


def marginal_comparisons(results):
    lookup = {(row['years'], row['index']): row for row in results}
    pairs = []
    for index in INDICES:
        for before, after in zip(YEARS, YEARS[1:]):
            pairs.append(('增加缴费年限', lookup[before, index], lookup[after, index]))
    for years in YEARS:
        for before, after in zip(INDICES, INDICES[1:]):
            pairs.append(('提高缴费档位', lookup[years, before], lookup[years, after]))
    return pairs


def write_outputs(config, results, details, issues, out):
    out.mkdir(parents=True, exist_ok=True)
    computed_all = all(r['total_pension'] is not None and r['total_paid'] is not None for r in results)
    columns = [
        ('years', '缴费年限'), ('index', '缴费档位'), ('start_month', '缴费开始月份'),
        ('end_month', '缴费结束月份'), ('months', '缴费月数'),
        ('employee_paid', '个人累计缴费_元'), ('employer_paid', '单位累计缴费_元'),
        ('total_paid', '累计缴费合计_元'), ('account_balance', '退休时个人账户余额_元'),
        ('effective_index', '模型平均缴费指数_基数受限时调整'),
        ('basic_coefficient', '基础养老金占计发基数比例'), ('basic_pension', '基础养老金_元每月'),
        ('personal_pension', '个人账户养老金_元每月'), ('total_pension', '养老金合计_元每月'),
        ('includes_forecast', '含预测参数'),
    ]
    money_keys = {key for key, _ in columns if key.endswith('_paid') or key.endswith('_pension') or key == 'account_balance'}
    with (out / '16种情景测算.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([label for _, label in columns] + ['结果状态'])
        for result in results:
            row = []
            for key, _ in columns:
                value = result[key]
                if key in money_keys:
                    value = money(value)
                elif key in ('index', 'basic_coefficient'):
                    value = percent(value)
                elif key == 'includes_forecast':
                    value = '是' if value else '否'
                row.append(value)
            ready = result['total_pension'] is not None and result['total_paid'] is not None
            row.append('条件估算（含假设；结合参数说明阅读）' if ready else '未完成：存在缺失参数')
            writer.writerow(row)
    with (out / '个人账户年度明细.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['缴费年限', '档位', '年份', '年初余额_元', '当年计入_元', '当年利息_元', '期末余额_元'])
        for row in details:
            writer.writerow([row['years'], percent(row['index']), row['year'], *(
                money(row[key]) for key in ('opening', 'credited', 'interest', 'closing')
            )])
    with (out / '增加年限与提高档位对比.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['比较方式', '原年限', '原档位', '新年限', '新档位', '个人累计缴费增加_元', '单位累计缴费增加_元', '月养老金增加_元', '基础养老金占B比例增加'])
        for kind, before, after in marginal_comparisons(results):
            differences = [
                None if before[key] is None or after[key] is None else after[key] - before[key]
                for key in ('employee_paid', 'employer_paid', 'total_pension')
            ]
            writer.writerow([
                kind, before['years'], percent(before['index']), after['years'], percent(after['index']),
                *(money(value) for value in differences), percent(after['basic_coefficient'] - before['basic_coefficient']),
            ])
    # Deduplicate missing-data notes by year for the human-readable report.
    absent_months = sorted({item[:7] for item in issues if len(item) >= 8 and item[4] == '-' and item[:4].isdigit() and item[5:7].isdigit()})
    absent_years = sorted({month[:4] for month in absent_months})
    lines = [
        '# 上海养老金与累计缴费：16种情景', '',
        '**状态：' + ('16种情况已按列明假设算出金额，属于简化估算。**' if computed_all else '尚未完成具体金额测算。缺失数据保持空白，空白不代表0元。**'), '',
        '男性，2027年7月满60岁，按企业职工参保、连续缴费至2027年7月测算；',
        '无视同缴费年限，不包含退休后的年度养老金调整。退休资格须另行核对。', '',
        '## 基础养老金关系', '',
        '设本情景采用的月计发基数为 B，以下为基础养老金占 B 的比例；',
        '缺少完整月度参数时，下表按目标指数计算，未反映历史上下限约束；补齐后按模型月均实际缴费比值调整。',
        '**这部分尚未包括个人账户养老金，不能称为每月养老金合计。**', '',
        '| 缴费年限 | 60%档 | 100%档 | 200%档 | 300%档 |',
        '|---|---:|---:|---:|---:|',
    ]
    if base_config := config.get('pension_base'):
        lines.insert(6, f"本情景 B = {base_config.get('monthly_amount') or '待补充'} 元/月；参数性质：{base_config.get('status')}。")
    for years in YEARS:
        cells = [percent(r['basic_coefficient']) + ' × B' for r in results if r['years'] == years]
        lines.append('| ' + ' | '.join([f'{years}年', *cells]) + ' |')
    lines.extend([
        '', '## 金额汇总', '',
        '| 年限 | 档位 | 个人累计缴费（元） | 单位累计缴费（元） | 缴费合计（元） | 月养老金合计（元） |',
        '|---|---:|---:|---:|---:|---:|',
    ])
    for r in results:
        values = [money(r[k]) or '待数据' for k in ('employee_paid', 'employer_paid', 'total_paid', 'total_pension')]
        lines.append('| ' + ' | '.join([str(r['years']), percent(r['index']), *values]) + ' |')
    lines.extend(['', '## 缴费期间', '', '| 年限 | 起止月份（含首尾） | 月数 |', '|---|---|---:|'])
    for years in YEARS:
        r = next(r for r in results if r['years'] == years)
        lines.append(f"| {years}年 | {r['start_month']} 至 {r['end_month']} | {r['months']} |")
    lines.extend([
        '', '## 计算口径', '',
        '- 基础养老金 = B × (1 + 平均缴费指数) ÷ 2 × 缴费年限 × 1%。',
        '- 个人或单位累计缴费 = 各月缴费基数 × 相应历史费率之和；累计缴费不含利息、不折现。',
        '- 本模型以各档目标指数乘以对应月份缴费基数基准，并受该月上下限约束，忽略逐月征收舍入差异。',
        '- 月度数据完整后，模型平均缴费指数按实际月缴费基数与参考基准比值的月平均数计算；实际核定指数仍需按官方口径核对。',
        '- 个人账户按各期计入比例和年度利息权重累计，不直接等同于个人缴费，也不把单位缴费全部计入个人账户。',
        '- 每月养老金合计 = 基础养老金 + 个人账户余额 ÷ 139；139作为本次60岁情景计发月数。',
        '- 假设无视同缴费年限、无其他过渡性待遇；若真实履历不符合该假设，须补充计算。',
        '- 金额显示至分，内部不逐月舍入；未来参数沿用最近公布值时须标记forecast并写明来源及依据。',
        ('- 本轮按用户要求忽略记账利率，个人账户累计利息为0。' if config.get('ignore_account_interest') else '- 个人账户按输入的历史利率与年度计息权重累计，退休当年仅计入退休前期间。'),
        '', '## 本轮补充数据', '',
        *(('- ' + note) for note in config.get('data_notes', ['尚无补充数据。'])),
        '', '年度原始表见 inputs/annual_contribution_limits.csv，档位换算见“年度缴费基数换算.csv”。',
        '', '## 数据核验状态', '',
        '2026-10-27尝试访问上海人社和上海市政府网站，均遇到域名解析失败；未取得官方正文。',
        '官方查询入口：https://rsj.sh.gov.cn/ 、https://www.shanghai.gov.cn/ 、https://www.mohrss.gov.cn/ 。',
        '这些网址为待查询入口，不作为本次已经核实的数值来源。', '',
    ])
    if absent_months:
        lines.append(f"- 历史缴费参数缺少或未核验：{len(absent_months)}个月，涉及{len(absent_years)}个年份（{absent_years[0]}—{absent_years[-1]}）。")
    other = [item for item in issues if item[:7] not in absent_months]
    lines.extend('- ' + item for item in other)
    if not issues:
        lines.append('- 必需字段与录入的核验状态检查通过；程序不代替对官方原文的人工核验。')
    lines.extend([
        '', '## 参数填写与复算', '',
        '在 inputs/config.json 中记录计发基数、参考期和来源；假设值须明确标注，不作为官方公布值。',
        '在 inputs/monthly_parameters.csv 中填写历月基数、费率及账户计入比例；',
        '在 inputs/interest_parameters.csv 中填写各年利率及官方计息权重。',
        '费率使用小数，例如8%填0.08；权重为年度利率的使用比例，',
        '例如仅在官方规则支持时，全年期初余额权重填1，7个月期初余额填7/12的小数值。',
        '尚未公布的未来值按最近公布参数沿用并标注forecast；已核验历史值标注verified。', '',
        '复现本轮已确认口径：`python3 prepare_estimate.py`，再运行 `python3 calculate.py`。',
        '校验：`python3 -m unittest -v test_calculate.py`。',
        'CSV空白金额为未能计算，不得填成0元。具体缺项见 validation.json。', '',
        '增加年限与提高档位的24组相邻比较另见“增加年限与提高档位对比.csv”；金额缺失时只输出已知的基础养老金比例变化。', '',
    ])
    (out / '上海养老金测算报告.md').write_text('\n'.join(lines), encoding='utf-8')
    validation = {
        'status': 'conditional_estimate' if computed_all else 'incomplete',
        'scenario_count': len(results),
        'scenarios_with_total_pension': sum(r['total_pension'] is not None for r in results),
        'scenarios_with_paid_totals': sum(r['total_paid'] is not None for r in results),
        'scenarios_with_forecast': sum(r['includes_forecast'] for r in results),
        'issues': issues,
        'note': 'status只检查录入信息，不能自动确认来源的真实性。',
    }
    (out / 'validation.json').write_text(json.dumps(validation, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return validation


def init_inputs(inputs):
    inputs.mkdir(parents=True, exist_ok=True)
    config = {
        'as_of': '2026-10-27',
        'retirement_month': '2027-07',
        'age_at_retirement': 60,
        'insurance_type': 'enterprise_employee',
        'retirement_eligibility_status': 'unverified',
        'payout_months': 139,
        'payout_months_status': 'unverified',
        'pension_base': {'monthly_amount': None, 'reference_period': None, 'status': 'unverified', 'source': '', 'note': ''},
        'note': '历史参数须有来源。未核实数据留空，不能把近年费率套用至全部历史年份。',
    }
    config_path = inputs / 'config.json'
    if not config_path.exists():
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    monthly_path = inputs / 'monthly_parameters.csv'
    if not monthly_path.exists():
        with monthly_path.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=MONTH_FIELDS)
            writer.writeheader()
            for month in months_between('1997-08', '2027-07'):
                writer.writerow({'month': month, 'status': 'unverified'})
    interest_path = inputs / 'interest_parameters.csv'
    if not interest_path.exists():
        with interest_path.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=INTEREST_FIELDS)
            writer.writeheader()
            for year in range(1997, 2028):
                writer.writerow({'year': year, 'status': 'unverified'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, default=Path(__file__).parent / 'inputs')
    parser.add_argument('--output', type=Path, default=Path(__file__).parent / 'output')
    parser.add_argument('--init-inputs', action='store_true', help='仅补建不存在的空白参数模板，不覆盖已有数据')
    args = parser.parse_args()
    if args.init_inputs:
        init_inputs(args.inputs)
    config = json.loads((args.inputs / 'config.json').read_text(encoding='utf-8'))
    monthly = load_csv(args.inputs / 'monthly_parameters.csv', 'month', MONTH_FIELDS)
    interest = load_csv(args.inputs / 'interest_parameters.csv', 'year', INTEREST_FIELDS)
    results, details, issues = calculate(config, monthly, interest)
    validation = write_outputs(config, results, details, issues, args.output)
    print(json.dumps({k: v for k, v in validation.items() if k != 'issues'}, ensure_ascii=False, indent=2))
    return 2 if validation['status'] == 'incomplete' else 0


if __name__ == '__main__':
    raise SystemExit(main())
