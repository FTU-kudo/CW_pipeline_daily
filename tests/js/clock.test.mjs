/* Kiểm thử đồng hồ thời gian thực — chạy: node tests/js/clock.test.mjs
   Bất biến quan trọng nhất: đồng hồ phải đúng giờ Việt Nam bất kể timezone
   của máy người xem, và trạng thái phiên phải khớp lịch HOSE/HNX. */
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import {
  BOUNDARIES, SESSION_LABEL, SESSION_TONE, TZ,
  clockParts, dateLabel, minutesToNextBoundary, secondsProgress, sessionKey, sessionLabel,
} from '../../docs/assets/clock.js';

let checks = 0;
const ok = (cond, msg) => { assert.ok(cond, msg); checks += 1; };

/* 1. Múi giờ cố định + chuyển đổi UTC → giờ VN */
ok(TZ === 'Asia/Ho_Chi_Minh', 'múi giờ phải là Asia/Ho_Chi_Minh');
const at = (iso) => clockParts(new Date(iso));
ok(at('2026-11-04T02:00:00Z').hhmmss === '09:00:00', '02:00Z phải là 09:00 giờ VN');
ok(at('2026-11-04T02:00:00Z').hm === '09:00', 'HH:MM đúng');
ok(at('2026-11-04T17:59:59Z').hhmmss === '00:59:59', 'qua nửa đêm VN vẫn đúng (không ra 24h)');

/* 2. Trạng thái phiên tại từng mốc (giờ VN → UTC = giờ VN − 7) */
const cases = [
  ['2026-11-04T01:59:00Z', 'pre', 'trước 09:00'],
  ['2026-11-04T02:00:00Z', 'ato', 'đúng 09:00 = ATO'],
  ['2026-11-04T02:14:59Z', 'ato', '09:14:59 vẫn ATO'],
  ['2026-11-04T02:15:00Z', 'open', '09:15 khớp lệnh liên tục'],
  ['2026-11-04T04:29:59Z', 'open', '11:29:59 còn khớp lệnh'],
  ['2026-11-04T04:30:00Z', 'break', '11:30 nghỉ trưa'],
  ['2026-11-04T05:59:59Z', 'break', '12:59:59 vẫn nghỉ'],
  ['2026-11-04T06:00:00Z', 'open', '13:00 phiên chiều'],
  ['2026-11-04T07:30:00Z', 'atc', '14:30 ATC'],
  ['2026-11-04T07:44:59Z', 'atc', '14:44:59 vẫn ATC'],
  ['2026-11-04T07:45:00Z', 'post', '14:45 sau giờ khớp lệnh'],
  ['2026-11-04T08:00:00Z', 'closed', '15:00 đóng cửa'],
  ['2026-11-04T12:00:00Z', 'closed', '19:00 đóng cửa'],
];
for (const [iso, want, why] of cases) ok(at(iso).session === want, `${iso} → ${why}`);
ok(at('2026-11-07T03:00:00Z').session === 'weekend', 'Thứ Bảy 10:00 là nghỉ cuối tuần');
ok(at('2026-11-08T03:00:00Z').session === 'weekend', 'Chủ Nhật là nghỉ cuối tuần');
ok(at('2026-11-09T02:30:00Z').session === 'open', 'Thứ Hai 09:30 khớp lệnh trở lại');

/* 3. sessionKey trực tiếp theo số phút */
ok(sessionKey(0) === 'pre' && sessionKey(539) === 'pre', 'nửa đêm → trước giờ mở cửa');
ok(sessionKey(900) === 'closed' && sessionKey(1439) === 'closed', 'sau 15:00 → đóng cửa');
ok(sessionKey(600, true) === 'weekend', 'cuối tuần thắng mọi mốc giờ');
ok(BOUNDARIES.every(([m], i, a) => i === 0 || m > a[i - 1][0]), 'các mốc phiên phải tăng dần');

/* 4. Nhãn VI/EN/VI+EN + màu trạng thái */
ok(sessionLabel('open', 'vi') === SESSION_LABEL.open[0], 'nhãn VI');
ok(sessionLabel('open', 'en') === SESSION_LABEL.open[1], 'nhãn EN');
ok(sessionLabel('open', 'both').includes('·'), 'chế độ VI+EN hiển thị cả hai');
ok(SESSION_TONE.open === 'live', 'phiên khớp lệnh phải là tone "live"');
ok(SESSION_TONE.weekend === 'muted' && SESSION_TONE.atc === 'amber', 'tone của weekend/ATC');
for (const key of Object.keys(SESSION_LABEL)) {
  ok(sessionLabel(key, 'vi') && sessionLabel(key, 'en'), `có nhãn cho trạng thái ${key}`);
}

/* 5. Ngày tháng */
const wed = at('2026-11-04T02:00:00Z');
ok(wed.weekday === 3, '2026-11-04 là Thứ Tư');
ok(dateLabel(wed, 'vi').includes('Thứ Tư') && dateLabel(wed, 'vi').includes('04/11/2026'), 'nhãn ngày VI');
ok(dateLabel(wed, 'en').includes('Wed') && dateLabel(wed, 'en').includes('04/11/2026'), 'nhãn ngày EN');

