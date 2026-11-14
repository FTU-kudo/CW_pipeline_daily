/* ============================================================
   Giao diện: sáng/tối · Việt/Anh · đồng hồ · chi tiết chứng quyền
   ------------------------------------------------------------
   Trang này cố ý KHÔNG dùng framework và KHÔNG gọi mạng tới nhà cung cấp dữ liệu:
   mọi thứ đọc từ file JSON đã publish cùng repo.

   Bốn phần, độc lập nhau:
     1. i18n      — từ điển VI→EN + áp dụng cho DOM, cho phép đổi ngôn ngữ tại chỗ.
     2. theme     — data-theme trên <html>, lưu vào localStorage, tôn trọng cài đặt hệ thống.
     3. clock     — đọc lại Date.now() mỗi giây (không cộng dồn), luôn theo giờ Việt Nam.
     4. detail    — bấm một mã để xem toàn bộ thông tin của mã đó.

   Nguyên tắc: **không hiển thị số 0 thay cho "không có dữ liệu"**. Trường thiếu hiển thị
   "—" kèm lý do; người đọc phải phân biệt được "không giao dịch" với "không đo được".
   ============================================================ */

/* ---------------------------------------------------------------
   1. I18N — khoá là chuỗi tiếng Việt HIỂN THỊ, giá trị là tiếng Anh
   --------------------------------------------------------------- */
