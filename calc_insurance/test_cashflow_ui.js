'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const charts = require('./cashflow_ui.js');
const data = JSON.parse(fs.readFileSync(path.join(__dirname, 'output', '现金流图表数据.json'), 'utf8'));

const options = { endAge: 85, years: data.years };
const overview = charts.overviewSvg(data, options);
assert.equal((overview.match(/class="cashflow-panel"/g) || []).length, 6);
assert.equal((overview.match(/class="cashflow-curve"/g) || []).length, 36);
assert.equal((overview.match(/data-role="retirement-line"/g) || []).length, 6);
assert.equal((overview.match(/data-role="recovery-marker"/g) || []).length, 36);
assert(!overview.includes('NaN'));
assert(!overview.includes('Infinity'));

for (const scenario of data.scenarios) {
  for (const scope of ['personal', 'combined']) {
    assert.equal(charts.cashflow(scenario, scope, scenario.start_age * 12 - 1), null);
    assert.equal(charts.cashflow(scenario, scope, scenario.start_age * 12).net, 0);
    assert(Math.abs(charts.cashflow(scenario, scope, 720).net + scenario.costs[scope].total) < 1e-7);
    const month = scenario.costs[scope].break_even_age_month;
    assert(charts.cashflow(scenario, scope, month - 1).net < 0);
    assert(charts.cashflow(scenario, scope, month).net >= 0);
    assert.equal(charts.ageLabel(month), scenario.costs[scope].break_even_label);
  }
}

for (const endAge of [80, 85, 90, 100]) {
  for (const years of [data.years, [38], []]) {
    const svg = charts.overviewSvg(data, { endAge, years });
    assert.equal((svg.match(/class="cashflow-curve"/g) || []).length, years.length * 6);
    assert(!svg.includes('NaN'));
    assert(!svg.includes('Infinity'));
    assert(svg.includes(`年龄22—${endAge}岁`));
  }
}
const empty = charts.overviewSvg(data, { endAge: 85, years: [] });
assert.equal((empty.match(/请选择至少一种缴费年限/g) || []).length, 6);
assert(charts.panelSvg(data, 7546, 'personal', options).includes('64岁'));

const comparison = charts.comparisonSvg(data, options);
assert.equal((comparison.match(/class="comparison-curve"/g) || []).length, 12);
assert.equal((comparison.match(/data-role="retirement-line"/g) || []).length, 1);
assert.equal((comparison.match(/data-role="recovery-line"/g) || []).length, 2);
assert(comparison.includes('71岁11个月'));
assert(comparison.includes('77岁9个月'));
const series = [...comparison.matchAll(/<polyline class="comparison-curve"[^>]+>/g)].map(m => m[0]);
assert(series.every(s => s.includes('data-scope="combined"')));
assert.equal(series.filter(s => s.includes('data-base="7546"')).length, 6);
assert.equal(series.filter(s => s.includes('data-base="37731"')).length, 6);
assert(!comparison.includes('data-base="12577"'));
for (const year of data.years) {
  const low = series.find(s => s.includes(`data-year="${year}"`) && s.includes('data-base="7546"'));
  const high = series.find(s => s.includes(`data-year="${year}"`) && s.includes('data-base="37731"'));
  assert(!low.includes('stroke-dasharray'));
  assert(high.includes('stroke-dasharray="10 6"'));
  assert(low.includes(`stroke="${data.colors[year]}"`));
  assert(high.includes(`stroke="${data.colors[year]}"`));
  const coordinates = line => line.match(/points="([^"]+)"/)[1].split(' ').map(p => p.split(',').map(Number));
  const lowPoints = coordinates(low), highPoints = coordinates(high);
  assert.deepEqual(lowPoints[0], highPoints[0]);
  assert.equal(lowPoints[1][0], highPoints[1][0]);
  assert(highPoints[1][1] > lowPoints[1][1]); // Higher total cost on the same y-axis.
}
for (const endAge of [80, 85, 90, 100]) {
  for (const years of [data.years, [38], []]) {
    const figure = charts.comparisonSvg(data, { endAge, years });
    assert.equal((figure.match(/class="comparison-curve"/g) || []).length, years.length * 2);
    assert(!figure.includes('NaN'));
    assert(!figure.includes('Infinity'));
  }
}
console.log('Chart checks passed: original 6 panels/36 curves; new 12-curve combined-cost comparison with one shared axis, distinct base styles, recovery ages, horizon changes and year filtering.');
