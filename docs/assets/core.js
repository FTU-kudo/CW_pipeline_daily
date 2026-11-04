/* =========================================================
   CW Intelligence — core: state, data, format, UI, charts, router
   Không phụ thuộc thư viện ngoài (chart tự vẽ bằng canvas).
   ========================================================= */

import { getLang, applyI18n } from './i18n.js';

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

export function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else if (k === 'text') node.textContent = v;
    else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
    else if (k === 'dataset') Object.assign(node.dataset, v);
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c === null || c === undefined || c === false) continue;
    node.appendChild(typeof c === 'string' || typeof c === 'number' ? document.createTextNode(String(c)) : c);
  }
  return node;
}

export function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

/* -------------------------- FORMAT -------------------------- */
const locale = () => (getLang() === 'en' ? 'en-US' : 'vi-VN');
export const fmt = {
  n(v, d = 0) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    return new Intl.NumberFormat(locale(), { minimumFractionDigits: d, maximumFractionDigits: d }).format(v);
  },
  /** Số + đơn vị đã bản địa hoá (dùng cho nhãn trục, tooltip). */
  unit(v, d = 1) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const en = getLang() === 'en';
    const a = Math.abs(v);
    if (a >= 1e9) return fmt.n(v / 1e9, d) + (en ? 'bn' : ' tỷ');
    if (a >= 1e6) return fmt.n(v / 1e6, d) + (en ? 'm' : ' tr');
    if (a >= 1e3) return fmt.n(v / 1e3, 0) + (en ? 'k' : ' ng');
    return fmt.n(v, 0);
  },
  px(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    if (v < 100) return fmt.n(v, 1);
    return fmt.n(v, 0);
  },
  pct(v, d = 1, sign = true) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const s = sign && v > 0 ? '+' : '';
    return s + fmt.n(v, d) + '%';
  },
  vnd(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const a = Math.abs(v);
    const en = getLang() === 'en';
    if (a >= 1e12) return fmt.n(v / 1e12, 2) + (en ? ' tn' : ' nghìn tỷ');
    if (a >= 1e9) return fmt.n(v / 1e9, 2) + (en ? ' bn' : ' tỷ');
    if (a >= 1e6) return fmt.n(v / 1e6, 1) + (en ? ' m' : ' tr');
    if (a >= 1e3) return fmt.n(v / 1e3, 0) + (en ? ' k' : ' ng');
    return fmt.n(v, 0);
  },
  compact(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const a = Math.abs(v);
    if (a >= 1e9) return fmt.n(v / 1e9, 1) + 'B';
    if (a >= 1e6) return fmt.n(v / 1e6, 1) + 'M';
    if (a >= 1e3) return fmt.n(v / 1e3, 0) + 'K';
    return fmt.n(v, 0);
  },
  date(iso) {
    if (!iso) return '—';
    const s = String(iso);
    if (/^\d{2}\/\d{2}\/\d{4}$/.test(s)) return s;
    const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
    return m ? `${m[3]}/${m[2]}/${m[1]}` : s;
  },
  dte(v) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    if (v < 0) return getLang() === 'en' ? 'expired' : 'đáo hạn';
    return v + (getLang() === 'en' ? ' days' : ' ngày');
  },
  cls(v, invert = false) {
    if (v === null || v === undefined || Number.isNaN(v) || v === 0) return 'dim';
    const positive = invert ? v < 0 : v > 0;
    return positive ? 'up' : 'down';
  },
  rec(rec) {
    const en = getLang() === 'en';
    const map = en
      ? { STRONG_BUY: 'STRONG BUY', BUY: 'BUY', HOLD: 'WATCH', AVOID: 'AVOID', HIGH_RISK: 'HIGH RISK', NO_DATA: 'NO DATA' }
      : { STRONG_BUY: 'MUA MẠNH', BUY: 'MUA', HOLD: 'THEO DÕI', AVOID: 'TRÁNH', HIGH_RISK: 'RỦI RO CAO', NO_DATA: 'CHƯA ĐỦ DL' };
    return map[rec] || rec || '—';
  },
  issuer(code, name) {
    if (name) return name;
    return (code || '').toUpperCase();
  },
  score(v) { return v === null || v === undefined ? '—' : fmt.n(v, 1); },
};

/* -------------------------- STORAGE -------------------------- */
export const store = {
  get(key, fallback) {
    try {
      const raw = localStorage.getItem('cwintel:' + key);
      return raw ? JSON.parse(raw) : fallback;
    } catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem('cwintel:' + key, JSON.stringify(value)); } catch { /* quota */ }
  },
  del(key) {
    try { localStorage.removeItem('cwintel:' + key); } catch { /* noop */ }
  },
};

/* -------------------------- DATA -------------------------- */
const cache = new Map();
export async function loadJSON(path) {
  if (cache.has(path)) return cache.get(path);
  const p = fetch(path, { cache: 'no-cache' }).then(async (res) => {
    if (!res.ok) throw new Error(`Không tải được ${path} (HTTP ${res.status})`);
    return res.json();
  });
  cache.set(path, p);
  return p;
}

