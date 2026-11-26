import assert from 'node:assert/strict';
import { num } from '../../docs/assets/ui.js';

const cases = [
  [20018.709, 0, '20.019'],
  [65066.454, 0, '65.066'],
  [1234.5, 0, '1.235'],
  [-1234.5, 0, '-1.235'],
  [12.25, 1, '12,3'],
  [12.24, 1, '12,2'],
  [null, 0, '—'],
  [Number.NaN, 0, '—'],
];

for (const [value, digits, expected] of cases) {
  assert.equal(num(value, digits), expected, `num(${value}, ${digits})`);
}

console.log(`valuation format: OK — ${cases.length} cases`);
