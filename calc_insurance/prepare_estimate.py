#!/usr/bin/env python3
"""Apply the user's confirmed July-June, zero-interest estimate assumptions.

This intentionally fills the scenario inputs. The 8%/16%/8% rates and 12577
pension base are modelling assumptions approved by the user, not historical
Shanghai policy observations.
"""

import csv
import json
from pathlib import Path

from calculate import INTEREST_FIELDS, MONTH_FIELDS
from import_annual_limits import ANNUAL_FIELDS, main as import_limits


ROOT = Path(__file__).parent


def main():
    inputs = ROOT / 'inputs'
    config_path = inputs / 'config.json'
    config = json.loads(config_path.read_text(encoding='utf-8'))
    config.update({
        'allow_assumed_pension_base': True,
        'future_contribution_base_policy': 'carry_forward_latest',
        'ignore_account_interest': True,
        'pension_base': {
            'monthly_amount': 12577,
            'reference_period': '估算参数：用户表中2026年缴费上限÷3',
            'status': 'assumption',
            'source': '用户明确同意本轮以12577元/月作为养老金计发基数演算',
            'note': '该值不是已核实的官方养老金计发基数，亦不是2027年公布值。',
        },
        'uniform_rate_assumptions': {
            'employee': '0.08', 'employer': '0.16', 'account_credit': '0.08',
            'source': '用户明确同意采用统一比例简化估算，不代表各年的真实费率或账户计入规则',
        },
        'data_notes': [
            '基数来源为用户提供的1993—2026年上下限表，未经独立官方核验。',
            '按用户最新指示，每年数值统一适用于当年7月至次年6月。',
            '连续缴费至2027年7月（含当月）：15、20、25、30年分别自2012、2007、2002、1997年8月起缴。',
            '2027年7月缺少新基数，按已选静态预测口径沿用2026年参数；这一月标记forecast。',
            '1993—1997年按用户确认的上限÷2推算100%基准；其后按上限÷3。1997年300%目标档封顶1778元。',
            '60%目标档按基准×60%并受上下限约束，不直接采用最低缴费基数；例如2020年为5603.40元。',
            '按用户确认，所有缴费年份统一采用个人8%、单位16%、个人账户计入8%；未还原历史费率及2006年前账户计入差异。',
            '按用户要求忽略记账利率，个人账户无利息，因此本轮个人账户余额等于个人累计缴费。',
            '按用户确认，养老金计发基数暂取12577元/月作演算参数，不代表上海官方核定基数或2027年公布值。',
            '60岁个人账户计发月数取139；养老金合计为本次简化起始月估算，不包括过渡性待遇及退休后年度调整。',
            '满60岁退休以符合弹性提前退休等条件为前提，本模型不确认个人办理资格。',
        ],
    })
    config['annual_limits_policy'].update({
        'calendar_mapping': 'july_through_next_june_user_instruction',
        'missing_effective_dates': 'resolved_by_user_cycle_assumption',
    })
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    annual_path = inputs / 'annual_contribution_limits.csv'
    with annual_path.open(encoding='utf-8-sig', newline='') as f:
        annual = list(csv.DictReader(f))
    for row in annual:
        year = int(row['year'])
        row['effective_from'] = f'{year}-07'
        row['effective_to'] = f'{year + 1}-06'
    with annual_path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=ANNUAL_FIELDS)
        writer.writeheader()
        writer.writerows(annual)

    import_limits()

    monthly_path = inputs / 'monthly_parameters.csv'
    with monthly_path.open(encoding='utf-8-sig', newline='') as f:
        monthly = list(csv.DictReader(f))
    for row in monthly:
        forecast_note = f"{row['month']}基数沿用2026年数据；最新值静态预测；" if row['base_status'] == 'forecast' else ''
        row.update(
            employee_rate='0.08', employer_rate='0.16', account_credit_rate='0.08',
            status='assumption',
            source='用户确认的统一8%/16%/8%比例简化估算；不是历史实际费率',
            note=forecast_note + '用户确认统一费率估算，未计入历史费率变化',
        )
    with monthly_path.open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=MONTH_FIELDS)
        writer.writeheader()
        writer.writerows(monthly)

    with (inputs / 'interest_parameters.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=INTEREST_FIELDS)
        writer.writeheader()
        for year in range(1997, 2028):
            writer.writerow({
                'year': year, 'annual_rate': '0', 'opening_balance_weight': '0',
                **{f'month_{m:02d}_weight': '0' for m in range(1, 13)},
                'status': 'user_provided', 'source': '用户明确要求忽略记账利率',
                'note': '零利率情景；权重填0仅简化计算，不表示官方计息规则',
            })


if __name__ == '__main__':
    main()