export const data = {
  meta: null, market: null, screener: null, recommendations: null,
  underlyings: null, quality: null, methodology: null, backtest: null, liquidity: null,
  series: new Map(),
  async init(onProgress = () => {}) {
    const steps = [
      ['meta', 'meta.json'],
      ['market', 'market.json'],
      ['screener', 'screener.json'],
      ['recommendations', 'recommendations.json'],
      ['underlyings', 'underlyings.json'],
      ['quality', 'quality.json'],
      ['methodology', 'methodology.json'],
      ['liquidity', 'liquidity.json'],
    ];
    let i = 0;
    for (const [key, file] of steps) {
      onProgress(++i / (steps.length + 1), key);
      this[key] = await loadJSON('data/' + file);
    }
    onProgress(1, 'done');
  },
  async backtestData() {
    if (!this.backtest) this.backtest = await loadJSON('data/backtest.json');
    return this.backtest;
  },
  async cwSeries(ticker) {
    if (!ticker) return null;
    if (this.series.has(ticker)) return this.series.get(ticker);
    const allowed = new Set(this.meta?.seriesTickers || []);
    if (allowed.size && !allowed.has(ticker)) { this.series.set(ticker, null); return null; }
    try {
      const s = await loadJSON(`data/series/cw/${ticker}.json`);
      this.series.set(ticker, s);
      return s;
    } catch { this.series.set(ticker, null); return null; }
  },
  async undSeries(sym) {
    const key = 'und:' + sym;
    if (this.series.has(key)) return this.series.get(key);
    try {
      const s = await loadJSON(`data/series/und/${sym}.json`);
      this.series.set(key, s);
      return s;
    } catch { this.series.set(key, null); return null; }
  },
  activeRows() { return this.screener?.active || []; },
  allRows() { return [...(this.screener?.active || []), ...(this.screener?.expired || [])]; },
  row(ticker) { return this.allRows().find((r) => r.t === ticker) || null; },
  card(ticker) { return (this.recommendations?.cards || []).find((c) => c.ticker === ticker) || null; },
};

/* -------------------------- THEME -------------------------- */
const THEME_ORDER = ['light', 'dark', 'auto'];
const THEME_LABEL = {
  vi: { light: 'Sáng', dark: 'Tối', auto: 'Theo hệ thống' },
  en: { light: 'Light', dark: 'Dark', auto: 'System' },
};
const THEME_ICON = { light: '☀', dark: '◐', auto: '◑' };

export function currentThemeMode() {
  return store.get('themeMode', null) || (store.get('theme', null) === 'light' ? 'light' : 'dark');
}

function resolvedTheme(mode) {
  if (mode === 'auto') {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }
  return mode === 'light' ? 'light' : 'dark';
}

function paintTheme() {
  const mode = currentThemeMode();
  const theme = resolvedTheme(mode);
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.themeMode = mode;
  const btn = $('#btn-theme');
  if (btn) {
    const lang = getLang() === 'en' ? 'en' : 'vi';
    btn.textContent = THEME_ICON[mode];
    btn.title = lang === 'en'
      ? `Theme: ${THEME_LABEL.en[mode]} (click to change)`
      : `Giao diện: ${THEME_LABEL.vi[mode]} (bấm để đổi)`;
    btn.setAttribute('aria-label', btn.title);
    btn.dataset.mode = mode;
  }
  redrawAllCharts();
}

export function initTheme() {
  paintTheme();
  const btn = $('#btn-theme');
  if (btn && !btn.dataset.bound) {
    btn.dataset.bound = '1';
    btn.addEventListener('click', () => {
      const mode = currentThemeMode();
      const next = THEME_ORDER[(THEME_ORDER.indexOf(mode) + 1) % THEME_ORDER.length];
      store.set('themeMode', next);
      store.set('theme', resolvedTheme(next));
      paintTheme();
    });
  }
  if (window.matchMedia && !initTheme._bound) {
    initTheme._bound = true;
    window.matchMedia('(prefers-color-scheme: light)').addEventListener?.('change', () => {
      if (currentThemeMode() === 'auto') paintTheme();
    });
  }
  window.addEventListener('cwintel:lang', paintTheme);
}

const redrawHooks = new Set();
export function onThemeChange(fn) { redrawHooks.add(fn); }
export function redrawAllCharts() {
  redrawHooks.forEach((fn) => { try { fn(); } catch { /* noop */ } });
  for (const canvas of chartRegistry) {
    if (!canvas.isConnected) { chartRegistry.delete(canvas); continue; }
    try { canvas._redraw?.(); } catch { /* noop */ }
  }
}