export const STRINGS = {
  // Tiêu đề & công cụ
  'Covered Warrants — Yuanta': 'Covered Warrants — Yuanta',
  'Bảng giá hiện tại từ endpoint stock_type=EW · dữ liệu được cập nhật theo lịch, không phải realtime':
    'Current board from the stock_type=EW endpoint · updated on a schedule, not realtime',
  'Sáng': 'Light',
  'Tối': 'Dark',
  'Ngôn ngữ': 'Language',
  'Đang đọc snapshot…': 'Reading snapshot…',
  'Snapshot chưa có': 'No snapshot yet',

  // Đồng hồ
  'Giờ Việt Nam': 'Vietnam time',
  'Đồng hồ thị trường': 'Market clock',
  'Nghỉ lễ': 'Market holiday',
  'Cuối tuần': 'Weekend',
  'Trước giờ mở cửa': 'Before the open',
  'Phiên ATO': 'ATO session',
  'Khớp lệnh liên tục': 'Continuous trading',
  'Nghỉ trưa': 'Lunch break',
  'Phiên ATC': 'ATC session',
  'Sau giờ khớp lệnh': 'After trading',
  'Đã đóng cửa': 'Closed',
  'còn {n} phút tới mốc phiên kế tiếp': '{n} min to the next session mark',

  // Thanh tab
  'Bảng giá': 'Board',
  'Xếp hạng': 'Ranking',
  'Định giá': 'Valuation',
  'Thanh khoản': 'Liquidity',
  'Theo cơ sở': 'By underlying',
  'Mã không giao dịch': 'Not trading',
  'Trong phiên': 'Intraday',
  'Trần–sàn': 'Price band',
  'Lịch sử': 'History',
  'Chi tiết mã': 'Ticker detail',

  // Bảng & thẻ
  'Mã': 'Ticker',
  'Cơ sở': 'Underlying',
  'Giá (VND)': 'Price (VND)',
  '%Ngày': '%Day',
  'Khối lượng': 'Volume',
  'Giá trị': 'Value',
  'Spread (bước giá)': 'Spread (ticks)',
  'Tỷ trọng GT': 'Value share',
  'Điểm': 'Score',
  'IV': 'IV',
  'Delta': 'Delta',
  'Đáo hạn': 'Maturity',
  'Số phiên': 'Sessions',
  'Độ phủ': 'Coverage',
  'Trạng thái': 'Status',
  'CW trong snapshot': 'Warrants in snapshot',
  'Giá trị giao dịch': 'Traded value',
  'Spread trung vị': 'Median spread',
  'Cổ phiếu cơ sở': 'Underlyings',
  'Tăng / giảm': 'Gainers / losers',
  'Kiểm tra chất lượng dữ liệu': 'Data quality check',
  'Đang tải…': 'Loading…',
  'Không có mã phù hợp.': 'No matching ticker.',
  'Tải JSON snapshot': 'Download JSON snapshot',
  'JSON gốc': 'Raw JSON',
  'mã có khớp lệnh': 'tickers traded',
  'VND trong phiên — không phải ADV': 'VND this session — not ADV',
  'bước giá (10 VND)': 'ticks (10 VND)',
  'nhóm suy ra từ mã CW': 'grouped from warrant codes',
  'mã đứng giá': 'tickers unchanged',
  'Lọc theo mã chứng quyền…': 'Filter by warrant code…',

  // Chi tiết mã
  'Thông tin chứng quyền': 'Warrant detail',
  'Đóng': 'Close',
  'Trường gốc từ API': 'Raw API fields',
  'Giá & thanh khoản': 'Price & liquidity',
  'Định giá Black–Scholes': 'Black–Scholes valuation',
  'Điểm số': 'Score',
  'Dải trần–sàn': 'Price band',
  'Trong phiên hôm nay': 'Today intraday',
  'Lịch sử theo phiên': 'Session history',
  'Cổ phiếu cơ sở (tham chiếu)': 'Underlying (reference)',
  'Bid / Ask': 'Bid / Ask',
  'Khối ngoại & room': 'Foreign flow & room',
  'Không giao dịch trong phiên': 'Not traded this session',
  'Không có khối định giá cho mã này': 'No valuation block for this ticker',
  'Chưa tích luỹ đủ lịch sử': 'Not enough history accumulated',
  'Bấm một mã ở cột đầu để xem toàn bộ thông tin': 'Click a ticker in the first column for full detail',
  'Chọn mã để xem chi tiết': 'Pick a ticker to see detail',
  'Không tìm thấy mã': 'Ticker not found',
  'Sao chép mã': 'Copy ticker',
  'Đã sao chép': 'Copied',
  'Mở trong tab mới': 'Open in new tab',

  // Nhãn trường
  'Giá khớp cuối': 'Last price',
  'Giá tham chiếu (đóng cửa phiên trước)': 'Reference (previous close)',
  'Giá mở cửa': 'Open',
  'Cao nhất': 'Highest',
  'Thấp nhất': 'Lowest',
  'Giá bình quân': 'Average price',
  'Thay đổi trong ngày': 'Change',
  'Trần': 'Ceiling',
  'Sàn': 'Floor',
  'Khối lượng khớp': 'Matched volume',
  'Giá trị khớp': 'Matched value',
  'Giá mua/bán tốt nhất': 'Best bid/ask',
  'Khối ngoại mua': 'Foreign buy volume',
  'Khối ngoại bán': 'Foreign sell volume',
  'Room ngoại còn lại': 'Remaining foreign room',
  'Strike': 'Strike',
  'Tỷ lệ chuyển đổi': 'Conversion ratio',
  'Ngày đáo hạn': 'Maturity date',
  'Số ngày còn lại': 'Days to maturity',
  'Giá cổ phiếu cơ sở': 'Underlying price',
  'Nguồn giá cơ sở': 'Underlying price source',
  'Premium hoà vốn': 'Break-even premium',
  'Đòn bẩy': 'Leverage',
  'Giá trị nội tại': 'Intrinsic value',
  'Giá trị thời gian': 'Time value',
  'IV (biến động ẩn)': 'IV (implied volatility)',
  'HV 21 phiên': 'HV 21 sessions',
  'HV 63 phiên': 'HV 63 sessions',
  'IV − HV': 'IV − HV',
  'IV nhóm cùng cơ sở': 'IV of the same-underlying group',
  'Chênh lệch IV': 'IV vs group',
  'ITM/ATM/OTM': 'ITM/ATM/OTM',
  'Gamma': 'Gamma',
  'Theta': 'Theta',
  'Vega': 'Vega',
  'Rho': 'Rho',
  'Delta quy đổi': 'Delta (converted)',
  'Lý do không định giá': 'Why not valued',
  'Số phiên có giao dịch': 'Sessions traded',
  'Phiên trắng liên tiếp': 'Consecutive idle sessions',
  'Giá đóng cửa': 'Close',
  'Cao': 'High',
  'Thấp': 'Low',
  'Mở': 'Open',
  'Tỷ lệ giá trên trần': 'Distance to ceiling',
  'Tỷ lệ giá trên sàn': 'Distance to floor',
  'Đang ở trần': 'At ceiling',
  'Đang ở sàn': 'At floor',
};

/* Câu có số liệu do engine sinh: [regex, hàm ghép tiếng Anh]. Chỉ những mẫu thường gặp —
   mẫu nào không khớp thì giữ nguyên tiếng Việt, KHÔNG đoán nghĩa. */
