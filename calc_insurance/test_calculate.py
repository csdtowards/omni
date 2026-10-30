"""Synthetic arithmetic checks. Fixture values are not Shanghai policy data."""

import copy
import unittest
from decimal import Decimal

from calculate import account_interest, calculate, months_between, start_month
from import_annual_limits import dated_mapping, normalize


def fixtures():
    config = {
        'retirement_month': '2027-07', 'age_at_retirement': 60,
        'insurance_type': 'enterprise_employee',
        'payout_months': 139, 'payout_months_status': 'verified',
        'retirement_eligibility_status': 'verified',
        'pension_base': {'monthly_amount': '10000', 'reference_period': 'synthetic', 'status': 'verified', 'source': 'synthetic-test-fixture'},
    }
    monthly = {
        month: {'reference_base': '1000', 'employee_rate': '0.08', 'employer_rate': '0.16',
                'account_credit_rate': '0.08', 'status': 'verified', 'source': 'synthetic-test-fixture'}
        for month in months_between('1997-08', '2027-07')
    }
    interest = {}
    for year in range(1997, 2028):
        last = 7 if year == 2027 else 12
        interest[str(year)] = {
            'annual_rate': '0', 'opening_balance_weight': str(Decimal(last) / 12),
            **{f'month_{m:02d}_weight': str(Decimal(max(0, last - m + 1)) / 12) for m in range(1, 13)},
            'status': 'verified', 'source': 'synthetic-test-fixture',
        }
    return config, monthly, interest