/* -------------------------- UI HELPERS -------------------------- */
let toastTimer = null;
export function toast(msg, ms = 2200) {
  const t = $('#toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), ms);
}

export function badge(rec) {
  return el('span', { class: `badge ${rec || 'NO_DATA'}`, text: fmt.rec(rec) });
}

export function scoreCell(score) {
  if (score === null || score === undefined) return el('span', { class: 'muted', text: '—' });
  const color = score >= 80 ? 'var(--up)' : score >= 65 ? 'var(--accent)' : score >= 45 ? 'var(--warn)' : 'var(--down)';
  return el('span', { class: 'score-pill', title: `CW Score ${score}/100 (tương đối trong vũ trụ)` }, [
    el('span', { style: `color:${color}`, text: fmt.n(score, 1) }),
    el('span', { class: 'score-bar', style: 'margin-left:6px' }, [
      el('i', { style: `width:${Math.max(2, Math.min(100, score))}%;background:${color}` }),
    ]),
  ]);
}

export function openDrawer(node) {
  const d = $('#drawer');
  const body = $('#drawer-body');
  body.innerHTML = '';
  body.appendChild(node);
  d.classList.remove('hidden');
  d.querySelector('.drawer-backdrop').onclick = closeDrawer;
}
export function closeDrawer() { $('#drawer')?.classList.add('hidden'); }

export function table({ columns, rows, onRowClick, compact = false, stickyFirst = false, empty = 'Không có dữ liệu' }) {
  const wrap = el('div', { class: 'table-wrap' });
  if (!rows || !rows.length) {
    wrap.appendChild(el('div', { class: 'empty', text: empty }));
    return wrap;
  }
  let sortKey = null;
  let sortDir = -1;
  const tbl = el('table', { class: 'tbl' + (compact ? ' compact' : '') + (stickyFirst ? ' sticky-first' : '') });
  const thead = el('thead');
  const headRow = el('tr');
  const tbody = el('tbody');

  const renderBody = () => {
    let list = rows.slice();
    if (sortKey) {
      const col = columns.find((c) => c.key === sortKey);
      list.sort((a, b) => {
        const va = col?.sortValue ? col.sortValue(a) : a[sortKey];
        const vb = col?.sortValue ? col.sortValue(b) : b[sortKey];
        if (va === null || va === undefined) return 1;
        if (vb === null || vb === undefined) return -1;
        if (typeof va === 'string' || typeof vb === 'string') {
          return String(va).localeCompare(String(vb), 'vi') * sortDir;
        }
        return (va - vb) * sortDir;
      });
    }
    tbody.innerHTML = '';
    const frag = document.createDocumentFragment();
    for (const row of list) {
      const tr = el('tr', { class: onRowClick ? 'clickable' : '' });
      for (const col of columns) {
        const td = el('td', { class: (col.align === 'right' ? 'num ' : '') + (col.className || '') });
        const value = col.render ? col.render(row) : row[col.key];
        if (value instanceof Node) td.appendChild(value);
        else td.textContent = value ?? '—';
        tr.appendChild(td);
      }
      if (onRowClick) tr.addEventListener('click', (e) => {
        if (e.target.closest('button, a, input, select')) return;
        onRowClick(row);
      });
      frag.appendChild(tr);
    }
    tbody.appendChild(frag);
  };

  for (const col of columns) {
    const th = el('th', {
      class: (col.align === 'right' ? 'num ' : '') + (col.sortable === false ? '' : ''),
      style: col.width ? `min-width:${col.width}px` : null,
      text: col.title,
      title: col.hint || '',
    });
    if (col.sortable !== false) {
      th.addEventListener('click', () => {
        if (sortKey === col.key) sortDir *= -1; else { sortKey = col.key; sortDir = -1; }
        Array.from(headRow.children).forEach((n) => n.classList.remove('sorted'));
        th.classList.add('sorted');
        th.querySelector('.arrow')?.remove();
        th.appendChild(el('span', { class: 'arrow', text: sortDir < 0 ? '▼' : '▲' }));
        renderBody();
      });
    }
    headRow.appendChild(th);
  }
  thead.appendChild(headRow);
  tbl.appendChild(thead);
  tbl.appendChild(tbody);
  wrap.appendChild(tbl);
  renderBody();
  return wrap;
}

/* -------------------------- CANVAS CHARTS -------------------------- */
function setupCanvas(canvas, height) {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  const w = Math.max(80, rect.width || canvas.parentElement?.clientWidth || 400);
  const h = height || rect.height || 200;
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  canvas.style.height = h + 'px';
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w, h };
}

function css(name, fallback = '#888') {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function niceTicks(min, max, count = 5) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return [];
  if (min === max) { min -= 1; max += 1; }
  const span = max - min;
  const step0 = span / count;
  const mag = Math.pow(10, Math.floor(Math.log10(step0)));
  const norm = step0 / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10) * mag;
  const start = Math.ceil(min / step) * step;
  const ticks = [];
  for (let v = start; v <= max + 1e-9; v += step) ticks.push(+v.toFixed(10));
  return ticks;
}

function tooltipFor(canvas) {
  const parent = canvas.parentElement;
  parent.style.position = 'relative';
  let tip = parent.querySelector('.chart-tip');
  if (!tip) {
    tip = el('div', {
      class: 'chart-tip',
      style: 'position:absolute;pointer-events:none;background:var(--surface-3);border:1px solid var(--border-2);' +
        'border-radius:6px;padding:5px 8px;font-size:10.5px;font-family:var(--font-mono);color:var(--text);' +
        'box-shadow:var(--shadow);display:none;z-index:9;white-space:nowrap',
    });
    parent.appendChild(tip);
  }
  return tip;
}
/* ---- registry: mọi chart tự vẽ lại khi đổi theme / đổi kích thước ---- */
const chartRegistry = new Set();
let resizeBound = false;

function registerChart(canvas, draw) {
  canvas._redraw = draw;
  chartRegistry.add(canvas);
  if (!resizeBound && typeof ResizeObserver !== 'undefined') {
    resizeBound = true;
    const ro = new ResizeObserver(() => {
      window.clearTimeout(registerChart._t);
      registerChart._t = window.setTimeout(() => {
        for (const c of chartRegistry) {
          if (!c.isConnected) { chartRegistry.delete(c); continue; }
          if (c.offsetParent === null) continue;
          try { c._redraw?.(); } catch { /* noop */ }
        }
      }, 80);
    });
    const watch = () => {
      for (const c of chartRegistry) {
        if (!c._watched) { ro.observe(c.parentElement || c); c._watched = true; }
      }
    };
    registerChart._watch = watch;
    window.addEventListener('resize', () => registerChart._t2 = window.clearTimeout(registerChart._t2) || window.setTimeout(() => {
      for (const c of chartRegistry) if (c.isConnected && c._redraw) { try { c._redraw(); } catch { /* noop */ } }
    }, 120));
  }
  if (typeof ResizeObserver !== 'undefined' && registerChart._watch) registerChart._watch();
}

