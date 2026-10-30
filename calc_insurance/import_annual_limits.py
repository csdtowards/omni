#!/usr/bin/env python3
"""Convert the user's annual limits, and map only explicitly dated periods.

The 2x cap through 1997 is a user-confirmed inference, not a verified policy
citation. The 3x cap from 1998 is the modelling basis used to derive references.
Future values may be carried forward only if explicitly configured.
"""

import csv
import json
from decimal import Decimal
from pathlib import Path

from calculate import MONTH_FIELDS, dec, money, months_between


ROOT = Path(__file__).parent
ANNUAL_FIELDS = ('year', 'upper_monthly', 'lower_monthly', 'status', 'source', 'effective_from', 'effective_to')
OUTPUT_FIELDS = (
    '年份', '上限_元每月', '下限_元每月', '上限相对100%基准倍数', '推算100%基准_元每月',
    '60%档受上下限约束后_元每月', '100%档_元每月', '200%档受上限约束后_元每月',
    '300%档受上限约束后_元每月', '下限占100%基准比例', '生效开始月份', '生效结束月份', '数据性质',
)


def normalize(row):
    year = int(row['year'])
    upper = dec(row['upper_monthly'], f'{year}年上限')
    lower = dec(row['lower_monthly'], f'{year}年下限')
    if not 0 < lower <= upper:
        raise ValueError(f'{year}年上下限无效')
    # Explicitly confirmed by the user for the supplied early-year series.
    multiplier = Decimal(2 if year <= 1997 else 3)
    reference = upper / multiplier
    bands = [min(upper, max(lower, reference * index)) for index in (Decimal('.6'), Decimal(1), Decimal(2), Decimal(3))]
    return {
        'year': year, 'upper': upper, 'lower': lower,
        'multiplier': multiplier, 'reference': reference, 'bands': bands,
        'source': row['source'], 'effective_from': row['effective_from'], 'effective_to': row['effective_to'],
    }


def dated_mapping(rows, monthly_calendar):
    """Both endpoints must be present. Overlaps are rejected, not guessed."""
    mapping = {}
    missing_dates = []
    for row in rows:
        start, end = row['effective_from'], row['effective_to']
        if not start or not end:
            missing_dates.append(str(row['year']))
            continue
        for value in (start, end):
            if len(value) != 7 or value[4] != '-':
                raise ValueError('生效月份须填写YYYY-MM格式')
            from datetime import date
            date.fromisoformat(value + '-01')
        if start > end:
            raise ValueError(f"{row['year']}年生效起止月份顺序错误")
        for month in months_between(start, end):
            if month in mapping:
                raise ValueError(f'{month}存在重叠的政策生效区间')
            mapping[month] = row
    return {month: mapping[month] for month in monthly_calendar if month in mapping}, sorted(set(missing_dates))


def main():
    inputs, output = ROOT / 'inputs', ROOT / 'output'
    output.mkdir(exist_ok=True)
    with (inputs / 'annual_contribution_limits.csv').open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != list(ANNUAL_FIELDS):
            raise ValueError('年度上下限表列名与模板不符')
        annual = [normalize(row) for row in reader]
    with (output / '年度缴费基数换算.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(OUTPUT_FIELDS)
        for row in annual:
            writer.writerow([
                row['year'], money(row['upper']), money(row['lower']), row['multiplier'], money(row['reference']),
                *(money(value) for value in row['bands']),
                format(row['lower'] / row['reference'] * 100, '.4f') + '%',
                row['effective_from'], row['effective_to'], '用户提供上下限；按确认的倍数推算；未独立核验',
            ])
    monthly_path = inputs / 'monthly_parameters.csv'
    with monthly_path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if set(reader.fieldnames or ()) - set(MONTH_FIELDS):
            raise ValueError('月度参数表存在未知列，不自动覆盖')
        monthly = list(reader)
    mapped, missing_dates = dated_mapping(annual, [row['month'] for row in monthly])
    config = json.loads((inputs / 'config.json').read_text(encoding='utf-8'))
    forecast_months = []
    dated = [row for row in annual if row['effective_from'] and row['effective_to']]
    if config.get('future_contribution_base_policy') == 'carry_forward_latest' and dated:
        latest = max(dated, key=lambda row: row['effective_to'])
        for row in monthly:
            month = row['month']
            if month not in mapped and month > latest['effective_to'] and month > config['as_of'][:7]:
                mapped[month] = {**latest, 'forecast': True}
                forecast_months.append(month)
    for row in monthly:
        if row['month'] not in mapped:
            continue
        annual_row = mapped[row['month']]
        if row.get('reference_base') and row.get('base_status') not in {'derived_user_provided', 'forecast'}:
            raise ValueError(f"{row['month']}已有独立基数数据，不自动覆盖")
        row.update(
            reference_base=str(annual_row['reference']),
            lower_base=str(annual_row['lower']), upper_base=str(annual_row['upper']),
            base_status='forecast' if annual_row.get('forecast') else 'derived_user_provided',
            base_source=annual_row['source'],
        )
        if annual_row.get('forecast'):
            row['note'] = f"{row['month']}基数沿用{annual_row['year']}年数据；最新值静态预测"
        # Employee/employer/account rates and their source/status stay untouched.
    with monthly_path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=MONTH_FIELDS)
        writer.writeheader()
        writer.writerows(monthly)
    summary = {
        'annual_rows': len(annual),
        'years_missing_effective_dates': missing_dates,
        'months_mapped': len(mapped),
        'months_not_mapped': len(monthly) - len(mapped),
        'forecast_months': forecast_months,
        'effective_date_policy': '只映射填写了生效起止月份的区间；不假设自然年度',
        'early_year_reference_policy': '用户确认：1993—1997年按上限÷2推算100%基准；300%档受上限约束',
        'later_year_reference_policy': '1998年起按上限÷3推算100%基准；60%档与最低基数单独列示',
        'source_status': 'user_provided_not_independently_verified',
        'pension_base': (
            '经用户同意以12577元作演算假设，未核定为官方计发基数'
            if config.get('allow_assumed_pension_base') else '未从社保缴费上限推定养老金计发基数'
        ),
        '2027': '7月沿用最近年度（预测）' if forecast_months else '按已有区间映射，其余待补充',
    }
    (output / 'annual_import_status.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
