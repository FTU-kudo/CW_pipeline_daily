/* Watchlist, Danh mục mô phỏng, Cảnh báo (lưu cục bộ trên trình duyệt) */
import {
  el, fmt, data, pageHead, sectionHead, badge, scoreCell, table, store, toast,
  downloadCsv, navigate, kpiCard,
} from '../core.js';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* ============================ WATCHLIST ============================ */
export function watchlistPage(view) {
  const tickers = store.get('watchlist', []);
  const rows = tickers.map((t) => data.row(t)).filter(Boolean);

  view.appendChild(pageHead(
    'Watchlist',
    'Danh sách theo dõi được lưu trên trình duyệt của bạn (localStorage). Không đồng bộ giữa các thiết bị.',
    [el('button', { class: 'btn sm primary', text: '+ Thêm từ Screener', onclick: () => navigate('#/screener') })],
  ));

  if (!rows.length) {
    view.appendChild(el('div', { class: 'empty' }, [
      el('div', { text: 'Watchlist đang trống.' }),
      el('div', { class: 'tiny muted', style: 'margin-top:6px', text: 'Nhấn ★ trên bảng screener hoặc trang chi tiết để thêm mã.' }),
      el('button', { class: 'btn sm', style: 'margin-top:10px', text: 'Mở Screener', onclick: () => navigate('#/screener') }),
    ]));
    return;
  }

  const avgScore = rows.reduce((a, r) => a + (r.score || 0), 0) / rows.length;
  const totalValue = rows.reduce((a, r) => a + (r.value20 || 0), 0);
  const nearest = rows.slice().sort((a, b) => (a.dte || 9999) - (b.dte || 9999))[0];

  view.appendChild(el('div', { class: 'grid kpi section' }, [
    kpiCard({ label: 'Số mã theo dõi', value: fmt.n(rows.length, 0) }),
    kpiCard({ label: 'Điểm trung bình', value: fmt.n(avgScore, 1) }),
    kpiCard({ label: 'Tín hiệu MUA', value: fmt.n(rows.filter((r) => r.rec === 'BUY' || r.rec === 'STRONG_BUY').length, 0), valueClass: 'up' }),
    kpiCard({ label: 'Cảnh báo đáo hạn gần', value: fmt.n(rows.filter((r) => (r.dte || 999) < 45).length, 0), valueClass: 'down', sub: nearest ? `gần nhất ${nearest.t} · ${nearest.dte} ngày` : '' }),
    kpiCard({ label: 'Tổng GT 20P', value: fmt.vnd(totalValue), sub: 'thanh khoản của các mã đang theo dõi' }),
  ]));

  view.appendChild(table({
    rows,
    onRowClick: (r) => navigate(`#/cw/${r.t}`),
    columns: [
      { key: 't', title: 'Mã', render: (r) => el('span', { class: 'tbl-ticker', text: r.t }) },
      { key: 'u', title: 'Cơ sở' },
      { key: 'issName', title: 'TCPH' },
      { key: 'price', title: 'Giá', align: 'right', render: (r) => fmt.px(r.price) },
      { key: 'chg1', title: '%1P', align: 'right', render: (r) => el('span', { class: fmt.cls(r.chg1), text: fmt.pct(r.chg1, 2) }) },
      { key: 'premium', title: 'Premium', align: 'right', render: (r) => fmt.pct(r.premium, 1, false) },
      { key: 'ivVsHv', title: 'IV−HV', align: 'right', render: (r) => el('span', { class: fmt.cls(-(r.ivVsHv || 0)), text: fmt.pct(r.ivVsHv, 0) }) },
      { key: 'dte', title: 'DTE', align: 'right' },
      { key: 'score', title: 'Điểm', align: 'right', render: (r) => scoreCell(r.score) },
      { key: 'rec', title: 'Khuyến nghị', render: (r) => badge(r.rec) },
      {
        key: 'x', title: '', sortable: false,
        render: (r) => el('button', {
          class: 'btn sm ghost', text: '✕', title: 'Bỏ theo dõi',
          onclick: (ev) => {
            ev.stopPropagation();
            store.set('watchlist', store.get('watchlist', []).filter((t) => t !== r.t));
            toast(`Đã bỏ ${r.t}`);
            navigate('#/watchlist');
          },
        }),
      },
    ],
  }));

  view.appendChild(el('div', { class: 'flex', style: 'margin-top:12px' }, [
    el('button', {
      class: 'btn sm', text: '⇩ Xuất CSV',
      onclick: () => {
        downloadCsv(`cw-watchlist-${data.meta?.asof || ''}.csv`, rows.map((r) => ({
          Ma: r.t, 'Co so': r.u, Gia: r.price, 'Chg1 (%)': r.chg1, 'Premium (%)': r.premium,
          'IV-HV (%)': r.ivVsHv, DTE: r.dte, Diem: r.score, Rec: fmt.rec(r.rec),
        })));
        toast('Đã xuất CSV');
      },
    }),
    el('button', {
      class: 'btn sm danger', text: 'Xoá tất cả',
      onclick: () => { if (confirm('Xoá toàn bộ watchlist?')) { store.set('watchlist', []); navigate('#/watchlist'); } },
    }),
  ]));
}