/* ---- legend: hiển thị tên series + màu, đọc được cả khi in ---- */
function ensureLegend(canvas, series) {
  const parent = canvas.parentElement;
  if (!parent) return;
  let box = parent.querySelector(':scope > .chart-legend');
  if (!series.length) { box?.remove(); return; }
  if (!box) {
    box = document.createElement('div');
    box.className = 'chart-legend';
    parent.insertBefore(box, canvas);
  }
  const sig = series.map((s) => `${s.name || ''}|${s.color || ''}`).join(';');
  if (box.dataset.sig === sig) return;
  box.dataset.sig = sig;
  box.innerHTML = '';
  for (const s of series) {
    const item = document.createElement('span');
    item.className = 'chart-legend-item';
    const sw = document.createElement('i');
    sw.style.background = s.color || css('--accent');
    item.appendChild(sw);
    item.appendChild(document.createTextNode(s.name || ''));
    box.appendChild(item);
  }
}

/* ---- crosshair: canvas phủ trong suốt, vẽ đường dóng + điểm ---- */
function ensureOverlay(canvas) {
  const parent = canvas.parentElement;
  if (!parent) return null;
  let ov = parent.querySelector(':scope > canvas.chart-overlay');
  if (!ov) {
    ov = document.createElement('canvas');
    ov.className = 'chart-overlay';
    ov.style.position = 'absolute';
    ov.style.left = '0';
    ov.style.top = '0';
    ov.style.pointerEvents = 'none';
    parent.appendChild(ov);
    if (getComputedStyle(parent).position === 'static') parent.style.position = 'relative';
  }
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  ov.width = Math.round(rect.width * dpr);
  ov.height = Math.round(canvas.getBoundingClientRect().height * dpr);
  ov.style.width = rect.width + 'px';
  ov.style.height = canvas.getBoundingClientRect().height + 'px';
  const ctx = ov.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, w: rect.width, h: canvas.getBoundingClientRect().height };
}

