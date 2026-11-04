/* ============================================================
   Đồng hồ thời gian thực cho topbar
   ------------------------------------------------------------
   Nguyên tắc để đồng hồ *luôn đúng*:
     1. Mỗi giây đều đọc lại `Date.now()` — không cộng dồn biến đếm, nên
        không bị trôi khi tab bị treo / máy sleep.
     2. Giờ luôn tính theo múi giờ Việt Nam bằng `Intl.DateTimeFormat`
        (timeZone: Asia/Ho_Chi_Minh), KHÔNG phụ thuộc timezone của máy
        người xem. Máy đặt ở New York vẫn thấy đúng giờ HOSE.
     3. Khi tab quay lại foreground (`visibilitychange`/`pageshow`) hoặc đổi
        ngôn ngữ, đồng hồ tick lại ngay thay vì chờ nhịp kế tiếp.
   Trạng thái phiên theo lịch HOSE/HNX (giờ VN, Thứ Hai–Thứ Sáu):
     09:00–09:15 ATO · 09:15–11:30 khớp lệnh liên tục · 11:30–13:00 nghỉ trưa
     13:00–14:30 khớp lệnh liên tục · 14:30–14:45 ATC · 14:45–15:00 sau giờ.
   Ngày lễ: danh sách do build phát hành (`meta.marketHolidays`, sinh từ
     `cwintel/config.py:MARKET_HOLIDAYS`) được truyền vào `startClock({ holidays })`;
     có ngày lễ thì trạng thái là `holiday` chứ không phải "đang khớp lệnh".
   ============================================================ */

export const TZ = 'Asia/Ho_Chi_Minh';

/** Dữ liệu phiên hôm nay được kỳ vọng sau 15:10 ICT — đồng bộ cwintel/sessions.py. */
export const CLOSE_READY_MINUTES = 15 * 60 + 10;

/** Các mốc phiên, tính bằng phút trong ngày (giờ VN). */
export const BOUNDARIES = [
  [540, 'ato'],     // 09:00 — mở cửa phiên ATO
  [555, 'open'],    // 09:15 — khớp lệnh liên tục
  [690, 'break'],   // 11:30 — nghỉ trưa
  [780, 'open'],    // 13:00 — phiên chiều
  [870, 'atc'],     // 14:30 — ATC
  [885, 'post'],    // 14:45 — sau giờ khớp lệnh
  [900, 'closed'],  // 15:00 — đóng cửa
];

const VI_WEEKDAY = ['Chủ Nhật', 'Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy'];

/** Nhãn trạng thái phiên: [tiếng Việt, tiếng Anh]. */
export const SESSION_LABEL = {
  holiday: ['Nghỉ lễ', 'Market holiday'],
  weekend: ['Nghỉ cuối tuần', 'Weekend'],
  pre: ['Trước giờ mở cửa', 'Pre-open'],
  ato: ['ATO · mở cửa', 'ATO · opening'],
  open: ['Đang khớp lệnh', 'Market open'],
  break: ['Nghỉ trưa', 'Lunch break'],
  atc: ['ATC · đóng cửa', 'ATC · closing'],
  post: ['Sau giờ khớp lệnh', 'After hours'],
  closed: ['Đã đóng cửa', 'Closed'],
};

/** Nhóm màu của từng trạng thái (dùng cho class CSS). */
export const SESSION_TONE = {
  holiday: 'muted', weekend: 'muted', pre: 'muted', closed: 'muted',
  ato: 'amber', atc: 'amber', open: 'live', break: 'muted', post: 'muted',
};

const fmtParts = new Intl.DateTimeFormat('en-GB', {
  timeZone: TZ, hour12: false,
  year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', weekday: 'short',
});

const WEEKDAY_INDEX = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };

/**
 * Chuẩn hoá danh sách ngày lễ về Set 'YYYY-MM-DD'.
 * Nhận mảng chuỗi ISO, Set, hoặc hàm trả về một trong hai (để đọc `meta` muộn).
 */
export function holidaySet(list) {
  const raw = typeof list === 'function' ? list() : list;
  if (!raw) return new Set();
  const out = new Set();
  for (const item of raw) {
    if (typeof item === 'string') out.add(item.slice(0, 10));
    else if (item) out.add(dayKey(item));
  }
  return out;
}