/* 6. Vòng giây + đếm ngược mốc phiên */
ok(secondsProgress(0) === 0 && secondsProgress(30) === 0.5, 'vòng giây tuyến tính');
ok(secondsProgress(59) < 1 && secondsProgress(-5) === 0 && secondsProgress(NaN) === 0, 'vòng giây an toàn');
ok(minutesToNextBoundary(at('2026-11-04T02:00:00Z')) === 15, '09:00 còn 15 phút tới 09:15');
ok(minutesToNextBoundary(at('2026-11-04T02:20:00Z')) === 130, '09:20 còn 130 phút tới 11:30');
ok(minutesToNextBoundary(at('2026-11-04T08:30:00Z')) === null, 'sau 15:00 không còn mốc');
ok(minutesToNextBoundary(at('2026-11-07T02:00:00Z')) === null, 'cuối tuần không đếm ngược');

/* 7. Không phụ thuộc timezone của máy: chạy lại trong tiến trình có TZ khác */
const script = `
  import('${new URL('../../docs/assets/clock.js', import.meta.url).href}').then((m) => {
    const p = m.clockParts(new Date('2026-11-04T02:00:00Z'));
    console.log(p.hhmmss + '|' + p.session);
  });
`;
for (const tz of ['America/New_York', 'Europe/London', 'Asia/Tokyo']) {
  const out = execFileSync(process.execPath, ['--input-type=module', '-e', script], {
    env: { ...process.env, TZ: tz }, encoding: 'utf8',
  }).trim();
  ok(out === '09:00:00|ato', `TZ=${tz} vẫn ra 09:00 ATO (nhận được ${out})`);
}

/* 8. Đồng hồ + KPI mới phải đạt WCAG AA ở cả hai theme (đọc token thật từ app.css) */
{
  const fs = await import('node:fs');
  const { contrast, mix } = await import('../../docs/assets/heatscale.js');
  const css = fs.readFileSync(new URL('../../docs/assets/app.css', import.meta.url), 'utf8');
  const palettes = {};
  for (const theme of ['dark', 'light']) {
    const block = css.split(`html[data-theme="${theme}"] {`)[1];
    ok(!!block, `đọc được palette ${theme}`);
    const body = block.split('}')[0];
    const tokens = {};
    for (const m of body.matchAll(/--([a-z0-9-]+):\s*(#[0-9a-f]{6})/gi)) tokens[m[1]] = m[2];
    palettes[theme] = tokens;
  }
  for (const [theme, t] of Object.entries(palettes)) {
    const clockBg = mix(t['surface-2'], t.accent, 0.08);
    ok(contrast(t.text, clockBg) >= 7, `${theme}: giờ HH:MM:SS tương phản cao (${contrast(t.text, clockBg).toFixed(1)})`);
    ok(contrast(t['text-2'], clockBg) >= 4.5, `${theme}: ngày tháng ≥ AA (${contrast(t['text-2'], clockBg).toFixed(1)})`);
    ok(contrast(t['text-3'], t.surface) >= 4.5, `${theme}: nhãn phiên "muted" ≥ AA`);
    const liveFg = mix(t.accent, t.text, 0.12);
    const liveBg = mix(t.surface, t.accent, 0.12);
    ok(contrast(liveFg, liveBg) >= 4.5, `${theme}: nhãn phiên "đang khớp lệnh" ≥ AA (${contrast(liveFg, liveBg).toFixed(1)})`);
    const amberFg = mix(t.warn, t.text, 0.16);
    const amberBg = mix(t.surface, t.warn, 0.12);
    ok(contrast(amberFg, amberBg) >= 4.5, `${theme}: nhãn phiên ATO/ATC ≥ AA (${contrast(amberFg, amberBg).toFixed(1)})`);
    for (const tone of ['up', 'down', 'warn']) {
      const fg = tone === 'warn' ? mix(t.warn, t.text, 0.15) : mix(t[tone], t.text, 0.18);
      const ratio = contrast(fg, t['surface-2']);
      ok(ratio >= 4.5, `${theme}: KPI tone-${tone} ≥ AA (${ratio.toFixed(1)})`);
    }
  }
  // CSS phải dùng đúng các hệ số đã kiểm tra ở trên
  ok(css.includes('color-mix(in srgb, var(--accent) 88%, var(--text))')
    || css.includes('color-mix(in srgb, var(--accent) 88%, var(--text))'), 'nhãn phiên live dùng màu pha sáng/tối');
  ok(css.includes('.clock-time') && css.includes('.clock-session') && css.includes('.kpi-card.tone-up::before'),
    'CSS có đủ thành phần đồng hồ + KPI tone');
}
console.log(`clock: ${checks} kiểm tra OK (đã gồm WCAG)`);