export function drawLine(canvas, opts) {
  const height = opts.height || 200;
  const { ctx, w, h } = setupCanvas(canvas, height);
  registerChart(canvas, () => drawLine(canvas, opts));
  const series = (opts.series || []).filter((s) => s.values && s.values.length);
  ensureLegend(canvas, series);
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', opts.title
    || (series.map((s) => s.name).filter(Boolean).join(', ') || 'chart'));
  const padR = 10; const padT = 12; const padB = 24;
  const all = series.flatMap((s) => s.values).filter((v) => Number.isFinite(v));
  if (!all.length) {
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = css('--text-3');
    ctx.font = '11px ' + css('--font-mono', 'monospace');
    ctx.fillText('—', 12, h / 2);
    return;
  }
  const zero = opts.zeroLine ? 0 : null;
  let min = Math.min(...all, ...(zero !== null ? [zero] : []));
  let max = Math.max(...all, ...(zero !== null ? [zero] : []));
  if (opts.yMin !== undefined) min = opts.yMin;
  if (opts.yMax !== undefined) max = opts.yMax;
  const padY = (max - min) * 0.08 || 1;
  min -= padY; max += padY;
  const n = Math.max(...series.map((s) => s.values.length));
  const ticks = niceTicks(min, max, 4);
  const yFmt = (v) => (opts.yFormat ? opts.yFormat(v) : fmt.n(v, 0));
  ctx.font = '10px ' + css('--font-mono', 'monospace');
  const labelW = Math.max(...ticks.map((t) => ctx.measureText(yFmt(t)).width), 18);
  const padL = Math.max(opts.padL ?? 0, labelW + 12);
  const iw = w - padL - padR; const ih = h - padT - padB;
  const x = (i) => padL + (n <= 1 ? iw / 2 : (i / (n - 1)) * iw);
  const y = (v) => padT + ih - ((v - min) / (max - min)) * ih;

  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = css('--grid'); ctx.lineWidth = 1;
  ctx.fillStyle = css('--text-3');
  for (const t of ticks) {
    const yy = Math.round(y(t)) + 0.5;
    ctx.beginPath(); ctx.moveTo(padL, yy); ctx.lineTo(w - padR, yy); ctx.stroke();
    ctx.fillText(yFmt(t), 4, yy + 3);
  }
  if (zero !== null) {
    ctx.strokeStyle = css('--border-2');
    ctx.beginPath(); ctx.moveTo(padL, y(0)); ctx.lineTo(w - padR, y(0)); ctx.stroke();
  }
  const labels = opts.labels || [];
  const steps = Math.min(w < 420 ? 3 : 6, n);
  for (let k = 0; k < steps; k++) {
    const i = Math.round((k / Math.max(1, steps - 1)) * (n - 1));
    ctx.fillStyle = css('--text-3');
    const txt = labels[i] || '';
    const tw = ctx.measureText(txt).width;
    ctx.fillText(txt, Math.min(w - padR - tw, Math.max(padL, x(i) - tw / 2)), h - 6);
  }
  for (const s of series) {
    if (s.fill) {
      const grad = ctx.createLinearGradient(0, padT, 0, padT + ih);
      grad.addColorStop(0, (s.color || css('--accent')) + (s.fill === true ? '55' : '30'));
      grad.addColorStop(1, 'transparent');
      ctx.beginPath();
      s.values.forEach((v, i) => { if (!Number.isFinite(v)) return; const px = x(i), py = y(v); i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py); });
      ctx.lineTo(x(s.values.length - 1), padT + ih); ctx.lineTo(x(0), padT + ih); ctx.closePath();
      ctx.fillStyle = grad; ctx.fill();
    }
    ctx.beginPath();
    ctx.strokeStyle = s.color || css('--accent');
    ctx.lineWidth = s.width || 1.7;
    ctx.lineJoin = 'round';
    let started = false;
    s.values.forEach((v, i) => {
      if (!Number.isFinite(v)) { started = false; return; }
      const px = x(i), py = y(v);
      if (!started) { ctx.moveTo(px, py); started = true; } else ctx.lineTo(px, py);
    });
    ctx.stroke();
  }
  if (opts.marker) {
    const { index, color } = opts.marker;
    if (index >= 0 && index < n) {
      ctx.strokeStyle = color || css('--warn');
      ctx.setLineDash([3, 3]);
      ctx.beginPath(); ctx.moveTo(x(index), padT); ctx.lineTo(x(index), padT + ih); ctx.stroke();
      ctx.setLineDash([]);
    }
  }

  const tip = tooltipFor(canvas);
  canvas.onmousemove = (ev) => {
    const rect = canvas.getBoundingClientRect();
    const mx = ev.clientX - rect.left;
    if (mx < padL || mx > w - padR) { tip.style.display = 'none'; ensureOverlay(canvas)?.ctx.clearRect(0, 0, w, h); return; }
    const i = Math.max(0, Math.min(n - 1, Math.round(((mx - padL) / iw) * (n - 1))));
    const rows = series.map((s) => {
      const v = s.values[i];
      const val = v === undefined || v === null || !Number.isFinite(v) ? '—' : (opts.yFormat ? opts.yFormat(v) : fmt.n(v, 2));
      return `<span class="tip-row"><i style="background:${s.color || css('--accent')}"></i>${esc(s.name || '')}<b>${esc(val)}</b></span>`;
    });
    tip.innerHTML = `<b class="tip-head">${esc(labels[i] || '')}</b>${rows.join('')}`;
    tip.style.display = 'block';
    const left = Math.min(w - tip.offsetWidth - 6, Math.max(6, mx + 12));
    tip.style.left = left + 'px';
    tip.style.top = '6px';
    // crosshair
    const ov = ensureOverlay(canvas);
    if (ov) {
      ov.ctx.clearRect(0, 0, ov.w, ov.h);
      ov.ctx.strokeStyle = css('--border-2');
      ov.ctx.lineWidth = 1;
      const px = Math.round(x(i)) + 0.5;
      ov.ctx.beginPath(); ov.ctx.moveTo(px, padT); ov.ctx.lineTo(px, padT + ih); ov.ctx.stroke();
      for (const s of series) {
        const v = s.values[i];
        if (!Number.isFinite(v)) continue;
        ov.ctx.beginPath();
        ov.ctx.arc(x(i), y(v), 3, 0, Math.PI * 2);
        ov.ctx.fillStyle = s.color || css('--accent');
        ov.ctx.fill();
        ov.ctx.strokeStyle = css('--surface');
        ov.ctx.lineWidth = 1.5;
        ov.ctx.stroke();
      }
    }
  };
  canvas.onmouseleave = () => {
    tip.style.display = 'none';
    const ov = ensureOverlay(canvas);
    if (ov) ov.ctx.clearRect(0, 0, ov.w, ov.h);
  };
}
export function drawBars(canvas, opts) {
  const { ctx, w, h } = setupCanvas(canvas, opts.height || 180);
  registerChart(canvas, () => drawBars(canvas, opts));
  const padL = opts.padL ?? 40; const padR = 8; const padT = 10; const padB = 26;
  const iw = w - padL - padR; const ih = h - padT - padB;
  const values = opts.values || [];
  const labels = opts.labels || [];
  if (!values.length) return;
  const maxV = Math.max(1, ...values.map((v) => Math.abs(v)));
  const min = Math.min(0, ...values);
  const max = Math.max(0, ...values);
  const padY = (max - min) * 0.1 || 1;
  const yMin = min - (min < 0 ? padY : 0); const yMax = max + (max > 0 ? padY : 0);
  const y = (v) => padT + ih - ((v - yMin) / (yMax - yMin)) * ih;
  ctx.clearRect(0, 0, w, h);
  ctx.strokeStyle = css('--grid'); ctx.fillStyle = css('--text-3'); ctx.font = '10px monospace';
  for (const t of niceTicks(yMin, yMax, 3)) {
    ctx.beginPath(); ctx.moveTo(padL, y(t)); ctx.lineTo(w - padR, y(t)); ctx.stroke();
    ctx.fillText(opts.yFormat ? opts.yFormat(t) : fmt.n(t, 0), 3, y(t) + 3);
  }
  const bw = iw / values.length;
  values.forEach((v, i) => {
    const x0 = padL + i * bw + Math.min(3, bw * 0.15);
    const x1 = padL + (i + 1) * bw - Math.min(3, bw * 0.15);
    const y0 = y(Math.max(0, v)); const y1 = y(Math.min(0, v));
    ctx.fillStyle = opts.colors?.[i] || (v >= 0 ? css('--up') : css('--down'));
    ctx.fillRect(x0, Math.min(y0, y1), Math.max(1, x1 - x0), Math.max(1, Math.abs(y1 - y0)));
    ctx.fillStyle = css('--text-3');
    const label = labels[i] || '';
    const tw = ctx.measureText(label).width;
    ctx.fillText(label, Math.max(padL, Math.min(w - tw - 2, (x0 + x1) / 2 - tw / 2)), h - 8);
  });
  const tip = tooltipFor(canvas);
  canvas.onmousemove = (ev) => {
    const rect = canvas.getBoundingClientRect();
    const i = Math.floor((ev.clientX - rect.left - padL) / bw);
    if (i < 0 || i >= values.length) { tip.style.display = 'none'; return; }
    tip.innerHTML = `<b>${esc(labels[i])}</b><br>${opts.tipFormat ? opts.tipFormat(values[i], i) : fmt.n(values[i], 2)}`;
    tip.style.display = 'block';
    tip.style.left = Math.min(w - 120, Math.max(0, ev.clientX - rect.left + 10)) + 'px';
    tip.style.top = '6px';
  };
  canvas.onmouseleave = () => { tip.style.display = 'none'; };
}

