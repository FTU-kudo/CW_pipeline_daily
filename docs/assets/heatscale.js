/* ============================================================
   Thang màu cho heatmap — hàm thuần, không phụ thuộc DOM.
   ------------------------------------------------------------
   Tách riêng khỏi heatmap.js để (a) test được bằng Node, (b) đảm bảo
   MỌI ô đều có màu hợp lệ và chữ trên ô đạt WCAG AA ở cả light/dark.

   Quy ước:
   - scaleColor(value, scale, domain) luôn trả về '#rrggbb' hợp lệ.
   - readable(bg) chỉnh nhẹ độ sáng của nền (giữ nguyên sắc) cho tới khi
     chữ trắng hoặc chữ đen đạt tương phản >= 4.6:1, rồi trả về cặp màu.
   ============================================================ */

/** Màu cho ô không có dữ liệu (trung tính, đọc được ở cả hai theme). */
export const NO_DATA_COLOR = '#78838f';

const HEX_RE = /^#[0-9a-fA-F]{6}$/;

/** Chuẩn hoá & kiểm tra mã màu; trả về fallback nếu hỏng. */
export function safeHex(color, fallback = NO_DATA_COLOR) {
  if (typeof color !== 'string') return fallback;
  const c = color.trim();
  if (HEX_RE.test(c)) return c.toLowerCase();
  if (/^#[0-9a-fA-F]{3}$/.test(c)) {
    return ('#' + c[1] + c[1] + c[2] + c[2] + c[3] + c[3]).toLowerCase();
  }
  return fallback;
}

function channels(hex) {
  const h = safeHex(hex);
  return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
}

/** Trộn hai màu theo t ∈ [0,1]; luôn trả về màu hợp lệ (không bao giờ #NaN). */
export function mix(a, b, t) {
  const ca = channels(a);
  const cb = channels(b);
  const k = Number.isFinite(t) ? Math.max(0, Math.min(1, t)) : 0;
  const out = ca.map((v, i) => Math.round(v + (cb[i] - v) * k));
  return '#' + out.map((v) => Math.max(0, Math.min(255, v)).toString(16).padStart(2, '0')).join('');
}