/* ============================ PORTFOLIO ============================ */
const pfState = { ticker: '', price: '', qty: 10000, date: '' };

export function portfolioPage(view) {
  const entries = store.get('portfolio', []);
  const rows = entries.map((e) => {
    const r = data.row(e.ticker);
    const price = r?.price ?? null;
    const cost = e.price * e.qty;
    const mv = price !== null ? price * e.qty : null;
    const pl = mv !== null ? mv - cost : null;
    return {
      ...e, row: r, price, cost, mv, pl,
      plPct: pl !== null && cost ? (pl / cost) * 100 : null,
      dte: r?.dte ?? null, score: r?.score ?? null, rec: r?.rec ?? null,
      value20: r?.value20 ?? null,
    };
  });
  const totalCost = rows.reduce((a, r) => a + r.cost, 0);
  const totalMv = rows.reduce((a, r) => a + (r.mv || 0), 0);
  const totalPl = totalMv - totalCost;
  const maxWeight = totalMv ? Math.max(...rows.map((r) => (r.mv || 0) / totalMv)) : 0;

  view.appendChild(pageHead(
    'Danh mục mô phỏng',
    'Mô phỏng vị thế — <b>không</b> kết nối tài khoản, không đặt lệnh. Dữ liệu giá là snapshot cuối phiên, không phải giá khớp thực tế.',
    [el('button', {
      class: 'btn sm', text: '⇩ Xuất CSV',
      onclick: () => {
        downloadCsv('cw-portfolio.csv', rows.map((r) => ({
          Ma: r.ticker, 'Ngay mua': r.date, 'Gia mua': r.price, 'So luong': r.qty,
          'Gia hien tai': r.price ?? '', 'Gia tri thi truong': r.mv ?? '',
          'Lai lo': r.pl ?? '', 'Lai lo (%)': r.plPct ?? '', DTE: r.dte ?? '', Diem: r.score ?? '',
        })));
        toast('Đã xuất CSV');
      },
    })],
  ));

  // form
  const tickers = data.activeRows().map((r) => r.t).sort();
  const tickerInput = el('input', { type: 'text', list: 'cw-tickers', placeholder: 'VD: CVIB2612', value: pfState.ticker, style: 'min-width:140px' });
  const dl = el('datalist', { id: 'cw-tickers' }, tickers.map((t) => el('option', { value: t })));
  const priceInput = el('input', { type: 'number', min: 10, step: 10, placeholder: 'Giá mua (VND)', value: pfState.price, style: 'width:140px' });
  const qtyInput = el('input', { type: 'number', min: 100, step: 100, value: pfState.qty, style: 'width:120px' });
  const dateInput = el('input', { type: 'date', value: pfState.date || data.meta?.asof || '', style: 'width:150px' });

  const addBtn = el('button', { class: 'btn primary sm', text: '+ Thêm vị thế' });
  addBtn.onclick = () => {
    const t = tickerInput.value.trim().toUpperCase();
    if (!t || !data.row(t)) return toast('Mã CW không tồn tại trong snapshot');
    const qty = Math.max(100, Number(qtyInput.value) || 0);
    let price = Number(priceInput.value);
    if (!price || price <= 0) {
      const cur = data.row(t)?.price;
      if (!cur) return toast('Nhập giá mua');
      price = cur;
    }
    const list = store.get('portfolio', []);
    list.push({ id: Date.now(), ticker: t, price, qty, date: dateInput.value || data.meta?.asof });
    store.set('portfolio', list);
    pfState.ticker = ''; pfState.price = ''; pfState.date = '';
    toast(`Đã thêm ${t} vào danh mục mô phỏng`);
    navigate('#/portfolio');
  };

  view.appendChild(el('div', { class: 'card section' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Thêm vị thế (giả lập)' })]),
    el('div', { class: 'filterbar', style: 'margin-bottom:0' }, [
      el('label', { class: 'field' }, [el('span', { text: 'Mã CW' }), tickerInput, dl]),
      el('label', { class: 'field' }, [el('span', { text: 'Giá mua (VND/CW)' }), priceInput]),
      el('label', { class: 'field' }, [el('span', { text: 'Số lượng CW' }), qtyInput]),
      el('label', { class: 'field' }, [el('span', { text: 'Ngày mua' }), dateInput]),
      addBtn,
    ]),
    el('div', { class: 'tiny muted', style: 'margin-top:6px', text: 'Giá mua là giá bạn tự nhập (VND/CW); để trống sẽ dùng giá cuối phiên. Số lượng mặc định 10.000 CW.' }),
  ]));

  if (!rows.length) {
    view.appendChild(el('div', { class: 'empty', text: 'Chưa có vị thế nào. Thêm vị thế để xem P/L và phân bổ.' }));
    return;
  }

  view.appendChild(el('div', { class: 'grid kpi section' }, [
    kpiCard({ label: 'Vốn đầu tư', value: fmt.vnd(totalCost), sub: `${rows.length} vị thế` }),
    kpiCard({ label: 'Giá trị thị trường', value: fmt.vnd(totalMv) }),
    kpiCard({ label: 'Lãi/lỗ chưa thực hiện', value: fmt.vnd(totalPl), valueClass: totalPl >= 0 ? 'up' : 'down', sub: fmt.pct(totalCost ? (totalPl / totalCost) * 100 : 0, 2) }),
    kpiCard({ label: 'Tập trung lớn nhất', value: fmt.pct(maxWeight * 100, 1, false), valueClass: maxWeight > 0.4 ? 'down' : '', sub: 'tỷ trọng vị thế lớn nhất' }),
    kpiCard({ label: 'Đáo hạn gần nhất', value: (() => {
      const n = rows.slice().sort((a, b) => (a.dte ?? 9999) - (b.dte ?? 9999))[0];
      return n ? `${n.ticker} · ${n.dte}n` : '—';
    })(), valueClass: rows.some((r) => (r.dte || 999) < 45) ? 'down' : '' }),
  ]));

  // cảnh báo danh mục
  const warns = [];
  for (const r of rows) {
    if (!r.row) warns.push(`${r.ticker}: không còn trong snapshot (có thể đã đáo hạn) — cần thoát/ghi nhận.`);
    else {
      if ((r.dte || 999) < 45) warns.push(`${r.ticker}: chỉ còn ${r.dte} ngày tới đáo hạn.`);
      if ((r.value20 || 0) < 5e6) warns.push(`${r.ticker}: thanh khoản thấp (${fmt.vnd(r.value20)}/phiên) — khó thoát vị thế.`);
      if ((r.rec === 'AVOID' || r.rec === 'HIGH_RISK')) warns.push(`${r.ticker}: mô hình xếp hạng ${fmt.rec(r.rec)} — xem lại luận điểm.`);
    }
  }
  if (maxWeight > 0.4) warns.push(`Tập trung quá mức: một vị thế chiếm ${fmt.pct(maxWeight * 100, 1, false)} danh mục.`);
  if (warns.length) {
    view.appendChild(el('div', { class: 'card section' }, [
      el('div', { class: 'card-title' }, [el('h3', { text: 'Cảnh báo danh mục' })]),
      el('ul', { class: 'factor-list warn' }, warns.map((w) => el('li', { text: w }))),
    ]));
  }

  view.appendChild(table({
    rows,
    onRowClick: (r) => r.ticker && navigate(`#/cw/${r.ticker}`),
    columns: [
      { key: 'ticker', title: 'Mã', render: (r) => el('span', { class: 'tbl-ticker', text: r.ticker }) },
      { key: 'date', title: 'Ngày mua', render: (r) => fmt.date(r.date) },
      { key: 'price', title: 'Giá mua', align: 'right', render: (r) => fmt.px(r.price) },
      { key: 'qty', title: 'SL', align: 'right', render: (r) => fmt.n(r.qty, 0) },
      { key: 'cost', title: 'Vốn', align: 'right', render: (r) => fmt.vnd(r.cost), sortValue: (r) => r.cost },
      { key: 'cur', title: 'Giá hiện tại', align: 'right', render: (r) => (r.price !== null ? fmt.px(r.price) : '—'), sortValue: (r) => r.price },
      { key: 'mv', title: 'Giá trị', align: 'right', render: (r) => (r.mv !== null ? fmt.vnd(r.mv) : '—'), sortValue: (r) => r.mv },
      { key: 'pl', title: 'Lãi/lỗ', align: 'right', render: (r) => (r.pl === null ? '—' : el('span', { class: fmt.cls(r.pl), text: fmt.vnd(r.pl) })), sortValue: (r) => r.pl },
      { key: 'plPct', title: '%', align: 'right', render: (r) => (r.plPct === null ? '—' : el('span', { class: fmt.cls(r.plPct), text: fmt.pct(r.plPct, 2) })), sortValue: (r) => r.plPct },
      { key: 'w', title: 'Tỷ trọng', align: 'right', render: (r) => (totalMv && r.mv ? fmt.pct((r.mv / totalMv) * 100, 1, false) : '—'), sortValue: (r) => r.mv },
      { key: 'dte', title: 'DTE', align: 'right', render: (r) => (r.dte === null ? '—' : r.dte) },
      { key: 'score', title: 'Điểm', align: 'right', render: (r) => scoreCell(r.score) },
      {
        key: 'x', title: '', sortable: false,
        render: (r) => el('button', {
          class: 'btn sm ghost', text: '✕',
          onclick: (ev) => {
            ev.stopPropagation();
            store.set('portfolio', store.get('portfolio', []).filter((e) => e.id !== r.id));
            toast('Đã xoá vị thế');
            navigate('#/portfolio');
          },
        }),
      },
    ],
  }));

  view.appendChild(el('div', { class: 'notice warn', style: 'margin-top:12px', html:
    'P/L tính trên giá cuối phiên và <b>chưa</b> trừ phí giao dịch/thuế, chưa tính chênh lệch mua-bán thực tế. '
    + 'Đây là công cụ mô phỏng để quản trị rủi ro, không phải sao kê.' }));
}