export function drawCandles(canvas, payload, opts = {}) {
  registerChart(canvas, () => drawCandles(canvas, payload, opts));
  const height = opts.height || 320;
  const { ctx, w, h } = setupCanvas(canvas, height);
  const { o, h: hi, l, c, v, dates, ma20, ma50 } = payload;
  if (!c || !c.length) {
    ctx.fillStyle = css('--text-3'); ctx.font = '11px sans-serif';
    ctx.fillText('Không có dữ liệu giá', 20, h / 2);
    return;
  }
  const showVol = opts.showVolume !== false;
  const volH = showVol ? Math.round(h * 0.2) : 0;
  const padL = 6; const padR = 52; const padT = 8;
  const priceH = h - padT - volH - 18;
  const iw = w - padL - padR;
  const n = c.length;
  const lows = l.filter(Number.isFinite); const highs = hi.filter(Number.isFinite);
  const maVals = [...(ma20 || []), ...(ma50 || [])].filter(Number.isFinite);
  let min = Math.min(...lows, ...(maVals.length ? maVals : []));
  let max = Math.max(...highs, ...(maVals.length ? maVals : []));
  const pad = (max - min) * 0.06 || 1; min -= pad; max += pad;
  const y = (val) => padT + priceH - ((val - min) / (max - min)) * priceH;
  const cw = iw / n;
  const bodyW = Math.max(1, Math.min(11, cw * 0.66));
  ctx.clearRect(0, 0, w, h);
  // grid + right labels
  ctx.strokeStyle = css('--grid'); ctx.fillStyle = css('--text-3'); ctx.font = '10px monospace';
  for (const t of niceTicks(min, max, 4)) {
    const yy = y(t);
    ctx.beginPath(); ctx.moveTo(padL, yy); ctx.lineTo(w - padR, yy); ctx.stroke();
    ctx.fillText(fmt.px(t), w - padR + 5, yy + 3);
  }
  // volume
  if (showVol) {
    const vMax = Math.max(...v.filter(Number.isFinite), 1);
    const vTop = padT + priceH + 10;
    const vh = volH - 4;
    for (let i = 0; i < n; i++) {
      const hgt = (v[i] / vMax) * vh;
      const x = padL + i * cw + (cw - bodyW) / 2;
      ctx.fillStyle = c[i] >= o[i] ? css('--up') + '66' : css('--down') + '66';
      ctx.fillRect(x, vTop + vh - hgt, bodyW, hgt);
    }
  }
  // candles
  for (let i = 0; i < n; i++) {
    const x = padL + i * cw + cw / 2;
    const up = c[i] >= o[i];
    ctx.strokeStyle = up ? css('--up') : css('--down');
    ctx.fillStyle = up ? css('--up') : css('--down');
    ctx.beginPath(); ctx.moveTo(x, y(hi[i])); ctx.lineTo(x, y(l[i])); ctx.stroke();
    const y0 = y(Math.max(o[i], c[i])); const y1 = y(Math.min(o[i], c[i]));
    ctx.fillRect(x - bodyW / 2, y0, bodyW, Math.max(1, y1 - y0));
  }
  // MAs
  const drawMA = (arr, color) => {
    if (!arr || !arr.length) return;
    ctx.beginPath(); ctx.strokeStyle = color; ctx.lineWidth = 1.2;
    let started = false;
    for (let i = 0; i < n; i++) {
      const val = arr[i];
      if (!Number.isFinite(val)) { started = false; continue; }
      const x = padL + i * cw + cw / 2;
      if (!started) { ctx.moveTo(x, y(val)); started = true; } else ctx.lineTo(x, y(val));
    }
    ctx.stroke();
  };
  drawMA(ma20, css('--accent-2'));
  drawMA(ma50, css('--violet'));

  const tip = tooltipFor(canvas);
  canvas.onmousemove = (ev) => {
    const rect = canvas.getBoundingClientRect();
    const i = Math.floor((ev.clientX - rect.left - padL) / cw);
    if (i < 0 || i >= n) { tip.style.display = 'none'; return; }
    tip.innerHTML = `<b>${esc(dates[i])}</b><br>O ${fmt.px(o[i])} · H ${fmt.px(hi[i])}<br>L ${fmt.px(l[i])} · C ${fmt.px(c[i])}<br>KL ${fmt.compact(v[i])}`;
    tip.style.display = 'block';
    tip.style.left = Math.min(w - 120, Math.max(0, ev.clientX - rect.left + 12)) + 'px';
    tip.style.top = '8px';
  };
  canvas.onmouseleave = () => { tip.style.display = 'none'; };
}