/** Độ chói tương đối theo WCAG 2.x. */
export function luminance(hex) {
  const [r, g, b] = channels(hex).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** Tỉ lệ tương phản giữa hai màu (1–21). */
export function contrast(a, b) {
  const la = luminance(a);
  const lb = luminance(b);
  const hi = Math.max(la, lb);
  const lo = Math.min(la, lb);
  return (hi + 0.05) / (lo + 0.05);
}

export const TEXT_ON_DARK = '#ffffff';
export const TEXT_ON_LIGHT = '#0b1118';

/** Chọn màu chữ cho nền `bg` sao cho tương phản cao nhất. */
export function pickText(bg) {
  const light = contrast(bg, TEXT_ON_LIGHT);
  const dark = contrast(bg, TEXT_ON_DARK);
  return light >= dark ? TEXT_ON_LIGHT : TEXT_ON_DARK;
}

/**
 * Đảm bảo nền + chữ đạt tương phản tối thiểu, chỉ dịch độ sáng của nền
 * (giữ sắc màu để ý nghĩa tăng/giảm không bị sai).
 * @returns {{bg: string, fg: string, ratio: number}}
 */
export function readable(bg, minRatio = 4.6) {
  let color = safeHex(bg);
  let fg = pickText(color);
  let ratio = contrast(color, fg);
  for (let i = 0; i < 8 && ratio < minRatio; i += 1) {
    // chữ sáng → nền tối lại; chữ tối → nền sáng lên
    color = mix(color, fg === TEXT_ON_DARK ? '#000000' : '#ffffff', 0.09);
    fg = pickText(color);
    ratio = contrast(color, fg);
  }
  return { bg: color, fg, ratio };
}

/** Chuẩn hoá domain: hàm / mảng / số / null đều dùng được. */
export function resolveDomain(domain, rows = []) {
  if (typeof domain === 'function') {
    try {
      return resolveDomain(domain(rows), rows);
    } catch {
      return null;
    }
  }
  if (Array.isArray(domain)) {
    const [lo, hi] = domain.map(Number);
    if (Number.isFinite(lo) && Number.isFinite(hi)) return [lo, hi];
    return null;
  }
  if (Number.isFinite(domain)) return domain;
  return null;
}

/* ---------- bảng màu cho từng thang ---------- */
const DIV_NEUTRAL = '#64748b';
const DIV_UP = '#0f9d6e';
const DIV_DOWN = '#d33f3f';
const POS = '#0b8f62';
const MID = '#c68a00';
const NEG = '#b3261e';
const BLUE_LO = '#1d3f8f';
const BLUE_HI = '#4aa3ff';
const TEAL_LO = '#0f3f4a';
const TEAL_HI = '#00b894';

/** Số dương/âm của thang 'div' được chuẩn hoá theo biên độ hi. */
function divColor(value, hi) {
  const amp = Number.isFinite(hi) && hi > 0 ? hi : Math.max(1, Math.abs(value || 1));
  const t = Math.max(-1, Math.min(1, (Number.isFinite(value) ? value : 0) / amp));
  return t >= 0 ? mix(DIV_NEUTRAL, DIV_UP, t) : mix(DIV_NEUTRAL, DIV_DOWN, -t);
}

function bandColor(value, lo, hi, stops) {
  const span = Number.isFinite(hi) && Number.isFinite(lo) && hi > lo ? hi - lo : 0;
  const t = span ? Math.max(0, Math.min(1, ((Number.isFinite(value) ? value : lo) - lo) / span)) : 0.5;
  if (t <= 0.5) return mix(stops[0], stops[1], t / 0.5);
  return mix(stops[1], stops[2], (t - 0.5) / 0.5);
}

/**
 * Màu nền cho một giá trị. Không bao giờ trả về chuỗi không hợp lệ.
 * @param {number} value
 * @param {'div'|'score'|'asc'|'blue'|'maturity'|'intensity'|string} scale
 * @param {[number, number]|number|null} domain
 */
export function scaleColor(value, scale, domain) {
  if (!Number.isFinite(value)) return NO_DATA_COLOR;
  const resolved = resolveDomain(domain);
  const arr = Array.isArray(resolved) ? resolved : null;

  switch (scale) {
    case 'div': {
      const hi = arr ? arr[1] : (Number.isFinite(resolved) ? resolved : null);
      return divColor(value, hi);
    }
    case 'score':
      return bandColor(value, 0, 100, [NEG, MID, POS]);
    case 'asc':
      return bandColor(value, arr ? arr[0] : 0, arr ? arr[1] : 100, [POS, MID, NEG]);
    case 'blue':
      return bandColor(value, arr ? arr[0] : 15, arr ? arr[1] : 100, [BLUE_LO, '#2f6fbf', BLUE_HI]);
    case 'maturity':
      return bandColor(value, arr ? arr[0] : 0, arr ? arr[1] : 365, [NEG, MID, POS]);
    case 'intensity': {
      const t = Math.max(0, Math.min(1, Math.log10(Math.max(1, value)) / 10));
      return mix(TEAL_LO, TEAL_HI, t);
    }
    default:
      return NO_DATA_COLOR;
  }
}

/** Các điểm màu cho thanh legend (đã gồm cả trường hợp thiếu domain). */
export function legendStops(scale, domain, n = 7) {
  const resolved = resolveDomain(domain);
  const arr = Array.isArray(resolved) ? resolved : null;
  const count = Math.max(2, Math.min(12, n));
  let lo = arr ? arr[0] : 0;
  let hi = arr ? arr[1] : 100;
  if (scale === 'div') {
    const amp = arr ? arr[1] : (Number.isFinite(resolved) ? resolved : 1);
    lo = -Math.abs(amp) || -1;
    hi = Math.abs(amp) || 1;
  }
  if (scale === 'intensity') { lo = 10; hi = 1e10; }
  if (!(hi > lo)) { lo = 0; hi = lo + 1; }
  return Array.from({ length: count }, (_, i) => {
    const v = lo + ((hi - lo) * i) / (count - 1);
    return scaleColor(scale === 'intensity' ? 10 ** (Math.log10(hi) * (i / (count - 1))) : v, scale, resolved);
  });
}