/* ============================ ALERTS ============================ */
const ALERT_TYPES = {
  score_above: { label: 'Điểm CW ≥', unit: 'điểm', def: 70, test: (r, t) => (r.score || 0) >= t, describe: (t) => `Điểm ≥ ${t}` },
  score_below: { label: 'Điểm CW ≤', unit: 'điểm', def: 45, test: (r, t) => (r.score || 0) <= t, describe: (t) => `Điểm ≤ ${t}` },
  rec_change: { label: 'Khuyến nghị thay đổi', unit: '', def: null, test: null, describe: () => 'Hạng thay đổi so lần quét trước' },
  price_above: { label: 'Giá CW ≥', unit: 'nghìn', def: 1000, test: (r, t) => (r.price || 0) >= t, describe: (t) => `Giá ≥ ${fmt.n(t)}` },
  price_below: { label: 'Giá CW ≤', unit: 'nghìn', def: 200, test: (r, t) => (r.price || 0) <= t, describe: (t) => `Giá ≤ ${fmt.n(t)}` },
  volume_spike: { label: 'KL đột biến (× TB20)', unit: 'lần', def: 2, test: (r, t) => (r.volAccel || 0) >= t, describe: (t) => `KL ≥ ${t}× TB` },
  rsi_above: { label: 'RSI(14) CW ≥', unit: '', def: 75, test: (r, t) => (r.rsi || 0) >= t, describe: (t) => `RSI ≥ ${t}` },
  rsi_below: { label: 'RSI(14) CW ≤', unit: '', def: 25, test: (r, t) => (r.rsi || 0) <= t, describe: (t) => `RSI ≤ ${t}` },
  dte_below: { label: 'Còn ≤ ngày tới đáo hạn', unit: 'ngày', def: 30, test: (r, t) => (r.dte ?? 9999) <= t, describe: (t) => `DTE ≤ ${t}` },
  liquidity_below: { label: 'GT giao dịch TB20 ≤', unit: 'triệu VND', def: 5, test: (r, t) => ((r.value20 || 0) / 1e6) <= t, describe: (t) => `GT ≤ ${t} tr` },
  premium_above: { label: 'Premium hoà vốn ≥', unit: '%', def: 35, test: (r, t) => (r.premium || 0) >= t, describe: (t) => `Premium ≥ ${t}%` },
  underlying_break: { label: 'Cơ sở mất MA50', unit: '', def: null, test: (r) => r.uAbove50 === 0, describe: () => 'Cơ sở dưới MA50' },
  breakout: { label: 'CW vượt đỉnh 20 phiên', unit: '', def: null, test: (r) => r.breakout === 1, describe: () => 'Breakout 20 phiên' },
  iv_spike: { label: 'IV − HV ≥', unit: '%', def: 50, test: (r, t) => (r.ivVsHv || 0) >= t, describe: (t) => `IV−HV ≥ ${t}%` },
};