export function drawSpark(canvas, values, color) {
  registerChart(canvas, () => drawSpark(canvas, values, color));
  const { ctx, w, h } = setupCanvas(canvas, canvas.clientHeight || 26);
  const vals = (values || []).filter(Number.isFinite);
  if (vals.length < 2) return;
  const min = Math.min(...vals); const max = Math.max(...vals);
  const pad = (max - min) * 0.15 || 1;
  const x = (i) => (i / (vals.length - 1)) * w;
  const y = (v) => h - ((v - (min - pad)) / ((max + pad) - (min - pad))) * h;
  ctx.clearRect(0, 0, w, h);
  ctx.beginPath(); ctx.strokeStyle = color || css('--accent'); ctx.lineWidth = 1.2;
  vals.forEach((v, i) => (i === 0 ? ctx.moveTo(x(i), y(v)) : ctx.lineTo(x(i), y(v))));
  ctx.stroke();
}

/* -------------------------- BLACK-SCHOLES (client) -------------------------- */
function ncdf(x) {
  // Abramowitz–Stegun 26.2.17, sai số < 1.5e-7 (đủ cho mô phỏng UI)
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const d = 0.3989422804014327 * Math.exp(-x * x / 2);
  const p = d * t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
  return x >= 0 ? 1 - p : p;
}

export function bsPrice({ S, K, T, r, sigma, ratio = 1, kind = 'call' }) {
  if (!(S > 0 && K > 0 && ratio > 0)) return 0;
  const intr = kind === 'put' ? Math.max(K - S, 0) / ratio : Math.max(S - K, 0) / ratio;
  if (!(T > 0) || !(sigma > 0)) return intr;
  const vt = sigma * Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / vt;
  const d2 = d1 - vt;
  const c = kind === 'put'
    ? K * Math.exp(-r * T) * ncdf(-d2) - S * ncdf(-d1)
    : S * ncdf(d1) - K * Math.exp(-r * T) * ncdf(d2);
  return Math.max(c / ratio, intr);
}

export function bsGreeks({ S, K, T, r, sigma, ratio = 1 }) {
  if (!(S > 0 && K > 0 && T > 0 && sigma > 0 && ratio > 0)) return null;
  const vt = sigma * Math.sqrt(T);
  const d1 = (Math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / vt;
  const d2 = d1 - vt;
  const pdf = Math.exp(-0.5 * d1 * d1) / Math.sqrt(2 * Math.PI);
  const disc = Math.exp(-r * T);
  return {
    delta: ncdf(d1) / ratio,
    gamma: pdf / (S * vt) / ratio,
    vega: (S * pdf * Math.sqrt(T)) / 100 / ratio,
    theta: (-(S * pdf * sigma) / (2 * Math.sqrt(T)) - r * K * disc * ncdf(d2)) / 365 / ratio,
  };
}

/* -------------------------- ROUTER -------------------------- */
const routes = new Map();
let currentRoute = null;
export function registerRoute(name, handler) { routes.set(name, handler); }

export function navigate(hash) {
  if (location.hash === hash) render();
  else location.hash = hash;
}

export async function render() {
  const hash = location.hash.replace(/^#\/?/, '') || 'overview';
  const pathOnly = hash.split('?')[0];
  const [name, param] = pathOnly.split('/');
  const handler = routes.get(name) || routes.get('overview');
  currentRoute = { name, param };
  const view = $('#view');
  if (!view) return;
  view.innerHTML = '';
  view.scrollTop = 0;
  window.scrollTo({ top: 0 });
  $$('#nav .nav-item').forEach((a) => a.classList.toggle('active', a.dataset.route === name));
  $('#sidebar')?.classList.remove('open');
  try {
    await handler(view, param);
    applyI18n(view);
    applyI18n(document.querySelector('.topbar') || document.body);
    // Nội dung render trễ (dữ liệu lazily load, legend của chart) được phủ nốt.
    const routeAt = currentRoute;
    window.setTimeout(() => {
      if (currentRoute === routeAt) applyI18n(view);
    }, 260);
  } catch (err) {
    console.error(err);
    view.appendChild(el('div', { class: 'empty', html: `<b>Không hiển thị được trang</b><br>${esc(err.message)}` }));
  }
}

export function startRouter() {
  window.addEventListener('hashchange', render);
  render();
}

/* -------------------------- SEARCH -------------------------- */
export function initSearch() {
  const input = $('#global-search');
  const box = $('#search-results');
  if (!input || !box) return;
  const rows = () => {
    const seen = new Map();
    for (const r of data.activeRows()) {
      seen.set(r.t, { type: 'CW', id: r.t, label: `${r.t} · ${r.u}`, meta: `${fmt.rec(r.rec)} · ${fmt.n(r.score, 1)} điểm` });
      if (!seen.has('u:' + r.u)) seen.set('u:' + r.u, { type: 'CP', id: r.u, label: r.u, meta: 'Cổ phiếu cơ sở' });
    }
    for (const c of data.recommendations?.cards || []) {
      const k = 'iss:' + c.issuer;
      if (!seen.has(k)) seen.set(k, { type: 'TCPH', id: c.issuer, label: c.issuer_name || c.issuer, meta: 'Tổ chức phát hành' });
    }
    return Array.from(seen.values());
  };
  let items = [];
  let sel = 0;
  const close = () => { box.classList.remove('on'); box.innerHTML = ''; };
  const paint = () => {
    box.innerHTML = '';
    items.slice(0, 12).forEach((it, i) => {
      const row = el('div', { class: 'search-row' + (i === sel ? ' sel' : '') }, [
        el('span', { class: 'badge tag', text: it.type }),
        el('span', { class: 't', text: it.label }),
        el('span', { class: 'spacer' }),
        el('span', { class: 'muted tiny', text: it.meta }),
      ]);
      row.onclick = () => {
        close();
        input.value = '';
        if (it.type === 'CW') navigate(`#/cw/${it.id}`);
        else navigate(`#/screener?u=${encodeURIComponent(it.id)}`);
      };
      box.appendChild(row);
    });
    box.classList.toggle('on', items.length > 0);
  };
  input.addEventListener('input', () => {
    const q = input.value.trim().toLowerCase();
    if (!q) { close(); return; }
    items = rows().filter((it) => it.label.toLowerCase().includes(q) || it.meta.toLowerCase().includes(q)).slice(0, 40);
    sel = 0;
    paint();
  });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { sel = Math.min(items.length - 1, sel + 1); paint(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { sel = Math.max(0, sel - 1); paint(); e.preventDefault(); }
    else if (e.key === 'Enter' && items[sel]) { items[sel] && box.children[sel]?.click(); }
    else if (e.key === 'Escape') { close(); input.blur(); }
  });
  document.addEventListener('click', (e) => { if (!e.target.closest('.search-wrap')) close(); });
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement !== input && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) {
      e.preventDefault(); input.focus();
    }
    if (e.key === 'Escape') closeDrawer();
  });
}

