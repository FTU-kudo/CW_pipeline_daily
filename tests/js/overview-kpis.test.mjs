import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {metricNumber, metricPercent, safeDivide, safeRatioPercent} from '../../docs/assets/kpi-metrics.mjs';

const html = readFileSync(new URL('../../docs/index.html', import.meta.url), 'utf8');
const translations = readFileSync(new URL('../../docs/assets/ui.js', import.meta.url), 'utf8');
const css = readFileSync(new URL('../../docs/assets/ui.css', import.meta.url), 'utf8');

test('safe KPI arithmetic handles zero, missing, and non-finite inputs', () => {
  assert.equal(safeDivide(18_000, 0), null);
  assert.equal(safeDivide(null, 4), null);
  assert.equal(safeDivide(18_000, 3), 6_000);
  assert.equal(safeRatioPercent(0, 0), '0.0');
  assert.equal(safeRatioPercent(1, 4), '25.0');
  assert.equal(safeRatioPercent(null, 4), '—');
  assert.equal(safeRatioPercent(Infinity, 2), '—');
  assert.equal(safeRatioPercent(Number.MAX_VALUE, Number.MIN_VALUE), '—');
  assert.equal(safeDivide(Number.MAX_VALUE, Number.MIN_VALUE), null);
});

test('large numbers use Vietnamese dots and English commas without rounding away digits', () => {
  assert.equal(metricNumber(1234.56, 1), '1,234.6');
  assert.equal(metricNumber(1_000_000_000, 0, 'vi-VN'), '1.000.000.000');
  assert.equal(metricNumber(1_000_000_000, 0, 'en-US'), '1,000,000,000');
  assert.equal(metricNumber(1234.56, 1, 'vi-VN'), '1.234,6');
  assert.equal(metricPercent(52.63), '52.6%');
  assert.equal(metricPercent(null), '—');
  assert.doesNotMatch(metricNumber(3.25, 2), /\d,\d/);
});

test('overview always builds the full eight-card, current-session KPI deck', () => {
  const block = html.split('const cards = [', 2)[1].split('\n  ];', 1)[0];
  const labels = [...block.matchAll(/k: '([^']+)'/g)].map(match => match[1]);
  assert.deepEqual(labels, [
    'Mã CW niêm yết', 'Giá trị giao dịch', 'Tăng / giảm / giữ nguyên', 'Cổ phiếu cơ sở',
    'Phân bố trạng thái tiền', 'IV trung vị', 'IV − HV', 'Spread trung vị',
  ]);
  for (const metric of ['activePct', 'inactivePct', 'avgValuePerActiveCW', 'avgCWPerUnderlying',
    'upPct', 'downPct', 'unchangedPct', 'itmPct', 'atmPct', 'otmPct', 'validSpreadCount',
    'abovePct', 'belowPct', 'medianSpreadTicks', 'medianSpreadAbsVND']) {
    assert.ok(block.includes(metric) || html.includes(`const ${metric}`), `missing dynamic ${metric}`);
  }
  assert.match(html, /class="ov-tier ov-tier-primary"/);
  assert.match(html, /class="ov-tier ov-tier-secondary"/);
  assert.match(html, /const kpiNum = \(value, digits = 0\) => metricNumber\(value, digits, getLang\(\) === 'en' \? 'en-US' : 'vi-VN'\)/);
  assert.match(html, /const kpiVnd = value =>[\s\S]*?kpiNum\(amount\)/);
  assert.match(html, /const kpiCompactVnd = value =>[\s\S]*?toFixed\(2\)[\s\S]*?bi\('tỷ', 'bn'\)[\s\S]*?toFixed\(2\)/);
  assert.match(block, /v: kpiCompactVnd\(totalValue\)/);
  assert.match(html, /numericCell\(r,'TotalVal'\)/);
  assert.match(html, /compactSplit: true/);
  assert.match(html, /splitLabelsOnly: true/);
  assert.match(html, /\{percentOnly: true\}/);
  assert.match(css, /\.ov-tier-primary\s*\{\s*grid-template-columns:\s*repeat\(3,/);
  assert.match(css, /\.ov-tier-secondary\s*\{\s*grid-template-columns:\s*repeat\(5,/);
  assert.match(css, /@media \(max-width: 1023px\)\s*\{[\s\S]*?\.ov-tier-secondary\s*\{\s*grid-template-columns:\s*repeat\(2,/);
});

test('every new KPI footer label has a VI to EN dictionary entry', () => {
  for (const key of ['Khớp lệnh', 'Không GD', 'Bình quân / mã khớp lệnh', 'Mật độ phân bổ',
    'Giữ nguyên', 'Tăng / giảm / giữ nguyên',
    'CW / cổ phiếu cơ sở', 'Đã định giá', 'Phiên hiện tại', 'Biên độ IQR (Q1–Q3)',
    'IV > HV', 'IV < HV', 'Chênh lệch bid-ask', 'bước giá', 'điểm']) {
    assert.ok(translations.includes(`'${key}':`), `missing EN translation for ${key}`);
  }
});