/** 'YYYY-MM-DD' của một mốc giờ Việt Nam. */
export function dayKey(parts) {
  const p = (parts && typeof parts.day === 'number') ? parts : clockParts(parts);
  return `${p.year}-${String(p.month).padStart(2, '0')}-${String(p.day).padStart(2, '0')}`;
}

/** Trạng thái phiên từ số phút trong ngày, cờ cuối tuần và cờ ngày lễ. */
export function sessionKey(minutes, isWeekend = false, isHoliday = false) {
  if (isHoliday) return 'holiday';
  if (isWeekend) return 'weekend';
  if (!Number.isFinite(minutes)) return 'closed';
  if (minutes < BOUNDARIES[0][0]) return 'pre';
  for (let i = 0; i < BOUNDARIES.length; i += 1) {
    const [start, key] = BOUNDARIES[i];
    const end = i + 1 < BOUNDARIES.length ? BOUNDARIES[i + 1][0] : 1440;
    if (minutes >= start && minutes < end) return key;
  }
  return 'closed';
}

/**
 * Tách giờ Việt Nam từ một mốc thời gian bất kỳ.
 * @param {number|Date} now mốc thời gian (ms hoặc Date); mặc định là hiện tại
 * @param {Iterable<string>|Set<string>|Function} holidays ngày nghỉ dạng 'YYYY-MM-DD'
 */
export function clockParts(now = Date.now(), holidays = null) {
  const date = now instanceof Date ? now : new Date(now);
  const parts = {};
  for (const p of fmtParts.formatToParts(date)) parts[p.type] = p.value;
  const hour = Number(parts.hour) % 24;          // một số ICU trả '24' cho nửa đêm
  const minute = Number(parts.minute);
  const second = Number(parts.second);
  const weekday = WEEKDAY_INDEX[parts.weekday] ?? 0;
  const minutes = hour * 60 + minute;
  const isWeekend = weekday === 0 || weekday === 6;
  const day = Number(parts.day);
  const month = Number(parts.month);
  const year = Number(parts.year);
  const iso = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  const holidaySetCache = holidays == null ? null : holidaySet(holidays);
  const isHoliday = !!holidaySetCache && holidaySetCache.has(iso);
  return {
    hour, minute, second, minutes,
    weekday, isWeekend, isHoliday, iso,
    day, month, year,
    session: sessionKey(minutes, isWeekend, isHoliday),
    hhmmss: `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:`
      + String(second).padStart(2, '0'),
    hm: `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`,
  };
}

/**
 * Hôm nay đã có một phiên đóng cửa cần dữ liệu hay chưa (theo giờ Việt Nam hiện tại).
 * Khác với meta.session.todayClosed, vốn là trạng thái tại thời điểm build.
 */
export function hasClosedToday(parts) {
  return !parts.isWeekend && !parts.isHoliday && parts.minutes >= CLOSE_READY_MINUTES;
}

/** Nhãn trạng thái phiên, tự chọn ngôn ngữ. */
export function sessionLabel(session, lang = 'vi') {
  const pair = SESSION_LABEL[session] || SESSION_LABEL.closed;
  if (lang === 'en') return pair[1];
  if (lang === 'both') return `${pair[0]} · ${pair[1]}`;
  return pair[0];
}

/** "Thứ Ba · 04/11/2026" (giờ VN). */
export function dateLabel(parts, lang = 'vi') {
  const dd = String(parts.day).padStart(2, '0');
  const mm = String(parts.month).padStart(2, '0');
  if (lang === 'en') {
    const en = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][parts.weekday] || '';
    return `${en} ${dd}/${mm}/${parts.year}`;
  }
  // Ở chế độ VI+EN phần ngày dùng chung một dạng (thứ tiếng Việt) để không bị dài quá topbar;
  // nhãn trạng thái phiên mới là phần cần song ngữ.
  return `${VI_WEEKDAY[parts.weekday] || ''} · ${dd}/${mm}/${parts.year}`;
}

/** Phần trăm đã trôi qua của phút hiện tại (0–1) — dùng cho vòng giây. */
export function secondsProgress(second) {
  const s = Number.isFinite(second) ? Math.max(0, Math.min(59, second)) : 0;
  return s / 60;
}