/* -------------------------- SMALL SHARED COMPONENTS -------------------------- */
export function pageHead(title, sub, actions = []) {
  return el('div', { class: 'page-head' }, [
    el('div', {}, [el('h1', { text: title }), sub ? el('div', { class: 'sub', html: sub }) : null]),
    actions.length ? el('div', { class: 'page-actions' }, actions) : null,
  ]);
}

export function kpiCard({ label, value, sub, delta, deltaClass, valueClass = '', id }) {
  return el('div', { class: 'kpi-card', id }, [
    el('div', { class: 'kpi-label', text: label }),
    el('div', { class: `kpi-value ${valueClass}` }, [el('span', { text: value })].concat(
      delta !== undefined && delta !== null ? [el('span', { class: `kpi-delta ${deltaClass || ''}`, style: 'margin-left:8px', text: delta })] : [])),
    sub ? el('div', { class: 'kpi-sub', html: sub }) : null,
  ]);
}

export function sectionHead(title, right = null) {
  return el('div', { class: 'section-head' }, [el('h2', { text: title }), right]);
}

export function downloadCsv(filename, rows, columns) {
  const cols = columns || Object.keys(rows[0] || {});
  const esc2 = (v) => {
    const s = v === null || v === undefined ? '' : String(v);
    return /[",\n;]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  };
  const csv = [cols.join(','), ...rows.map((r) => cols.map((c) => esc2(r[c])).join(','))].join('\n');
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
  const a = el('a', { href: URL.createObjectURL(blob), download: filename });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

/** Xuất Excel-compatible (SpreadsheetML 2003) — mở được bằng Excel/LibreOffice, không cần thư viện. */
export function downloadXls(filename, rows, columns) {
  const cols = columns || Object.keys(rows[0] || {}).map((k) => ({ key: k, title: k }));
  const escXml = (v) => String(v ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const cell = (v) => {
    const num = typeof v === 'number' && Number.isFinite(v);
    return `<Cell><Data ss:Type="${num ? 'Number' : 'String'}">${escXml(v)}</Data></Cell>`;
  };
  const header = '<Row>' + cols.map((c) => `<Cell ss:StyleID="h"><Data ss:Type="String">${escXml(c.title)}</Data></Cell>`).join('') + '</Row>';
  const body = rows.map((r) => '<Row>' + cols.map((c) => cell(r[c.key])).join('') + '</Row>').join('');
  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Styles><Style ss:ID="h"><Font ss:Bold="1"/><Interior ss:Color="#EEF2F6" ss:Pattern="Solid"/></Style></Styles>
 <Worksheet ss:Name="CW"><Table>${header}${body}</Table></Worksheet>
</Workbook>`;
  const blob = new Blob(['\ufeff' + xml], { type: 'application/vnd.ms-excel' });
  const a = el('a', { href: URL.createObjectURL(blob), download: filename.replace(/\.csv$/, '.xls') });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export function watchToggle(ticker) {
  const list = store.get('watchlist', []);
  const btn = el('button', { class: 'btn sm' });
  const paint = () => {
    const on = store.get('watchlist', []).includes(ticker);
    btn.innerHTML = on ? '★ Đang theo dõi' : '☆ Theo dõi';
    btn.classList.toggle('primary', on);
  };
  btn.onclick = () => {
    const cur = store.get('watchlist', []);
    const next = cur.includes(ticker) ? cur.filter((t) => t !== ticker) : [...cur, ticker];
    store.set('watchlist', next);
    paint();
    toast(next.includes(ticker) ? `Đã thêm ${ticker} vào watchlist` : `Đã xoá ${ticker} khỏi watchlist`);
  };
  paint();
  return btn;
}
