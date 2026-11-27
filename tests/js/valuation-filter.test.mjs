import test from 'node:test';
import assert from 'node:assert/strict';
import { activeValuationFilterCount, filterValuationRows } from '../../docs/assets/valuation-filter.mjs';

const rows = [
  {ticker: 'CACB2622', underlying: 'ACB', iv: 27.4, ivGroupMedian: 42, ivResidualPct: -34.7, ivMinusHv: 9.3, delta: 0.162, moneyness: 'OTM', strike: 21000, underlyingPrice: 19550, cwPrice: 240, daysToMaturity: 74, premiumPct: 9.9, underlyingSource: 'close'},
  {ticker: 'CACB2603', underlying: 'ACB', iv: 30.6, ivGroupMedian: 42, ivResidualPct: -27.2, ivMinusHv: 12.4, delta: 0.019, moneyness: 'OTM', strike: 22418, underlyingPrice: 19550, cwPrice: 10, daysToMaturity: 20, premiumPct: 14.8, underlyingSource: 'close'},
  {ticker: 'CVHM2601', underlying: 'VHM', iv: 35, ivGroupMedian: 33, ivResidualPct: 6, ivMinusHv: -2, delta: 0.55, moneyness: 'ATM', strike: 80000, underlyingPrice: 80000, cwPrice: 1500, daysToMaturity: 120, premiumPct: 5},
];

test('valuation filters combine the underlying, moneyness, and numeric criteria', () => {
  const filtered = filterValuationRows(rows, '', {
    underlying: 'ACB', moneyness: 'OTM', iv: {min: '25', max: '29'},
    delta: {min: '0.1'}, daysToMaturity: {min: '30'},
  });
  assert.deepEqual(filtered.map(row => row.ticker), ['CACB2622']);
});

test('valuation search checks warrant data and filters are inclusive at their bounds', () => {
  assert.deepEqual(filterValuationRows(rows, 'acb', {premiumPct: {min: '9.9', max: '9.9'}}).map(row => row.ticker), ['CACB2622']);
  assert.deepEqual(filterValuationRows(rows, 'cvhm').map(row => row.ticker), ['CVHM2601']);
  assert.deepEqual(filterValuationRows(rows, '', {daysToMaturity: {max: '20'}}).map(row => row.ticker), ['CACB2603']);
});

test('active filter count counts each selected category and numeric bound', () => {
  assert.equal(activeValuationFilterCount({underlying: 'ACB', moneyness: 'OTM', iv: {min: '20', max: '40'}, premiumPct: {max: '10'}}), 5);
  assert.equal(activeValuationFilterCount({}), 0);
});