export const TEMPLATES = [
  [/^(\d+) mã có khớp lệnh$/, (n) => `${n} tickers traded`],
  [/^(\d+) mã không giao dịch$/, (n) => `${n} tickers not trading`],
  [/^(\d+) \/ ([\d.]+) mã$/, (a, b) => `${a} / ${b} tickers`],
  [/^Lấy lúc (.+)$/, (t) => `Fetched ${t}`],
  [/^Phiên (.+)$/, (d) => `Session ${d}`],
  [/^(\d+) phiên$/, (n) => `${n} sessions`],
  [/^IV trung vị ([\d.,]+)%$/, (v) => `Median IV ${v}%`],
];

let lang = 'vi';
let observer = null;
const originals = new Map();

export function getLang() { return lang; }
export function bi(vi, en) { return lang === 'en' ? en : vi; }

export function translate(text) {
  if (!text) return null;
  const key = text.trim();
  if (!key) return null;
  if (Object.prototype.hasOwnProperty.call(STRINGS, key)) return STRINGS[key];
  for (const [re, fn] of TEMPLATES) {
    const m = key.match(re);
    if (m) { try { return fn(...m.slice(1)); } catch { return null; } }
  }
  return null;
}

const SKIP = new Set(['SCRIPT', 'STYLE', 'PRE', 'CODE', 'CANVAS']);
const SKIP_CLASS = new Set(['i18n-skip']);

function applyNode(node) {
  const raw = node.nodeValue;
  if (!raw || !raw.trim()) return;
  const parent = node.parentElement;
  if (!parent || SKIP.has(parent.tagName) || parent.closest('[data-no-i18n]')) return;
  for (const c of parent.classList) if (SKIP_CLASS.has(c)) return;
  const core = raw.trim();
  const en = translate(core);
  if (!en || en === core) return;
  if (!originals.has(node)) originals.set(node, raw);
  const lead = raw.match(/^\s*/)[0];
  const trail = raw.match(/\s*$/)[0];
  node.nodeValue = lead + (lang === 'en' ? en : (originals.get(node) || core).trim()) + trail;
}

function applyAttrs(root) {
  for (const el of root.querySelectorAll('[placeholder],[title],[aria-label]')) {
    for (const attr of ['placeholder', 'title', 'aria-label']) {
      const saved = 'data-vi-' + attr;
      const current = el.getAttribute(attr);
      if (current && !el.hasAttribute(saved)) el.setAttribute(saved, current);
      const base = el.getAttribute(saved);
      if (!base) continue;
      const en = translate(base);
      if (!en) continue;
      el.setAttribute(attr, lang === 'en' ? en : base);
    }
  }
}

export function applyI18n(root = document.body) {
  if (!root) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const batch = [];
  let node;
  while ((node = walker.nextNode())) batch.push(node);
  batch.forEach(applyNode);
  applyAttrs(root);
}

function reset() {
  for (const [node, raw] of originals) if (node.isConnected) node.nodeValue = raw;
  originals.clear();
}

export function setLang(next) {
  const value = next === 'en' ? 'en' : 'vi';
  if (value === lang) return;
  lang = value;
  try { localStorage.setItem('cwintel:lang', value); } catch { /* chế độ riêng tư */ }
  document.documentElement.lang = value;
  document.documentElement.dataset.lang = value;
  reset();
  applyI18n(document.body);
  syncButtons();
  window.dispatchEvent(new CustomEvent('cwintel:lang', { detail: { lang: value } }));
}

export function onLangChange(fn) {
  window.addEventListener('cwintel:lang', (event) => fn(event.detail.lang));
}

function syncButtons() {
  for (const b of document.querySelectorAll('[data-lang-set]')) {
    const on = b.dataset.langSet === lang;
    b.classList.toggle('on', on);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
  }
}

export function initI18n() {
  let saved = 'vi';
  try { saved = localStorage.getItem('cwintel:lang') || 'vi'; } catch { /* ignore */ }
  lang = saved === 'en' ? 'en' : 'vi';
  document.documentElement.lang = lang;
  document.documentElement.dataset.lang = lang;
  for (const b of document.querySelectorAll('[data-lang-set]')) {
    b.addEventListener('click', () => setLang(b.dataset.langSet));
  }
  syncButtons();
  // Áp dụng lại sau mỗi lần render: nội dung do JS sinh cũng phải được dịch.
  observer = new MutationObserver(() => {
    window.clearTimeout(initI18n._t);
    initI18n._t = window.setTimeout(() => applyI18n(document.body), 40);
  });
  observer.observe(document.body, { childList: true, subtree: true });
  applyI18n(document.body);
}

