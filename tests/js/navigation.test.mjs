import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { slugifyVietnamese, urlForView, viewFromSearch, VIEW_SLUGS } from '../../docs/assets/navigation.mjs';

test('Vietnamese navigation labels normalize to canonical slugs', () => {
  assert.deepEqual(VIEW_SLUGS, {
    board: 'bang-gia',
    scoring: 'xep-hang',
    valuation: 'dinh-gia',
    liquidity: 'thanh-khoan',
    underlyings: 'theo-co-so',
    stale: 'ma-khong-giao-dich',
    intraday: 'trong-phien',
    band: 'tran-san',
    history: 'lich-su',
    glossary: 'giai-thich-thuat-ngu',
  });
  assert.equal(slugifyVietnamese('Định giá · Trần–sàn'), 'dinh-gia-tran-san');
});

test('every current navigation button has a URL slug mapping', () => {
  const html = fs.readFileSync(new URL('../../docs/index.html', import.meta.url), 'utf8');
  const viewIds = [...html.matchAll(/data-view="([^"]+)"/g)].map(([, view]) => view);
  assert.ok(viewIds.length > 0);
  for (const view of viewIds) assert.ok(VIEW_SLUGS[view], `missing slug mapping for ${view}`);
});

test('initial tab query resolves known views and safely defaults invalid/missing values', () => {
  assert.equal(viewFromSearch('?tab=dinh-gia'), 'valuation');
  assert.equal(viewFromSearch('?tab=giai-thich-thuat-ngu'), 'glossary');
  assert.equal(viewFromSearch('?tab=tran-san'), 'band');
  assert.equal(viewFromSearch('?tab=not-a-tab'), 'board');
  assert.equal(viewFromSearch(''), 'board');
});

test('view URLs stay on the current path and preserve unrelated query/hash state', () => {
  const href = 'https://example.test/?campaign=demo#table';
  assert.equal(urlForView(href, 'valuation'), '/?campaign=demo&tab=dinh-gia#table');
  assert.equal(urlForView('https://example.test/?campaign=demo&tab=valuation', 'glossary'),
    '/?campaign=demo&tab=giai-thich-thuat-ngu');
  assert.equal(urlForView('https://example.test/?tab=xep-hang#top', 'board'), '/#top');
});
