import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {sortBoardRows} from '../../docs/assets/board-sort.mjs';

test('all eleven requested board columns expose sortable headers', () => {
  const html = readFileSync(new URL('../../docs/index.html', import.meta.url), 'utf8');
  const headers = [...html.matchAll(/<button[^>]*data-board-sort="([^"]+)"/g)].map(match => match[1]);
  assert.deepEqual(headers, ['ticker', 'reference', 'last', 'change', 'high', 'low', 'volume', 'value', 'share', 'spread', 'room']);
});

test('sorts numeric columns high-to-low and low-to-high', () => {
  const rows = [{v: 12}, {v: 2}, {v: 100}];
  assert.deepEqual(sortBoardRows(rows, 'v', 'desc').map(r => r.v), [100, 12, 2]);
  assert.deepEqual(sortBoardRows(rows, 'v', 'asc').map(r => r.v), [2, 12, 100]);
});

test('sorts CW codes lexically with natural number order', () => {
  const rows = [{code: 'CACB9'}, {code: 'CACB12'}, {code: 'ACB20'}];
  assert.deepEqual(sortBoardRows(rows, 'code', 'desc').map(r => r.code), ['CACB12', 'CACB9', 'ACB20']);
  assert.deepEqual(sortBoardRows(rows, 'code', 'asc').map(r => r.code), ['ACB20', 'CACB9', 'CACB12']);
});

test('keeps missing values last in both directions and preserves ties', () => {
  const rows = [{v: 4, id: 'a'}, {v: null, id: 'missing'}, {v: 4, id: 'b'}, {v: 1, id: 'c'}];
  assert.deepEqual(sortBoardRows(rows, 'v', 'desc').map(r => r.id), ['a', 'b', 'c', 'missing']);
  assert.deepEqual(sortBoardRows(rows, 'v', 'asc').map(r => r.id), ['c', 'a', 'b', 'missing']);
});

test('sorts computed values without mutating source list', () => {
  const rows = [{n: 1}, {n: 3}, {n: 2}];
  const result = sortBoardRows(rows, 'computed', 'desc', row => row.n * 2);
  assert.deepEqual(result.map(r => r.n), [3, 2, 1]);
  assert.deepEqual(rows.map(r => r.n), [1, 3, 2]);
});