/* ---------------------------------------------------------------
   2. THEME
   --------------------------------------------------------------- */
export function getTheme() {
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
}

export function setTheme(next) {
  const value = next === 'light' ? 'light' : 'dark';
  document.documentElement.dataset.theme = value;
  try { localStorage.setItem('cwintel:theme', value); } catch { /* ignore */ }
  for (const b of document.querySelectorAll('[data-theme-set]')) {
    const on = b.dataset.themeSet === value;
    b.classList.toggle('on', on);
    b.setAttribute('aria-pressed', on ? 'true' : 'false');
  }
  window.dispatchEvent(new CustomEvent('cwintel:theme', { detail: { theme: value } }));
}

export function onThemeChange(fn) {
  window.addEventListener('cwintel:theme', (event) => fn(event.detail.theme));
}

export function initTheme() {
  let saved = null;
  try { saved = localStorage.getItem('cwintel:theme'); } catch { /* ignore */ }
  // Không có lựa chọn đã lưu thì theo cài đặt hệ thống — không áp đặt.
  const system = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches
    ? 'light' : 'dark';
  setTheme(saved === 'light' || saved === 'dark' ? saved : system);
  for (const b of document.querySelectorAll('[data-theme-set]')) {
    b.addEventListener('click', () => setTheme(b.dataset.themeSet));
  }
}

/* ---------------------------------------------------------------
   3. ĐỒNG HỒ — mỗi giây đọc lại Date.now(), không cộng dồn biến đếm
   --------------------------------------------------------------- */
export const TZ = 'Asia/Ho_Chi_Minh';

// Mốc phiên tính bằng phút trong ngày (giờ VN), khớp quy ước HOSE/HNX.
const BOUNDARIES = [
  [540, 'ato'], [555, 'open'], [690, 'break'], [780, 'open'],
  [870, 'atc'], [885, 'post'], [900, 'closed'],
];

const SESSION_LABEL = {
  holiday: ['Nghỉ lễ', 'Market holiday'],
  weekend: ['Cuối tuần', 'Weekend'],
  pre: ['Trước giờ mở cửa', 'Before the open'],
  ato: ['Phiên ATO', 'ATO session'],
  open: ['Khớp lệnh liên tục', 'Continuous trading'],
  break: ['Nghỉ trưa', 'Lunch break'],
  atc: ['Phiên ATC', 'ATC session'],
  post: ['Sau giờ khớp lệnh', 'After trading'],
  closed: ['Đã đóng cửa', 'Closed'],
};

const WEEKDAY_VI = ['Chủ Nhật', 'Thứ Hai', 'Thứ Ba', 'Thứ Tư', 'Thứ Năm', 'Thứ Sáu', 'Thứ Bảy'];

const PARTS_FMT = new Intl.DateTimeFormat('en-GB', {
  timeZone: TZ, year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', weekday: 'short', hour12: false,
});
const WEEKDAY_INDEX = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };

function sessionKey(minutes, isWeekend, isHoliday) {
  if (isHoliday) return 'holiday';
  if (isWeekend) return 'weekend';
  for (let i = BOUNDARIES.length - 1; i >= 0; i -= 1) {
    if (minutes >= BOUNDARIES[i][0]) return BOUNDARIES[i][1];
  }
  return 'pre';
}