/** Số phút còn lại tới mốc phiên kế tiếp (null khi đã đóng cửa / cuối tuần). */
export function minutesToNextBoundary(parts) {
  if (parts.isWeekend || parts.isHoliday) return null;
  for (const [start] of BOUNDARIES) {
    if (parts.minutes < start) return start - parts.minutes;
  }
  return null;
}

const RADIUS = 15;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/**
 * Gắn đồng hồ vào DOM và chạy mỗi giây.
 * @param {Document|HTMLElement} root nơi chứa các phần tử #clock-*
 * @param {{ lang?: () => string, now?: () => number,
 *           holidays?: Iterable<string>|Set<string>|Function }} opts
 * @returns {{ tick: Function, stop: Function, read: Function }}
 */
export function startClock(root, opts = {}) {
  const doc = (root && root.querySelector) ? root : document;
  const langOf = typeof opts.lang === 'function'
    ? opts.lang
    : ((typeof opts.lang === 'string') ? () => opts.lang : () => 'vi');
  const nowOf = typeof opts.now === 'function' ? opts.now : () => Date.now();
  const holidaysOf = () => (typeof opts.holidays === 'function' ? opts.holidays() : opts.holidays);
  const host = doc.querySelector('#market-clock');
  const timeEl = doc.querySelector('#clock-time');
  const dateEl = doc.querySelector('#clock-date');
  const sessionEl = doc.querySelector('#clock-session');
  const ringEl = doc.querySelector('#clock-ring');
  if (!host || !timeEl) return { tick: () => {}, stop: () => {}, read: () => null };

  let timer = null;
  let last = null;

  const read = () => {
    const parts = clockParts(nowOf(), holidaysOf());
    last = parts;
    return parts;
  };

  const tick = () => {
    const parts = read();
    const lang = langOf() || 'vi';
    timeEl.textContent = parts.hhmmss;
    if (timeEl.tagName === 'TIME') {
      timeEl.setAttribute('datetime', `${parts.year}-${String(parts.month).padStart(2, '0')}`
        + `-${String(parts.day).padStart(2, '0')}T${parts.hhmmss}+07:00`);
      timeEl.setAttribute('title', `${dateLabel(parts, lang)} · ${parts.hhmmss} (GMT+7)`);
    }
    if (dateEl) dateEl.textContent = dateLabel(parts, lang);
    if (sessionEl) sessionEl.textContent = sessionLabel(parts.session, lang);
    if (host) {
      host.dataset.session = parts.session;
      host.dataset.tone = SESSION_TONE[parts.session] || 'muted';
    }
    if (ringEl) {
      const ratio = secondsProgress(parts.second);
      ringEl.setAttribute('stroke-dasharray', CIRCUMFERENCE.toFixed(2));
      ringEl.setAttribute('stroke-dashoffset', (CIRCUMFERENCE * (1 - ratio)).toFixed(2));
    }
    const next = minutesToNextBoundary(parts);
    if (host) {
      const label = sessionLabel(parts.session, lang);
      const en = lang === 'en';
      const tzWord = en ? 'Vietnam time' : 'giờ Việt Nam';
      host.setAttribute('aria-label', next === null
        ? `${label} · ${parts.hhmmss} ${tzWord}`
        : en
          ? `${label} · ${parts.hhmmss} ${tzWord} · ${next} min to the next session mark`
          : `${label} · ${parts.hhmmss} ${tzWord} · còn ${next} phút tới mốc phiên kế tiếp`);
      host.title = next === null
        ? `${label} — ${parts.hhmmss} (GMT+7)`
        : en
          ? `${label} — ${next} min to the next session mark (GMT+7)`
          : `${label} — còn ${next} phút tới mốc phiên kế tiếp (GMT+7)`;
    }
    return parts;
  };

  tick();
  timer = setInterval(tick, 1000);              // luôn đọc lại Date.now(), không cộng dồn

  const resync = () => tick();
  if (typeof document !== 'undefined' && document.addEventListener) {
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) resync();
    });
  }
  if (typeof window !== 'undefined' && window.addEventListener) {
    window.addEventListener('pageshow', resync);
    window.addEventListener('cwintel:lang', resync);
    window.addEventListener('focus', resync);
  }

  const stop = () => {
    if (timer) clearInterval(timer);
    timer = null;
  };

  return { tick, stop, read: () => last };
}
