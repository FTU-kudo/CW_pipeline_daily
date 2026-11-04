/* Kiểm thử thang màu heatmap — chạy: node tests/js/heatscale.test.mjs
   Không phụ thuộc thư viện ngoài; quy tắc chính là bất biến mà UI dựa vào:
   mọi ô phải có màu hợp lệ (không #NaN) và chữ trên ô đạt WCAG AA. */
import assert from 'node:assert/strict';
import {
  NO_DATA_COLOR, contrast, legendStops, luminance, mix, pickText,
  readable, resolveDomain, safeHex, scaleColor,
} from '../../docs/assets/heatscale.js';

const HEX = /^#[0-9a-f]{6}$/;
const SCALES = ['div', 'score', 'asc', 'blue', 'maturity', 'intensity'];
const DOMAINS = {
  div: [0, 12],
  score: [0, 100],
  asc: [0, 60],
  blue: [15, 90],
  maturity: [0, 365],
  intensity: null,
};

let checks = 0;

/* 1. mix() không bao giờ sinh #NaN (nguồn gốc bug cũ) */
for (const t of [-5, 0, 0.25, 0.5, 1, 2, NaN, undefined, 'x']) {
  const c = mix('#1b2735', '#00c896', t);
  assert.match(c, HEX, `mix(t=${t}) trả về ${c}`);
  checks += 1;
}
assert.equal(mix('#zzzzzz', '#00c896', 0.5), mix(NO_DATA_COLOR, '#00c896', 0.5), 'màu hỏng phải fallback');

/* 2. scaleColor hợp lệ với mọi giá trị, kể cả NaN/null/undefined */
for (const scale of SCALES) {
  const domain = DOMAINS[scale];
  const samples = [NaN, null, undefined, -1e9, -100, -1, 0, 0.5, 1, 5, 10, 50, 100, 365, 1e6, Infinity];
  for (const v of samples) {
    const c = scaleColor(v, scale, domain);
    assert.match(c, HEX, `${scale}(${v}) trả về ${c}`);
    checks += 1;
  }
}
assert.equal(scaleColor(50, 'khong-ton-tai', null), NO_DATA_COLOR);

/* 3. domain nhận hàm / mảng / số / null và không còn là hàm khi resolve */
assert.deepEqual(resolveDomain((rows) => [0, 12], []), [0, 12]);
assert.deepEqual(resolveDomain([0, '12'], []), [0, 12]);
assert.equal(resolveDomain(12, []), 12);
assert.equal(resolveDomain(null, []), null);
assert.equal(resolveDomain(() => { throw new Error('boom'); }, []), null);
assert.notEqual(typeof resolveDomain((() => [0, 1]), []), 'function', 'domain phải được resolve, không truyền hàm vào scaleColor');

/* 4. Chữ trên mọi ô đạt WCAG AA (>= 4.5:1) sau khi qua readable() */
for (const scale of SCALES) {
  const domain = DOMAINS[scale];
  for (let v = -100; v <= 400; v += 1) {
    const { bg, fg, ratio } = readable(scaleColor(v, scale, domain));
    assert.match(bg, HEX);
    assert.match(fg, HEX);
    assert.ok(ratio >= 4.5, `${scale}(${v}): ${fg} trên ${bg} chỉ ${ratio.toFixed(2)}:1`);
    checks += 1;
  }
}

/* 5. pickText chọn đúng phía */
assert.equal(pickText('#000000'), '#ffffff');
assert.equal(pickText('#ffffff'), '#0b1118');
assert.ok(luminance('#ffffff') > luminance('#000000'));

/* 6. Legend: 7 điểm màu hợp lệ, kể cả khi thiếu domain */
for (const scale of SCALES) {
  const stops = legendStops(scale, DOMAINS[scale], 7);
  assert.equal(stops.length, 7);
  for (const c of stops) assert.match(c, HEX, `${scale} legend trả ${c}`);
  const fallback = legendStops(scale, null, 5);
  for (const c of fallback) assert.match(c, HEX, `${scale} legend(null) trả ${c}`);
}

/* 7. safeHex */
assert.equal(safeHex('#ABC'), '#aabbcc');
assert.equal(safeHex('#123456 '), '#123456');
assert.equal(safeHex('red'), NO_DATA_COLOR);
assert.ok(contrast('#000000', '#ffffff') > 20);

console.log(`heatscale: OK — ${checks} phép kiểm tra`);
