import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const html = readFileSync(new URL('../../docs/index.html', import.meta.url), 'utf8');
const css = readFileSync(new URL('../../docs/assets/ui.css', import.meta.url), 'utf8');

test('unified valuation toolbar derives the underlying choices and result count from filtered data', () => {
  assert.match(html, /valuationRowsCache\.map\(row => row\.underlying\)/);
  assert.match(html, /num\(filtered\.length\).*mã phù hợp.*matching warrants/s);
  assert.match(html, /data-val-filter="underlying"/);
  assert.match(html, /data-val-moneyness/);
  assert.match(html, /data-val-query-clear/);
  assert.match(html, /data-val-advanced-toggle/);
  assert.match(html, /data-val-filter-reset/);
});

test('all numeric min/max fields share one compact horizontal row inside the advanced grid', () => {
  assert.match(html, /class="valuation-range-inputs"><input[^>]+data-val-bound="min"[^>]*>.*?<input[^>]+data-val-bound="max"/);
  assert.match(css, /\.valuation-range-inputs\s*\{\s*display:\s*grid;\s*grid-template-columns:\s*minmax\(0,1fr\) auto minmax\(0,1fr\)/);
  assert.match(css, /\.valuation-filter-grid\s*\{\s*display:\s*grid;\s*grid-template-columns:\s*repeat\(5,minmax\(0,1fr\)\)/);
});

test('active filters render individual removable chips and keep bilingual labels', () => {
  assert.match(html, /valuation-active-chips/);
  assert.match(html, /data-val-chip-clear="\$\{key\}"/);
  assert.match(html, /Xóa tất cả.*Clear all/);
  assert.match(html, /Cổ phiếu cơ sở.*Underlying/);
  assert.match(html, /Trạng thái tiền.*Moneyness/);
});