function evalAlerts() {
  const rules = store.get('alertRules', []);
  const prev = store.get('alertPrevRec', {});
  const hits = [];
  for (const rule of rules) {
    if (!rule.enabled) continue;
    const type = ALERT_TYPES[rule.type];
    if (!type) continue;
    const rows = rule.ticker ? [data.row(rule.ticker)].filter(Boolean) : data.activeRows();
    for (const r of rows) {
      if (rule.type === 'rec_change') {
        const before = prev[r.t];
        if (before && before !== r.rec) {
          hits.push({ rule, row: r, msg: `${r.t}: ${fmt.rec(before)} → ${fmt.rec(r.rec)}` });
        }
        continue;
      }
      const ok = type.test(r, rule.threshold);
      if (ok) hits.push({ rule, row: r, msg: `${r.t} (${r.u}) — ${type.describe(rule.threshold)}: hiện ${alertValue(r, rule.type)}` });
    }
  }
  return hits;
}

function alertValue(r, type) {
  switch (type) {
    case 'score_above':
    case 'score_below': return fmt.n(r.score, 1) + ' điểm';
    case 'price_above':
    case 'price_below': return fmt.px(r.price);
    case 'volume_spike': return fmt.n(r.volAccel, 1) + '×';
    case 'rsi_above':
    case 'rsi_below': return fmt.n(r.rsi, 0);
    case 'dte_below': return r.dte + ' ngày';
    case 'liquidity_below': return fmt.vnd(r.value20);
    case 'premium_above': return fmt.pct(r.premium, 1, false);
    case 'iv_spike': return fmt.pct(r.ivVsHv, 0);
    case 'underlying_break': return r.uAbove50 === 0 ? 'dưới MA50' : 'trên MA50';
    case 'breakout': return r.breakout === 1 ? 'vượt đỉnh 20 phiên' : 'chưa breakout';
    default: return '—';
  }
}

