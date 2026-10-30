(function (root) {
  'use strict';

  const PANEL = { width: 480, height: 370, left: 61, top: 95, plotWidth: 400, plotHeight: 228 };
  const COMPARISON = { width: 1488, height: 742, left: 88, top: 190, plotWidth: 1362, plotHeight: 425 };
  const COMPARISON_BASES = [7546, 37731];
  const integer = new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 0 });
  const yuan = new Intl.NumberFormat('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const esc = value => String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
  const f = value => Number(value).toFixed(3);

  function ageLabel(ageMonth) {
    const years = Math.floor(ageMonth / 12), months = ageMonth % 12;
    return years + '岁' + (months ? months + '个月' : '');
  }

  function cashflow(scenario, scope, ageMonth) {
    const start = scenario.start_age * 12;
    if (ageMonth < start) return null;
    const cost = scenario.costs[scope];
    const paid = Math.min(ageMonth - start, scenario.years * 12) * cost.monthly;
    const received = Math.max(0, ageMonth - 720) * scenario.monthly_pension;
    return { paid, received, net: received - paid };
  }

  function selected(data, base, years) {
    return data.scenarios.filter(s => s.base === base && years.includes(s.years));
  }

  function sharedScale(data, base, options) {
    const scenarios = selected(data, base, options.years);
    if (!scenarios.length) return { min: -10000, max: 10000, step: 5000 };
    const min = Math.min(0, ...scenarios.map(s => -s.costs.combined.total));
    const max = Math.max(0, ...scenarios.map(s => cashflow(s, 'personal', options.endAge * 12).net));
    return niceScale(min, max);
  }

  function niceScale(min, max) {
    const range = Math.max(1, max - min);
    const raw = range / 4.5;
    const magnitude = Math.pow(10, Math.floor(Math.log10(raw)));
    const normalized = raw / magnitude;
    const factor = [1, 2, 2.5, 5, 10].find(v => v >= normalized) || 10;
    const step = factor * magnitude;
    return { min: Math.floor((min - range * 0.025) / step) * step, max: Math.ceil((max + range * 0.025) / step) * step, step };
  }

  function comparisonSelected(data, options) {
    return data.scenarios.filter(s => COMPARISON_BASES.includes(s.base) && options.years.includes(s.years));
  }

  function comparisonScale(data, options) {
    const scenarios = comparisonSelected(data, options);
    if (!scenarios.length) return { min: -10000, max: 10000, step: 5000 };
    return niceScale(
      Math.min(0, ...scenarios.map(s => -s.costs.combined.total)),
      Math.max(0, ...scenarios.map(s => cashflow(s, 'combined', options.endAge * 12).net))
    );
  }

  function comparisonSvg(data, options) {
    const { width, height, left, top, plotWidth, plotHeight } = COMPARISON;
    const scenarios = comparisonSelected(data, options);
    const scale = comparisonScale(data, options);
    const x = age => left + (age - data.min_age) / (options.endAge - data.min_age) * plotWidth;
    const y = amount => top + (scale.max - amount) / (scale.max - scale.min) * plotHeight;
    const right = left + plotWidth, bottom = top + plotHeight;
    let svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" data-comparison="combined" role="img" aria-labelledby="comparison-title comparison-desc" font-family="system-ui,-apple-system,'Microsoft YaHei','PingFang SC',sans-serif">`;
    svg += '<title id="comparison-title">7546元与37731元缴费基数：个人加单位成本同轴对比</title><desc id="comparison-desc">两种月缴费基数的个人加单位24%成本累计现金流，在同一组年龄和金额坐标轴中比较；颜色表示缴费年限，实线为7546元基数，虚线为37731元基数。</desc>';
    svg += `<rect x=".5" y=".5" width="${width - 1}" height="${height - 1}" rx="14" fill="#fff" stroke="#dfe6df"/>`;
    svg += '<text x="30" y="40" font-size="24" font-weight="700" fill="#193441">两档基数同轴对比 · 个人 + 单位成本24%</text>';
    svg += '<text x="30" y="69" font-size="14" fill="#526974">月缴费基数 ¥7,546 与 ¥37,731 · 六种缴费年限 · 共用年龄轴与金额轴</text>';
    data.years.forEach((year, i) => {
      const xx = 32 + i * 112;
      svg += `<g opacity="${options.years.includes(year) ? 1 : .25}"><line x1="${xx}" x2="${xx + 24}" y1="103" y2="103" stroke="${data.colors[year]}" stroke-width="3"/><text x="${xx + 32}" y="108" font-size="13" fill="#334e59">${year}年</text></g>`;
    });
    svg += '<line x1="842" x2="886" y1="103" y2="103" stroke="#3e5561" stroke-width="2.7"/><text x="896" y="108" font-size="13" fill="#334e59">¥7,546 实线</text>';
    svg += '<line x1="1110" x2="1154" y1="103" y2="103" stroke="#3e5561" stroke-width="2.7" stroke-dasharray="10 6"/><text x="1164" y="108" font-size="13" fill="#334e59">¥37,731 虚线</text>';
    for (const [i, base] of COMPARISON_BASES.entries()) {
      const s = scenarios.find(s => s.base === base);
      if (s) svg += `<text x="${32 + i * 610}" y="144" font-size="14" fill="#245d4c" font-weight="600">¥${integer.format(base)} 回正：${esc(s.costs.combined.break_even_label)}（领金第${s.costs.combined.break_even_months}个月）</text>`;
    }
    if (!scenarios.length) svg += '<text x="32" y="144" font-size="14" fill="#71828a">请选择至少一种缴费年限</text>';
    svg += `<defs><clipPath id="comparison-clip"><rect x="${left}" y="${top}" width="${plotWidth}" height="${plotHeight}"/></clipPath></defs>`;
    svg += `<rect x="${f(x(60))}" y="${top}" width="${f(right - x(60))}" height="${plotHeight}" fill="#f3f7fb"/>`;
    svg += `<text x="${left}" y="${top - 12}" font-size="12" fill="#71828a">累计净现金流（万元）</text>`;
    for (let tick = scale.min; tick <= scale.max + scale.step * .01; tick += scale.step) {
      const yy = y(tick), zero = Math.abs(tick) < scale.step * .001;
      svg += `<line x1="${left}" x2="${right}" y1="${f(yy)}" y2="${f(yy)}" stroke="${zero ? '#647986' : '#e7ede8'}" stroke-width="${zero ? 1.8 : 1}"/>`;
      const value = tick / 10000;
      const label = Number.isInteger(value) ? integer.format(value) : value.toFixed(1);
      svg += `<text x="${left - 12}" y="${f(yy + 4)}" text-anchor="end" font-size="12" fill="#627681">${label}</text>`;
    }
    const ticks = [data.min_age, 30, 40, 50, 60, 70, 80, 90, 100].filter(a => a <= options.endAge);
    if (!ticks.includes(options.endAge)) ticks.push(options.endAge);
    for (const age of ticks) {
      svg += `<line x1="${f(x(age))}" x2="${f(x(age))}" y1="${bottom}" y2="${bottom + 5}" stroke="#a8b6af"/><text x="${f(x(age))}" y="${bottom + 23}" text-anchor="middle" font-size="12" fill="#627681">${age}</text>`;
    }
    svg += `<text x="${right}" y="${bottom + 43}" text-anchor="end" font-size="12" fill="#71828a">年龄（岁）</text>`;
    svg += `<line data-role="retirement-line" x1="${f(x(60))}" x2="${f(x(60))}" y1="${top}" y2="${bottom}" stroke="#788c98" stroke-dasharray="5 5"/><text x="${f(x(60) + 8)}" y="${top + 18}" fill="#607686" font-size="12">60岁退休</text>`;
    for (const base of COMPARISON_BASES) {
      const s = scenarios.find(s => s.base === base);
      if (!s) continue;
      const age = s.costs.combined.break_even_age_month / 12;
      if (age <= options.endAge) svg += `<line data-role="recovery-line" data-base="${base}" x1="${f(x(age))}" x2="${f(x(age))}" y1="${top}" y2="${bottom}" stroke="#4b8c6c" stroke-opacity=".55" stroke-dasharray="2 5"/>`;
    }
    svg += '<g clip-path="url(#comparison-clip)">';
    for (const s of scenarios) {
      const cost = s.costs.combined;
      const points = [[x(s.start_age), y(0)], [x(60), y(-cost.total)], [x(options.endAge), y(cashflow(s, 'combined', options.endAge * 12).net)]];
      const dash = s.base === 37731 ? ' stroke-dasharray="10 6"' : '';
      svg += `<polyline class="comparison-curve" data-base="${s.base}" data-year="${s.years}" data-scope="combined" points="${points.map(p => p.map(f).join(',')).join(' ')}" fill="none" stroke="${data.colors[s.years]}" stroke-width="2.6" stroke-linejoin="round" opacity=".94"${dash}><title>基数${integer.format(s.base)}元，缴费${s.years}年，个人加单位成本${yuan.format(cost.total)}元</title></polyline>`;
      const month = cost.break_even_age_month;
      if (month <= options.endAge * 12) svg += `<circle data-role="recovery-marker" cx="${f(x(month / 12))}" cy="${f(y(cashflow(s, 'combined', month).net))}" r="3" fill="${data.colors[s.years]}"/>`;
    }
    svg += '</g>';
    svg += '<text x="32" y="685" font-size="13" fill="#526974">同色表示相同缴费年限；实线与虚线区分缴费基数。24%成本均包含个人8%与单位16%，个人账户仍按8%计入。</text>';
    svg += '<text x="32" y="711" font-size="12" fill="#71828a">沿用计发基数演算值12,577元/月、60岁退休及139计发月数；不计利息、养老金调整及折现。结果为简化估算。</text></svg>';
    return svg;
  }

  function panelMarkup(data, base, scope, options) {
    const scenarios = selected(data, base, options.years);
    const scale = sharedScale(data, base, options);
    const { left, top, plotWidth, plotHeight } = PANEL;
    const x = age => left + (age - data.min_age) / (options.endAge - data.min_age) * plotWidth;
    const y = amount => top + (scale.max - amount) / (scale.max - scale.min) * plotHeight;
    const right = left + plotWidth, bottom = top + plotHeight;
    const clip = `clip-${base}-${scope}`;
    const costLabel = scope === 'personal' ? '个人成本 · 8%' : '个人 + 单位成本 · 24%';
    let svg = `<rect x=".5" y=".5" width="479" height="369" rx="14" fill="#fff" stroke="#dfe6df"/>`;
    svg += `<text x="22" y="29" fill="#1e3542" font-size="16" font-weight="700">月缴费基数 ¥${integer.format(base)}</text>`;
    svg += `<text x="22" y="51" fill="#526974" font-size="12">${costLabel}</text>`;
    if (scenarios.length) {
      const cost = scenarios[0].costs[scope];
      svg += `<text x="22" y="72" fill="#245d4c" font-size="12" font-weight="600">回正 ${esc(cost.break_even_label)} · 领金第${cost.break_even_months}个月</text>`;
    } else {
      svg += '<text x="22" y="72" fill="#7a8a91" font-size="12">请选择至少一种缴费年限</text>';
    }
    svg += `<defs><clipPath id="${clip}"><rect x="${left}" y="${top}" width="${plotWidth}" height="${plotHeight}"/></clipPath></defs>`;
    svg += `<rect x="${f(x(60))}" y="${top}" width="${f(right - x(60))}" height="${plotHeight}" fill="#f3f7fb"/>`;
    svg += `<text x="${left}" y="86" fill="#71828a" font-size="10">累计净现金流（万元）</text>`;
    for (let tick = scale.min; tick <= scale.max + scale.step * 0.01; tick += scale.step) {
      const yy = y(tick), zero = Math.abs(tick) < scale.step * 0.001;
      svg += `<line x1="${left}" x2="${right}" y1="${f(yy)}" y2="${f(yy)}" stroke="${zero ? '#647986' : '#e7ede8'}" stroke-width="${zero ? '1.6' : '1'}"/>`;
      const value = tick / 10000;
      const label = Number.isInteger(value) ? integer.format(value) : value.toFixed(1);
      svg += `<text x="${left - 9}" y="${f(yy + 3.5)}" text-anchor="end" fill="#627681" font-size="10">${label}</text>`;
    }
    let ticks = [data.min_age, 30, 40, 50, 60, 70, 80, 90, 100].filter(a => a <= options.endAge);
    if (!ticks.includes(options.endAge)) ticks.push(options.endAge);
    for (const age of ticks) {
      const xx = x(age);
      svg += `<line x1="${f(xx)}" x2="${f(xx)}" y1="${bottom}" y2="${bottom + 4}" stroke="#a8b6af"/>`;
      svg += `<text x="${f(xx)}" y="${bottom + 18}" text-anchor="middle" fill="#627681" font-size="10">${age}</text>`;
    }
    svg += `<text x="${right}" y="${bottom + 36}" text-anchor="end" fill="#71828a" font-size="10">年龄（岁）</text>`;
    svg += `<line data-role="retirement-line" x1="${f(x(60))}" x2="${f(x(60))}" y1="${top}" y2="${bottom}" stroke="#788c98" stroke-width="1" stroke-dasharray="4 4"/>`;
    svg += `<text x="${f(x(60) + 4)}" y="${top + 12}" fill="#607686" font-size="10">60岁退休</text>`;
    if (scenarios.length) {
      const recoveryAge = scenarios[0].costs[scope].break_even_age_month / 12;
      if (recoveryAge <= options.endAge) {
        svg += `<line data-role="recovery-line" x1="${f(x(recoveryAge))}" x2="${f(x(recoveryAge))}" y1="${top}" y2="${bottom}" stroke="#4b8c6c" stroke-opacity=".5" stroke-dasharray="2 4"/>`;
      }
    }
    svg += `<g clip-path="url(#${clip})">`;
    for (const s of scenarios) {
      const color = data.colors[s.years];
      const end = cashflow(s, scope, options.endAge * 12);
      const points = [[x(s.start_age), y(0)], [x(60), y(-s.costs[scope].total)], [x(options.endAge), y(end.net)]];
      svg += `<polyline class="cashflow-curve" data-year="${s.years}" data-base="${base}" data-scope="${scope}" points="${points.map(p => p.map(f).join(',')).join(' ')}" fill="none" stroke="${color}" stroke-width="2.3" stroke-linejoin="round" stroke-linecap="round" opacity=".92"><title>${s.years}年，${esc(costLabel)}，月养老金${yuan.format(s.monthly_pension)}元</title></polyline>`;
      const month = s.costs[scope].break_even_age_month;
      if (month <= options.endAge * 12) {
        svg += `<circle data-role="recovery-marker" cx="${f(x(month / 12))}" cy="${f(y(cashflow(s, scope, month).net))}" r="2.6" fill="${color}"/>`;
      }
    }
    svg += '</g>';
    return svg;
  }

  function panelSvg(data, base, scope, options) {
    return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${PANEL.width} ${PANEL.height}" data-base="${base}" data-scope="${scope}" role="img" aria-label="月缴费基数${base}元，${scope === 'personal' ? '个人' : '个人加单位'}成本累计现金流" style="font-family:system-ui,-apple-system,'Microsoft YaHei','PingFang SC',sans-serif">${panelMarkup(data, base, scope, options)}</svg>`;
  }

  function overviewSvg(data, options) {
    const width = 1560, height = 1070;
    let svg = `<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" role="img" aria-labelledby="figure-title figure-desc" font-family="system-ui,-apple-system,'Microsoft YaHei','PingFang SC',sans-serif">`;
    svg += '<title id="figure-title">社保累计现金流与回正年龄</title><desc id="figure-desc">三个固定月缴费基数，六种缴费年限；上排个人8%成本，下排个人加单位24%成本。缴费阶段现金流下降，60岁后领取养老金并逐渐回正。</desc>';
    svg += `<rect width="${width}" height="${height}" fill="#f5f6f2"/>`;
    svg += '<text x="36" y="47" font-size="28" font-weight="700" fill="#193441">社保累计现金流 · 从缴费到回正</text>';
    svg += '<text x="36" y="78" font-size="14" fill="#526974">固定月基数 7,546 / 12,577 / 37,731 元 · 60岁退休 · 计发月数139 · 计发基数演算值12,577元 · 不计利息与年度调整</text>';
    data.years.forEach((year, i) => {
      const xx = 38 + i * 128;
      const opacity = options.years.includes(year) ? 1 : .25;
      svg += `<g opacity="${opacity}"><line x1="${xx}" x2="${xx + 25}" y1="116" y2="116" stroke="${data.colors[year]}" stroke-width="3"/><text x="${xx + 33}" y="121" font-size="13" fill="#334e59">缴费${year}年</text></g>`;
    });
    svg += `<text x="${width - 36}" y="121" text-anchor="end" font-size="12" fill="#657983">横轴：年龄22—${options.endAge}岁 · 纵轴：累计净现金流</text>`;
    data.scopes.forEach((scope, row) => {
      data.bases.forEach((base, col) => {
        svg += `<g class="cashflow-panel" data-base="${base}" data-scope="${scope.id}" transform="translate(${36 + col * 504},${153 + row * 390})">${panelMarkup(data, base, scope.id, options)}</g>`;
      });
    });
    svg += '<text x="36" y="958" font-size="13" fill="#435f6c">上排仅计个人8%成本；下排计个人与单位合计24%成本。两种口径使用相同的月养老金。</text>';
    svg += '<text x="36" y="983" font-size="13" fill="#435f6c">同一基数下，各年限的累计成本与养老金同比增加，所以回正年龄一致；圆点为首次累计非负的月末。</text>';
    svg += '<text x="36" y="1008" font-size="12" fill="#687d86">养老金按固定月额持续计入；139仅作为计发除数。不同年限从各自起缴年龄起画线，同基数上下两图使用相同纵轴范围。</text>';
    svg += '<text x="36" y="1035" font-size="12" fill="#687d86">本图为用户确认的固定基数、固定费率、零利息演算，不代表官方核定待遇。准确金额与年度明细见配套CSV。</text></svg>';
    return svg;
  }

  function initialize(data) {
    const state = { endAge: data.default_end_age, years: [...data.years] };
    const legend = document.getElementById('legend');
    const charts = document.getElementById('charts');
    const comparison = document.getElementById('comparison-chart');
    const tooltip = document.getElementById('tooltip');
    legend.innerHTML = data.years.map(year => `<button type="button" data-year="${year}" aria-pressed="true"><span class="dot" style="background:${data.colors[year]}"></span>${year}年</button>`).join('');
    document.getElementById('assumptions').innerHTML = data.assumptions.map(text => `<li>${esc(text)}</li>`).join('');

    function showTooltip(event, svg) {
      const comparing = svg.dataset.comparison === 'combined';
      const geometry = comparing ? COMPARISON : PANEL;
      const bounds = svg.getBoundingClientRect();
      const localX = (event.clientX - bounds.left) / bounds.width * geometry.width;
      const localY = (event.clientY - bounds.top) / bounds.height * geometry.height;
      if (localX < geometry.left || localX > geometry.left + geometry.plotWidth || localY < geometry.top || localY > geometry.top + geometry.plotHeight) {
        tooltip.hidden = true;
        return;
      }
      const ageMonth = Math.round((data.min_age + (localX - geometry.left) / geometry.plotWidth * (state.endAge - data.min_age)) * 12);
      const base = Number(svg.dataset.base), scope = comparing ? 'combined' : svg.dataset.scope;
      const rows = comparing ? comparisonSelected(data, state) : selected(data, base, state.years);
      if (!rows.length) { tooltip.hidden = true; return; }
      tooltip.innerHTML = `<strong>${ageLabel(ageMonth)} · ${comparing ? '两档基数同轴对比' : '基数' + integer.format(base) + '元'}</strong><em>${scope === 'personal' ? '个人8%口径' : '个人加单位24%口径'} · 累计现金流</em>` + rows.map(s => {
        const value = cashflow(s, scope, ageMonth);
        const label = value === null ? '未起缴' : (value.net >= 0 ? '+' : '−') + yuan.format(Math.abs(value.net)) + '元';
        return `<div class="tiprow"><span><span class="dot" style="background:${data.colors[s.years]}"></span>${comparing ? integer.format(s.base) + ' · ' : ''}${s.years}年</span><span>${label}</span></div>`;
      }).join('');
      tooltip.hidden = false;
      const measured = tooltip.getBoundingClientRect();
      tooltip.style.left = Math.max(8, Math.min(root.innerWidth - measured.width - 8, event.clientX + 18)) + 'px';
      tooltip.style.top = Math.max(8, Math.min(root.innerHeight - measured.height - 8, event.clientY + 16)) + 'px';
    }

    function render() {
      tooltip.hidden = true;
      comparison.innerHTML = comparisonSvg(data, state);
      charts.innerHTML = data.scopes.map(scope => data.bases.map(base => `<div class="chart-card">${panelSvg(data, base, scope.id, state)}</div>`).join('')).join('');
      [...charts.querySelectorAll('svg'), ...comparison.querySelectorAll('svg')].forEach(svg => {
        svg.addEventListener('pointermove', event => showTooltip(event, svg));
        svg.addEventListener('pointerleave', () => { tooltip.hidden = true; });
      });
      legend.querySelectorAll('button').forEach(button => button.setAttribute('aria-pressed', String(state.years.includes(Number(button.dataset.year)))));
      document.getElementById('summary-body').innerHTML = data.scenarios.filter(s => state.years.includes(s.years)).map(s => `<tr><td>${integer.format(s.base)}</td><td>${s.years}年</td><td>${s.start_age}岁</td><td>${yuan.format(s.costs.personal.total)}</td><td>${yuan.format(s.costs.combined.total)}</td><td>${yuan.format(s.monthly_pension)}</td><td>${esc(s.costs.personal.break_even_label)}</td><td>${esc(s.costs.combined.break_even_label)}</td></tr>`).join('');
    }

    legend.addEventListener('click', event => {
      const button = event.target.closest('button[data-year]');
      if (!button) return;
      const year = Number(button.dataset.year);
      state.years = state.years.includes(year) ? state.years.filter(v => v !== year) : [...state.years, year].sort((a, b) => a - b);
      render();
    });
    document.getElementById('end-age').addEventListener('change', event => { state.endAge = Number(event.target.value); render(); });
    function download(filename, content, type) {
      const url = URL.createObjectURL(new Blob([content], { type }));
      const anchor = document.createElement('a');
      anchor.href = url; anchor.download = filename;
      document.body.appendChild(anchor); anchor.click(); anchor.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }
    document.getElementById('download-svg').addEventListener('click', () => download('社保累计现金流.svg', overviewSvg(data, state), 'image/svg+xml;charset=utf-8'));
    document.getElementById('download-comparison').addEventListener('click', () => download('两档基数合计成本对比.svg', comparisonSvg(data, state), 'image/svg+xml;charset=utf-8'));
    document.getElementById('download-summary').addEventListener('click', () => download('现金流方案汇总.csv', data.downloads.summary, 'text/csv;charset=utf-8'));
    document.getElementById('download-annual').addEventListener('click', () => download('现金流年度明细.csv', data.downloads.annual, 'text/csv;charset=utf-8'));
    render();
  }

  const api = { PANEL, COMPARISON, ageLabel, cashflow, selected, sharedScale, panelSvg, overviewSvg, comparisonSelected, comparisonScale, comparisonSvg };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.CashflowCharts = api;
  if (typeof document !== 'undefined') initialize(JSON.parse(document.getElementById('cashflow-data').textContent));
})(globalThis);