export function clockParts(now = Date.now(), holidays = null) {
  const date = now instanceof Date ? now : new Date(now);
  const parts = {};
  for (const p of PARTS_FMT.formatToParts(date)) parts[p.type] = p.value;
  const hour = Number(parts.hour) % 24;          // vài ICU trả '24' cho nửa đêm
  const minute = Number(parts.minute);
  const second = Number(parts.second);
  const weekday = WEEKDAY_INDEX[parts.weekday] ?? 0;
  const minutes = hour * 60 + minute;
  const iso = `${parts.year}-${parts.month}-${parts.day}`;
  const isWeekend = weekday === 0 || weekday === 6;
  const isHoliday = holidays ? holidays.has(iso) : false;
  return {
    hour, minute, second, minutes, weekday, isWeekend, isHoliday, iso,
    day: Number(parts.day), month: Number(parts.month), year: Number(parts.year),
    session: sessionKey(minutes, isWeekend, isHoliday),
    hhmmss: `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
      + `:${String(second).padStart(2, '0')}`,
  };
}

export function sessionLabel(session, language = 'vi') {
  const pair = SESSION_LABEL[session] || SESSION_LABEL.closed;
  return language === 'en' ? pair[1] : pair[0];
}

export function dateLabel(parts, language = 'vi') {
  const dd = String(parts.day).padStart(2, '0');
  const mm = String(parts.month).padStart(2, '0');
  if (language === 'en') {
    const en = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][parts.weekday] || '';
    return `${en} ${dd}/${mm}/${parts.year}`;
  }
  return `${WEEKDAY_VI[parts.weekday] || ''} · ${dd}/${mm}/${parts.year}`;
}

export function minutesToNextBoundary(parts) {
  if (parts.isWeekend || parts.isHoliday) return null;
  for (const [start] of BOUNDARIES) if (parts.minutes < start) return start - parts.minutes;
  return null;
}

/**
 * Chạy đồng hồ mỗi giây. `holidays` là Set các ngày nghỉ (YYYY-MM-DD) — có thì trạng thái
 * là "Nghỉ lễ" chứ không phải "đang khớp lệnh".
 */
export function startClock(opts = {}) {
  const langOf = typeof opts.lang === 'function' ? opts.lang : () => opts.lang || 'vi';
  const nowOf = typeof opts.now === 'function' ? opts.now : () => Date.now();
  const timeEl = document.getElementById('clock-time');
  const dateEl = document.getElementById('clock-date');
  const sessionEl = document.getElementById('clock-session');
  const fetchedEl = document.getElementById('clock-fetched');
  if (!timeEl) return { stop: () => {} };

  const tick = () => {
    const parts = clockParts(nowOf(), opts.holidays || null);
    timeEl.textContent = parts.hhmmss;
    timeEl.setAttribute('datetime', `${parts.iso}T${parts.hhmmss}+07:00`);
    if (dateEl) dateEl.textContent = dateLabel(parts, langOf());
    if (sessionEl) sessionEl.textContent = sessionLabel(parts.session, langOf());
    const host = document.getElementById('market-clock');
    if (host) host.dataset.session = parts.session;
    const next = minutesToNextBoundary(parts);
    const tz = langOf() === 'en' ? 'Vietnam time' : 'giờ Việt Nam';
    const label = sessionLabel(parts.session, langOf());
    const tip = next === null
      ? `${label} · ${parts.hhmmss} ${tz}`
      : (langOf() === 'en'
        ? `${label} · ${parts.hhmmss} ${tz} · ${next} min to the next session mark`
        : `${label} · ${parts.hhmmss} ${tz} · còn ${next} phút tới mốc phiên kế tiếp`);
    timeEl.setAttribute('title', tip);
    if (host) host.setAttribute('aria-label', tip);
    return parts;
  };

  tick();
  const timer = setInterval(tick, 1000);
  // Tab bị treo / máy sleep thì nhịp có thể trôi: đọc lại ngay khi quay lại foreground.
  document.addEventListener('visibilitychange', () => { if (!document.hidden) tick(); });
  window.addEventListener('pageshow', tick);
  window.addEventListener('focus', tick);
  window.addEventListener('cwintel:lang', tick);
  return { stop: () => clearInterval(timer), tick };
}

/* ---------------------------------------------------------------
   4. ĐỊNH DẠNG SỐ — dùng chung, không làm tròn quá mức
   --------------------------------------------------------------- */
export function num(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return Number(value).toLocaleString('vi-VN', {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  });
}

export function money(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  const v = Number(value);
  if (Math.abs(v) >= 1e9) return `${(v / 1e9).toFixed(2)} ${bi('tỷ', 'bn')}`;
  if (Math.abs(v) >= 1e6) return `${(v / 1e6).toFixed(1)} ${bi('tr', 'mn')}`;
  return num(v);
}

export function pct(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—';
  return `${Number(value).toFixed(digits)}%`;
}

export function esc(value) {
  return String(value ?? '—').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

/** Ô "—" kèm lý do khi thiếu số liệu, để không ai đọc nhầm thành 0. */
export function dash(title) {
  return `<span class="na" title="${esc(title || bi('Không có dữ liệu', 'No data'))}">—</span>`;
}

export function valueOr(value, formatter, reason) {
  if (value === null || value === undefined || (typeof value === 'number' && Number.isNaN(value))) {
    return dash(reason);
  }
  return formatter(value);
}