export function alertsPage(view) {
  view.appendChild(pageHead(
    'Cảnh báo',
    'Quy tắc cảnh báo chạy <b>trên trình duyệt</b> khi bạn mở trang (không có server nền). Lưu cục bộ theo thiết bị.',
    [el('button', {
      class: 'btn sm', text: '🔔 Bật thông báo trình duyệt',
      onclick: async () => {
        if (!('Notification' in window)) return toast('Trình duyệt không hỗ trợ thông báo');
        const perm = await Notification.requestPermission();
        toast(perm === 'granted' ? 'Đã bật thông báo' : 'Bạn đã từ chối quyền thông báo');
      },
    })],
  ));

  view.appendChild(el('div', { class: 'notice', html:
    '<b>Giới hạn:</b> đây là cảnh báo phía client, chỉ chạy khi tab đang mở. Gửi Telegram/email cần backend (GitHub Actions + bot) — '
    + 'xem hướng dẫn ở trang Phương pháp. Hệ thống không gửi dữ liệu của bạn đi đâu cả.' }));

  // form thêm quy tắc
  const typeSel = el('select', {}, Object.entries(ALERT_TYPES).map(([k, v]) => el('option', { value: k, text: v.label })));
  const tickerInput = el('input', { type: 'text', list: 'cw-alert-tickers', placeholder: 'Tất cả CW (hoặc nhập mã)', style: 'min-width:180px' });
  const tickerDl = el('datalist', { id: 'cw-alert-tickers' }, data.activeRows().map((r) => el('option', { value: r.t })));
  const threshold = el('input', { type: 'number', step: 'any', value: ALERT_TYPES.score_above.def, style: 'width:120px' });
  const unitLbl = el('span', { class: 'tiny muted', text: ALERT_TYPES.score_above.unit });
  typeSel.onchange = () => {
    const t = ALERT_TYPES[typeSel.value];
    threshold.value = t.def ?? '';
    unitLbl.textContent = t.unit;
  };
  const add = el('button', { class: 'btn primary sm', text: '+ Thêm cảnh báo' });
  add.onclick = () => {
    const rules = store.get('alertRules', []);
    const rule = {
      id: Date.now(), type: typeSel.value,
      ticker: tickerInput.value.trim().toUpperCase() || null,
      threshold: threshold.value === '' ? null : Number(threshold.value),
      enabled: true,
    };
    if (rule.ticker && !data.row(rule.ticker)) return toast('Mã CW không có trong snapshot');
    rules.push(rule);
    store.set('alertRules', rules);
    toast('Đã thêm cảnh báo');
    navigate('#/alerts');
  };

  view.appendChild(el('div', { class: 'card section' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Thêm quy tắc cảnh báo' })]),
    el('div', { class: 'filterbar', style: 'margin-bottom:0' }, [
      el('label', { class: 'field' }, [el('span', { text: 'Loại' }), typeSel]),
      el('label', { class: 'field' }, [el('span', { text: 'Mã CW (trống = toàn bộ)' }), tickerInput, tickerDl]),
      el('label', { class: 'field' }, [el('span', { text: 'Ngưỡng' }), el('div', { class: 'flex' }, [threshold, unitLbl])]),
      add,
    ]),
  ]));

  const rules = store.get('alertRules', []);
  const rulesCard = el('div', { class: 'card section' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: `Quy tắc của bạn (${rules.length})` })]),
  ]);
  if (!rules.length) rulesCard.appendChild(el('div', { class: 'empty', text: 'Chưa có quy tắc nào.' }));
  else {
    const t = el('table', { class: 'tbl compact' });
    t.innerHTML = '<thead><tr><th>Loại</th><th>Phạm vi</th><th>Ngưỡng</th><th>Bật</th><th></th></tr></thead>';
    const tb = el('tbody');
    rules.forEach((r) => {
      const type = ALERT_TYPES[r.type] || { label: r.type };
      tb.appendChild(el('tr', {}, [
        el('td', { text: type.label }),
        el('td', { class: 'mono', text: r.ticker || 'Toàn bộ' }),
        el('td', { class: 'mono', text: r.threshold === null ? '—' : `${fmt.n(r.threshold, 2)} ${type.unit || ''}` }),
        el('td', {}, [el('input', {
          type: 'checkbox', checked: r.enabled, onchange: (e) => {
            r.enabled = e.target.checked;
            store.set('alertRules', rules);
          },
        })]),
        el('td', {}, [el('button', {
          class: 'btn sm ghost', text: '✕', onclick: () => {
            store.set('alertRules', rules.filter((x) => x.id !== r.id));
            navigate('#/alerts');
          },
        })]),
      ]));
    });
    t.appendChild(tb);
    rulesCard.appendChild(t);
  }
  view.appendChild(rulesCard);

  // scan
  const scanCard = el('div', { class: 'card section' });
  scanCard.appendChild(el('div', { class: 'card-title' }, [
    el('h3', { text: 'Kết quả quét' }),
    el('button', { class: 'btn sm primary', text: '⟳ Quét ngay', onclick: () => runScan() }),
  ]));
  const scanBody = el('div');
  scanCard.appendChild(scanBody);
  view.appendChild(scanCard);

  function runScan() {
    const hits = evalAlerts();
    scanBody.innerHTML = '';
    const ts = new Date().toLocaleString('vi-VN');
    if (!hits.length) {
      scanBody.appendChild(el('div', { class: 'empty', text: `Không có cảnh báo nào được kích hoạt lúc ${ts}.` }));
    } else {
      scanBody.appendChild(el('div', { class: 'tiny muted', style: 'margin-bottom:8px', text: `${hits.length} cảnh báo lúc ${ts}` }));
      const box = el('div', { class: 'stack' });
      for (const h of hits) {
        box.appendChild(el('div', { class: 'flex', style: 'padding:8px 10px;background:var(--surface-2);border-radius:6px;border-left:3px solid var(--warn)' }, [
          el('span', { class: 'tbl-ticker', text: h.row.t }),
          el('span', { class: 'small', text: h.msg }),
          el('span', { class: 'spacer' }),
          el('button', { class: 'btn sm ghost', text: 'Chi tiết', onclick: () => navigate(`#/cw/${h.row.t}`) }),
        ]));
      }
      scanBody.appendChild(box);
      if ('Notification' in window && Notification.permission === 'granted') {
        try {
          new Notification(`CW Intelligence: ${hits.length} cảnh báo`, { body: hits.slice(0, 5).map((h) => h.msg).join('\n') });
        } catch { /* ignored */ }
      }
    }
    // lưu trạng thái khuyến nghị để so sánh lần sau
    const prev = {};
    for (const r of data.activeRows()) prev[r.t] = r.rec;
    store.set('alertPrevRec', prev);
    store.set('alertLastScan', ts);
  }

  const last = store.get('alertLastScan', null);
  if (last) scanBody.appendChild(el('div', { class: 'tiny muted', text: `Lần quét trước: ${last}. Nhấn "Quét ngay" để đánh giá lại.` }));
  else scanBody.appendChild(el('div', { class: 'tiny muted', text: 'Chưa quét lần nào trong phiên bản này.' }));
}
