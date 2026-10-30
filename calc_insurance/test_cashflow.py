"""Cash-flow timing and accounting regression checks for the agreed model."""

import csv
import io
import unittest
from decimal import Decimal as D

from cashflow import BASES, YEARS, Scenario, age_label, annual_csv, summary_csv


class CashflowTests(unittest.TestCase):
    def test_fixed_base_amounts_and_pension_components(self):
        s = Scenario(12577, 15)
        self.assertEqual(s.account_balance, D('181108.80'))
        self.assertEqual(s.total_cost('combined'), D('543326.40'))
        self.assertEqual(s.basic_pension, D('1886.55'))
        self.assertEqual(s.personal_pension, D('181108.80') / 139)
        self.assertEqual(s.pension, D('1886.55') + D('181108.80') / 139)
        # The requested 7546 is exact, not 60% * 12577 = 7546.2.
        exact = Scenario(7546, 15)
        self.assertEqual(exact.monthly_cost('personal'), D('603.68'))
        self.assertEqual(exact.account_balance, D('108662.40'))
        self.assertEqual(exact.basic_pension, D('1509.225'))

    def test_start_retirement_and_first_pension_boundaries(self):
        for years, start_age in zip(YEARS, (45, 40, 35, 30, 25, 22)):
            s = Scenario(12577, years)
            self.assertEqual(s.start_month, start_age * 12)
            for scope in ('personal', 'combined'):
                self.assertIsNone(s.snapshot(scope, s.start_month - 1))
                self.assertEqual(s.snapshot(scope, s.start_month)['net'], 0)
                self.assertEqual(s.snapshot(scope, s.start_month + 1)['net'], -s.monthly_cost(scope))
                at_retirement = s.snapshot(scope, 720)
                self.assertEqual(at_retirement['received'], 0)
                self.assertEqual(at_retirement['paid'], s.total_cost(scope))
                first_pension = s.snapshot(scope, 721)
                self.assertEqual(first_pension['paid'], at_retirement['paid'])
                self.assertEqual(first_pension['received'], s.pension)
                self.assertEqual(s.snapshot(scope, 732)['received'], s.pension * 12)

    def test_discrete_break_even_oracle_for_all_36_curves(self):
        expected = {7546: (48, 143), 12577: (57, 171), 37731: (71, 213)}
        for base in BASES:
            for years in YEARS:
                s = Scenario(base, years)
                for scope, expected_month in zip(('personal', 'combined'), expected[base]):
                    month = s.break_even_months(scope)
                    self.assertEqual(month, expected_month)
                    self.assertLess(s.snapshot(scope, 720 + month - 1)['net'], 0)
                    self.assertGreaterEqual(s.snapshot(scope, 720 + month)['net'], 0)

    def test_two_cost_scopes_share_pension_but_have_threefold_cost(self):
        for base in BASES:
            s = Scenario(base, 38)
            own = s.snapshot('personal', 1200)
            combined = s.snapshot('combined', 1200)
            self.assertEqual(combined['paid'], own['paid'] * 3)
            self.assertEqual(combined['received'], own['received'])
            self.assertEqual(own['received'], s.pension * 480)
            # 139 is a divisor, not a stopping point for receiving pension.
            self.assertGreater(s.snapshot('personal', 860)['received'], s.snapshot('personal', 859)['received'])

    def test_cost_and_pension_scale_with_years(self):
        for base in BASES:
            short, long = Scenario(base, 15), Scenario(base, 30)
            # Division by 139 repeats; Decimal's final precision digit can differ.
            self.assertAlmostEqual(long.pension, short.pension * 2, places=20)
            self.assertEqual(long.total_cost('combined'), short.total_cost('combined') * 2)

    def test_annual_and_summary_exports_cover_all_scenarios(self):
        scenarios = [Scenario(base, years) for base in BASES for years in YEARS]
        summary = list(csv.DictReader(io.StringIO(summary_csv(scenarios).lstrip('\ufeff'))))
        annual = list(csv.DictReader(io.StringIO(annual_csv(scenarios).lstrip('\ufeff'))))
        self.assertEqual(len(summary), 18)
        self.assertEqual(len(annual), 2454)
        self.assertEqual(len({(r['方案'], r['成本口径']) for r in annual}), 36)
        for row in annual:
            age = int(row['年龄_岁'])
            flow = D(row['本年度净现金流_元'])
            if row['时点'] == '起缴时点':
                self.assertEqual(flow, 0)
            elif age <= 60:
                self.assertLess(flow, 0)
                self.assertEqual(D(row['累计养老金收入_元']), 0)
            else:
                self.assertGreater(flow, 0)
                self.assertEqual(D(row['本年度缴费现金流_元']), 0)
        self.assertEqual(age_label(720 + 213), '77岁9个月')


if __name__ == '__main__':
    unittest.main()