class CalculationTests(unittest.TestCase):
    def test_assumed_pension_base_requires_explicit_opt_in(self):
        config, monthly, interest = fixtures()
        config['pension_base'].update(status='assumption', note='explicit synthetic test assumption')
        with self.assertRaises(ValueError):
            calculate(config, monthly, interest)
        config['allow_assumed_pension_base'] = True
        results, _, issues = calculate(config, monthly, interest)
        self.assertEqual(issues, [])
        self.assertEqual(sum(r['total_pension'] is not None for r in results), 16)

    def test_early_year_cap_and_sixty_percent_not_equal_minimum(self):
        def annual(year, upper, lower, start='', end=''):
            return normalize({'year': str(year), 'upper_monthly': str(upper), 'lower_monthly': str(lower),
                              'source': 'synthetic-test-fixture', 'effective_from': start, 'effective_to': end})
        early = annual(1997, 1778, 533)
        self.assertEqual(early['reference'], Decimal(889))
        self.assertEqual(early['bands'], [Decimal('533.4'), Decimal(889), Decimal(1778), Decimal(1778)])
        modern = annual(2020, 28017, 4927)
        self.assertEqual(modern['reference'], Decimal(9339))
        self.assertEqual(modern['bands'][0], Decimal('5603.4'))
        self.assertNotEqual(modern['bands'][0], modern['lower'])
        mapped, missing = dated_mapping([modern], ['2020-01', '2020-07', '2027-07'])
        self.assertEqual(mapped, {})
        self.assertEqual(missing, ['2020'])
        modern = annual(2020, 28017, 4927, '2020-07', '2021-06')
        mapped, missing = dated_mapping([modern], ['2020-06', '2020-07', '2021-06', '2021-07', '2027-07'])
        self.assertEqual(set(mapped), {'2020-07', '2021-06'})
        self.assertEqual(missing, [])
        overlap = annual(2021, 31014, 5975, '2021-06', '2022-06')
        with self.assertRaises(ValueError):
            dated_mapping([modern, overlap], ['2021-06'])

    def test_monthly_cap_applies_to_cost_account_and_average_index(self):
        config, monthly, interest = fixtures()
        monthly['1997-08'].update(lower_base='600', upper_base='2000')
        results, _, issues = calculate(config, monthly, interest)
        self.assertEqual(issues, [])
        result = next(r for r in results if r['years'] == 30 and r['index'] == 3)
        self.assertEqual(result['employee_paid'], Decimal('86320'))
        self.assertEqual(result['employer_paid'], Decimal('172640'))
        self.assertEqual(result['account_balance'], Decimal('86320'))
        self.assertAlmostEqual(result['basic_pension'], Decimal('5995.833333333333333333333333'), places=20)

    def test_exact_contribution_windows(self):
        expected = {15: '2012-08', 20: '2007-08', 25: '2002-08', 30: '1997-08'}
        for years, start in expected.items():
            self.assertEqual(start_month('2027-07', years), start)
            self.assertEqual(len(list(months_between(start, '2027-07'))), years * 12)
        self.assertEqual(start_month('2027-12', 15), '2013-01')

    def test_cash_cost_account_and_pension_are_distinct(self):
        results, _, issues = calculate(*fixtures())
        self.assertEqual(issues, [])
        self.assertEqual(len(results), 16)
        result = next(r for r in results if r['years'] == 15 and r['index'] == 1)
        # 180 months; employees pay 80 per month, employers 160. Only 80 enters account.
        self.assertEqual(result['employee_paid'], Decimal('14400'))
        self.assertEqual(result['employer_paid'], Decimal('28800'))
        self.assertEqual(result['total_paid'], Decimal('43200'))
        self.assertEqual(result['account_balance'], Decimal('14400'))
        self.assertEqual(result['basic_pension'], Decimal('1500'))
        self.assertAlmostEqual(result['total_pension'], Decimal('1603.597122302158273381294964'), places=20)

    def test_historical_credit_share_and_rate_change(self):
        config, monthly, interest = fixtures()
        # An artificial one-month rule change: extra employer funds enter account.
        monthly['1997-08'].update(employee_rate='0.05', employer_rate='0.2', account_credit_rate='0.11')
        results, _, issues = calculate(config, monthly, interest)
        self.assertEqual(issues, [])
        longest = next(r for r in results if r['years'] == 30 and r['index'] == 1)
        self.assertEqual(longest['employee_paid'], Decimal('28770'))
        self.assertEqual(longest['employer_paid'], Decimal('57640'))
        self.assertEqual(longest['account_balance'], Decimal('28830'))
        shortest = next(r for r in results if r['years'] == 15 and r['index'] == 1)
        self.assertEqual(shortest['employee_paid'], Decimal('14400'))

    def test_retirement_year_interest_excludes_future_months(self):
        row = {
            'annual_rate': '0.12', 'opening_balance_weight': str(Decimal(7) / 12),
            'month_01_weight': str(Decimal(7) / 12), 'month_07_weight': str(Decimal(1) / 12),
            'status': 'verified', 'source': 'synthetic-test-fixture',
        }
        # Opening 1200 earns 84 over 7 months. Jan/Jul additions earn 7 and 1.
        value = account_interest(row, 2027, 7, Decimal('1200'), {1: Decimal('100'), 7: Decimal('100')}, set())
        self.assertAlmostEqual(value, Decimal('92'), places=20)
        bad = copy.deepcopy(row)
        bad['opening_balance_weight'] = '1'
        with self.assertRaises(ValueError):
            account_interest(bad, 2027, 7, Decimal('1200'), {1: Decimal('100')}, set())

    def test_missing_is_never_zero_and_does_not_hide_known_subtotals(self):
        config, monthly, interest = fixtures()
        monthly['1997-08']['reference_base'] = ''
        interest['2027']['annual_rate'] = ''
        results, _, issues = calculate(config, monthly, interest)
        self.assertTrue(issues)
        longest = next(r for r in results if r['years'] == 30 and r['index'] == 1)
        shortest = next(r for r in results if r['years'] == 15 and r['index'] == 1)
        self.assertIsNone(longest['employee_paid'])
        self.assertIsNone(longest['account_balance'])
        self.assertEqual(longest['basic_pension'], Decimal('3000'))
        self.assertEqual(shortest['employee_paid'], Decimal('14400'))
        self.assertIsNone(shortest['personal_pension'])
        self.assertIsNone(shortest['total_pension'])

    def test_unverified_inputs_are_not_treated_as_policy_data(self):
        config, monthly, interest = fixtures()
        config['pension_base']['status'] = 'unverified'
        monthly['2012-08']['status'] = 'unverified'
        results, _, issues = calculate(config, monthly, interest)
        self.assertTrue(issues)
        for r in results:
            self.assertIsNone(r['total_paid'])
            self.assertIsNone(r['total_pension'])

    def test_yearly_interest_carries_forward_once(self):
        config, monthly, interest = fixtures()
        # Only the last complete year earns interest, using explicit monthly weights.
        interest['2026']['annual_rate'] = '0.12'
        results, details, issues = calculate(config, monthly, interest)
        self.assertEqual(issues, [])
        result = next(r for r in results if r['years'] == 15 and r['index'] == 1)
        # Opening 2026: Aug2012-Dec2025 = 161 months * 80 = 12880.
        # Interest: 12880*.12 + 80*.12*(12+...+1)/12 = 1545.6 + 62.4.
        self.assertEqual(result['account_balance'], Decimal('16008'))
        account_rows = [r for r in details if r['years'] == 15 and r['index'] == 1]
        self.assertEqual(sum((r['interest'] for r in account_rows), Decimal(0)), Decimal('1608'))
        self.assertEqual(account_rows[-1]['closing'], result['account_balance'])


if __name__ == '__main__':
    unittest.main()
