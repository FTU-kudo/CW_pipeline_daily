/* Screener đa điều kiện — AND/OR, bộ lọc lưu, xuất CSV, cột tuỳ chọn */
import {
  el, fmt, data, pageHead, table, scoreCell, badge, store, toast, downloadCsv, downloadXls, navigate, openDrawer, closeDrawer, $,
} from '../core.js';

const FIELDS = [
  { key: 'price', label: 'Giá CW (VND)', type: 'num', unit: 'VND', step: 10 },
  { key: 'chg1', label: '% thay đổi 1 phiên', type: 'num', unit: '%', step: 0.5 },
  { key: 'ret5', label: '% thay đổi 5 phiên', type: 'num', unit: '%', step: 1 },
  { key: 'ret21', label: '% thay đổi 21 phiên', type: 'num', unit: '%', step: 1 },
  { key: 'premium', label: 'Premium hoà vốn', type: 'num', unit: '%', step: 1 },
  { key: 'dte', label: 'Số ngày còn lại', type: 'num', unit: 'ngày', step: 10 },
  { key: 'score', label: 'CW Score', type: 'num', unit: 'điểm', step: 5 },
  { key: 'dq', label: 'Chất lượng dữ liệu (0–1)', type: 'num', unit: '', step: 0.05 },
  { key: 'iv', label: 'IV', type: 'num', unit: 'thập phân', step: 0.05 },
  { key: 'ivVsHv', label: 'IV − HV', type: 'num', unit: '%', step: 5 },
  { key: 'ivRank', label: 'IV rank (0–100)', type: 'num', unit: '', step: 5 },
  { key: 'delta', label: 'Delta', type: 'num', unit: '', step: 0.01 },
  { key: 'fvSmile', label: 'Giá trị hợp lý (smile)', type: 'num', unit: 'VND', step: 10 },
  { key: 'upsideSmile', label: 'Upside so giá trị hợp lý', type: 'num', unit: '%', step: 5 },
  { key: 'value20', label: 'GT giao dịch TB 20P', type: 'num', unit: 'VND', step: 1000000 },
  { key: 'vol', label: 'Khối lượng phiên', type: 'num', unit: 'CW', step: 10000 },
  { key: 'rsi', label: 'RSI (CW)', type: 'num', unit: '', step: 5 },
  { key: 'atrPct', label: 'ATR / giá', type: 'num', unit: '%', step: 1 },
  { key: 'sessions', label: 'Số phiên có dữ liệu', type: 'num', unit: '', step: 10 },
  { key: 'uRet21', label: '% cơ sở 21 phiên', type: 'num', unit: '%', step: 1 },
  { key: 'uRsi', label: 'RSI cổ phiếu cơ sở', type: 'num', unit: '', step: 5 },
  { key: 'uAbove50', label: 'Cơ sở trên MA50 (1/0)', type: 'num', unit: '', step: 1 },
  { key: 'above50', label: 'CW trên MA50 (1/0)', type: 'num', unit: '', step: 1 },
  { key: 'u', label: 'Cổ phiếu cơ sở', type: 'cat', options: () => uniq('u') },
  { key: 'issName', label: 'Tổ chức phát hành', type: 'cat', options: () => uniq('issName') },
  { key: 'money', label: 'Moneyness ITM/ATM/OTM', type: 'cat', options: () => ['ITM', 'ATM', 'OTM'] },
  { key: 'rec', label: 'Khuyến nghị', type: 'cat', options: () => ['STRONG_BUY', 'BUY', 'HOLD', 'AVOID', 'HIGH_RISK'] },
  { key: 't', label: 'Mã CW', type: 'text' },
  { key: 'iss', label: 'Mã TCPH', type: 'cat', options: () => uniq('iss') },
];

const FIELD_MAP = Object.fromEntries(FIELDS.map((f) => [f.key, f]));

function uniq(key) {
  return Array.from(new Set(data.activeRows().map((r) => r[key]).filter((v) => v !== null && v !== undefined && v !== ''))).sort();
}

const PRESETS = {
  cheap: {
    label: 'Định giá hấp dẫn',
    logic: 'AND',
    conditions: [
      { field: 'ivVsHv', op: '<=', v1: 0 },
      { field: 'premium', op: '<=', v1: 20 },
      { field: 'dte', op: '>=', v1: 45 },
      { field: 'value20', op: '>=', v1: 5000000 },
    ],
  },
  momentum: {
    label: 'Động lượng mạnh',
    logic: 'AND',
    conditions: [
      { field: 'uRet21', op: '>=', v1: 5 },
      { field: 'uAbove50', op: '=', v1: 1 },
      { field: 'delta', op: '>=', v1: 0.25 },
      { field: 'score', op: '>=', v1: 60 },
    ],
  },
  liquid: {
    label: 'Thanh khoản tốt',
    logic: 'AND',
    conditions: [
      { field: 'value20', op: '>=', v1: 20000000 },
      { field: 'sessions', op: '>=', v1: 60 },
      { field: 'premium', op: '<=', v1: 25 },
    ],
  },
  short: {
    label: 'Sắp đáo hạn (rủi ro)',
    logic: 'AND',
    conditions: [
      { field: 'dte', op: '<=', v1: 30 },
      { field: 'money', op: '=', v1: 'OTM' },
    ],
  },
  expensive: {
    label: 'CW đắt (tránh)',
    logic: 'OR',
    conditions: [
      { field: 'ivVsHv', op: '>=', v1: 50 },
      { field: 'premium', op: '>=', v1: 40 },
    ],
  },
  watch: {
    label: 'MUA/MUA MẠNH + DQ cao',
    logic: 'AND',
    conditions: [
      { field: 'score', op: '>=', v1: 65 },
      { field: 'dq', op: '>=', v1: 0.9 },
      { field: 'sessions', op: '>=', v1: 30 },
    ],
  },
};

const ALL_COLUMNS = [
  { key: 't', title: 'Mã', render: (r) => el('span', { class: 'tbl-ticker', text: r.t }), fixed: true, width: 96 },
  { key: 'u', title: 'Cơ sở', fixed: true, width: 60 },
  { key: 'issName', title: 'TCPH', width: 90 },
  { key: 'price', title: 'Giá', align: 'right', render: (r) => fmt.px(r.price) },
  { key: 'chg1', title: '%1P', align: 'right', render: (r) => el('span', { class: fmt.cls(r.chg1), text: fmt.pct(r.chg1, 2) }) },
  { key: 'ret5', title: '%5P', align: 'right', render: (r) => el('span', { class: fmt.cls(r.ret5), text: fmt.pct(r.ret5, 1) }) },
  { key: 'ret21', title: '%21P', align: 'right', render: (r) => el('span', { class: fmt.cls(r.ret21), text: fmt.pct(r.ret21, 1) }) },
  { key: 'S', title: 'Giá cơ sở', align: 'right', render: (r) => fmt.px(r.S) },
  { key: 'K', title: 'Strike (adj)', align: 'right', render: (r) => fmt.px(r.K) },
  { key: 'ratio', title: 'Tỷ lệ', align: 'right', render: (r) => fmt.n(r.ratio, 4) },
  { key: 'money', title: 'Moneyness', render: (r) => el('span', { class: `badge ${r.money}`, text: r.money }) },
  { key: 'moneyPct', title: '%Money', align: 'right', render: (r) => el('span', { class: fmt.cls(r.moneyPct), text: fmt.pct(r.moneyPct, 1) }) },
  { key: 'premium', title: 'Premium', align: 'right', render: (r) => fmt.pct(r.premium, 1, false) },
  { key: 'dte', title: 'DTE', align: 'right' },
  { key: 'iv', title: 'IV', align: 'right', render: (r) => fmt.pct((r.iv || 0) * 100, 0, false) },
  { key: 'ivVsHv', title: 'IV−HV', align: 'right', render: (r) => el('span', { class: fmt.cls(-(r.ivVsHv || 0)), text: fmt.pct(r.ivVsHv, 0) }) },
  { key: 'ivResid', title: 'IV resid', align: 'right', render: (r) => el('span', { class: fmt.cls(-(r.ivResid || 0)), text: fmt.pct(r.ivResid, 1) }) },
  { key: 'delta', title: 'Delta', align: 'right', render: (r) => fmt.n(r.delta, 3) },
  { key: 'theta', title: 'Theta/ngày', align: 'right', render: (r) => fmt.n(r.theta, 3) },
  { key: 'fvSmile', title: 'FV smile', align: 'right', render: (r) => fmt.px(r.fvSmile) },
  { key: 'upsideSmile', title: 'Upside', align: 'right', render: (r) => el('span', { class: fmt.cls(r.upsideSmile), text: fmt.pct(r.upsideSmile, 1) }) },
  { key: 'value20', title: 'GT 20P', align: 'right', render: (r) => fmt.vnd(r.value20) },
  { key: 'value', title: 'GT phiên', align: 'right', render: (r) => fmt.vnd(r.value) },
  { key: 'vol', title: 'KL phiên', align: 'right', render: (r) => fmt.compact(r.vol) },
  { key: 'rsi', title: 'RSI', align: 'right', render: (r) => fmt.n(r.rsi, 0) },
  { key: 'sessions', title: 'Số phiên', align: 'right' },
  { key: 'score', title: 'Điểm', align: 'right', render: (r) => scoreCell(r.score) },
  { key: 'dq', title: 'DQ', align: 'right', render: (r) => fmt.n(r.dq, 2) },
  { key: 'rec', title: 'Khuyến nghị', render: (r) => badge(r.rec), fixed: true, width: 104 },
  {
    key: 'actions',
    title: '',
    sortable: false,
    render: (r) => el('button', {
      class: 'btn sm ghost',
      text: '★',
      title: 'Thêm vào watchlist',
      onclick: (ev) => {
        ev.stopPropagation();
        const cur = store.get('watchlist', []);
        if (!cur.includes(r.t)) { store.set('watchlist', [...cur, r.t]); toast(`Đã thêm ${r.t} vào watchlist`); }
        else toast(`${r.t} đã có trong watchlist`);
      },
    }),
  },
];

const DEFAULT_COLS = ['t', 'u', 'price', 'chg1', 'ret5', 'premium', 'dte', 'iv', 'ivVsHv', 'value20', 'score', 'rec'];

let state = {
  logic: 'AND',
  conditions: [],
  q: '',
  showExpired: false,
  cols: store.get('screenerCols', DEFAULT_COLS),
  recFilter: '',
};

function cmp(v, op, target) {
  if (v === null || v === undefined) return false;
  switch (op) {
    case '>': return v > target;
    case '>=': return v >= target;
    case '<': return v < target;
    case '<=': return v <= target;
    case '=': return String(v) === String(target);
    case '!=': return String(v) !== String(target);
    case 'between': return v >= target && v <= (arguments[3] ?? target);
    case 'contains': return String(v).toLowerCase().includes(String(target).toLowerCase());
    default: return false;
  }
}

function evalCondition(row, c) {
  const field = FIELD_MAP[c.field];
  if (!field) return true;
  const v = row[c.field];
  if (field.type === 'num') {
    const n = Number(v);
    if (!Number.isFinite(n)) return false;
    if (c.op === 'between') return n >= Number(c.v1) && n <= Number(c.v2);
    return cmp(n, c.op, Number(c.v1));
  }
  return cmp(v, c.op, c.v1);
}

function applyFilters(rows) {
  let out = rows;
  if (state.q) {
    const q = state.q.toLowerCase();
    out = out.filter((r) => r.t.toLowerCase().includes(q) || r.u.toLowerCase().includes(q) || (r.issName || '').toLowerCase().includes(q));
  }
  if (state.recFilter) out = out.filter((r) => r.rec === state.recFilter);
  if (!state.conditions.length) return out;
  return out.filter((r) => {
    const results = state.conditions.map((c) => evalCondition(r, c));
    return state.logic === 'AND' ? results.every(Boolean) : results.some(Boolean);
  });
}

function blankCondition() {
  return { field: 'score', op: '>=', v1: 65, v2: '' };
}

function conditionRow(c, idx, rerender) {
  const field = FIELD_MAP[c.field] || FIELDS[0];
  const fieldSel = el('select', {}, FIELDS.map((f) => el('option', { value: f.key, text: f.label, selected: f.key === c.field })));
  fieldSel.onchange = () => {
    c.field = fieldSel.value;
    const nf = FIELD_MAP[c.field];
    c.op = nf.type === 'num' ? '>=' : '=';
    if (nf.type === 'num') c.v1 = nf.step >= 1000000 ? 5000000 : 0;
    else c.v1 = (nf.options ? nf.options()[0] : '') || '';
    rerender();
  };
  const ops = field.type === 'num' ? ['>', '>=', '<', '<=', '=', '!=', 'between'] : ['=', '!=', 'contains'];
  const opSel = el('select', {}, ops.map((o) => el('option', { value: o, text: o, selected: o === c.op })));
  opSel.onchange = () => { c.op = opSel.value; rerender(); };

  let valueEls;
  if (field.type === 'num') {
    valueEls = el('input', {
      type: 'number', value: c.v1, step: field.step || 1,
      oninput: (e) => { c.v1 = e.target.value === '' ? '' : Number(e.target.value); rerender(false); },
    });
  } else if (field.type === 'cat') {
    const opts = field.options ? field.options() : [];
    valueEls = el('select', {
      onchange: (e) => { c.v1 = e.target.value; rerender(false); },
    }, opts.map((o) => el('option', { value: o, text: field.key === 'rec' ? fmt.rec(o) : o, selected: String(c.v1) === String(o) })));
  } else {
    valueEls = el('input', { type: 'text', value: c.v1, oninput: (e) => { c.v1 = e.target.value; rerender(false); } });
  }

  const children = [fieldSel, opSel, valueEls];
  if (c.op === 'between') {
    children.splice(2, 1, el('input', {
      type: 'number', value: c.v1, step: field.step || 1,
      oninput: (e) => { c.v1 = Number(e.target.value); rerender(false); },
    }), el('input', {
      type: 'number', value: c.v2, step: field.step || 1,
      oninput: (e) => { c.v2 = Number(e.target.value); rerender(false); },
    }));
    children.splice(3, 0, el('span', { class: 'tiny muted', text: 'và' }));
  }

  children.push(el('button', {
    class: 'filter-remove', text: '×', title: 'Xoá điều kiện',
    onclick: () => { state.conditions.splice(idx, 1); rerender(); },
  }));

  return el('div', { class: 'filter-row', style: c.op === 'between' ? 'grid-template-columns:1fr 64px 1fr 18px 1fr 24px' : null }, children);
}

function render() {
  const view = $('#view');
  view.innerHTML = '';
  const allRows = state.showExpired ? data.allRows() : data.activeRows();
  const rows = applyFilters(allRows);

  view.appendChild(pageHead(
    'Bộ lọc chứng quyền',
    'Kết hợp nhiều điều kiện số/ định tính với logic AND/OR. Mọi giá trị tính từ dữ liệu cuối phiên, không realtime.',
    [
      el('button', {
        class: 'btn sm',
        text: 'Cột hiển thị',
        onclick: () => openColumnPicker(render),
      }),
      el('button', { class: 'btn sm', text: '⇩ CSV', onclick: () => exportCsv(rows) }),
      el('button', { class: 'btn sm', text: '⇩ Excel', onclick: () => exportExcel(rows) }),
      el('button', { class: 'btn sm primary', text: '⟳ Áp dụng ngay', onclick: render }),
    ],
  ));

  const layout = el('div', { class: 'screener-layout' });

  /* ---------- filters panel ---------- */
  const panel = el('div', { class: 'filters-panel' });
  const fcard = el('div', { class: 'card' });

  const qInput = el('input', { type: 'search', placeholder: 'Mã CW / cổ phiếu / TCPH', value: state.q, style: 'width:100%;margin-bottom:10px' });
  qInput.oninput = () => { state.q = qInput.value.trim(); renderResults(); };

  const logicToggle = el('div', { class: 'logic-toggle' }, [
    el('button', { class: state.logic === 'AND' ? 'on' : '', text: 'AND', onclick: () => { state.logic = 'AND'; render(); } }),
    el('button', { class: state.logic === 'OR' ? 'on' : '', text: 'OR', onclick: () => { state.logic = 'OR'; render(); } }),
  ]);

  fcard.appendChild(el('div', { class: 'card-title' }, [el('h3', { text: 'Điều kiện lọc' }), logicToggle]));
  fcard.appendChild(qInput);

  const condBox = el('div');
  if (!state.conditions.length) {
    condBox.appendChild(el('div', { class: 'tiny muted', style: 'padding:6px 0 10px', text: 'Chưa có điều kiện. Chọn bộ lọc mẫu hoặc thêm điều kiện.' }));
  }
  state.conditions.forEach((c, i) => condBox.appendChild(conditionRow(c, i, renderSoft)));
  fcard.appendChild(condBox);

  fcard.appendChild(el('div', { class: 'flex', style: 'margin:8px 0 12px' }, [
    el('button', { class: 'btn sm', text: '+ Thêm điều kiện', onclick: () => { state.conditions.push(blankCondition()); render(); } }),
    el('button', { class: 'btn sm ghost', text: 'Xoá hết', onclick: () => { state.conditions = []; render(); } }),
  ]));

  fcard.appendChild(el('div', { class: 'hr' }));
  fcard.appendChild(el('div', { class: 'tiny muted', style: 'margin-bottom:6px;text-transform:uppercase;letter-spacing:.6px', text: 'Bộ lọc mẫu' }));
  const presetWrap = el('div', { class: 'preset-row' });
  for (const [k, p] of Object.entries(PRESETS)) {
    presetWrap.appendChild(el('span', {
      class: 'chip', text: p.label,
      onclick: () => { state.conditions = p.conditions.map((c) => ({ ...c })); state.logic = p.logic; render(); },
    }));
  }
  fcard.appendChild(presetWrap);

  fcard.appendChild(el('div', { class: 'hr' }));
  fcard.appendChild(el('div', { class: 'tiny muted', style: 'margin-bottom:6px;text-transform:uppercase;letter-spacing:.6px', text: 'Bộ lọc đã lưu' }));
  const saved = store.get('savedFilters', []);
  const savedBox = el('div');
  if (!saved.length) savedBox.appendChild(el('div', { class: 'tiny muted', text: 'Chưa lưu bộ lọc nào.' }));
  saved.forEach((s, i) => {
    savedBox.appendChild(el('div', { class: 'saved-filter' }, [
      el('span', { text: s.name, style: 'cursor:pointer', onclick: () => { state.conditions = s.conditions.map((c) => ({ ...c })); state.logic = s.logic; render(); } }),
      el('button', { text: '×', onclick: () => { const list = store.get('savedFilters', []); list.splice(i, 1); store.set('savedFilters', list); render(); } }),
    ]));
  });
  fcard.appendChild(savedBox);
  const saveName = el('input', { type: 'text', placeholder: 'Tên bộ lọc…', style: 'width:100%;margin-top:6px;height:28px' });
  fcard.appendChild(el('div', { class: 'flex', style: 'margin-top:6px' }, [
    saveName,
    el('button', {
      class: 'btn sm', text: 'Lưu',
      onclick: () => {
        const name = saveName.value.trim();
        if (!name) return toast('Nhập tên bộ lọc trước');
        const list = store.get('savedFilters', []);
        list.push({ name, logic: state.logic, conditions: state.conditions.map((c) => ({ ...c })) });
        store.set('savedFilters', list);
        toast('Đã lưu bộ lọc');
        render();
      },
    }),
  ]));

  fcard.appendChild(el('div', { class: 'hr' }));
  const expiredChip = el('span', { class: 'chip' + (state.showExpired ? ' on' : ''), text: 'Bao gồm CW đã đáo hạn' });
  expiredChip.onclick = () => { state.showExpired = !state.showExpired; render(); };
  fcard.appendChild(el('div', { class: 'flex flex-wrap' }, [expiredChip]));
  fcard.appendChild(el('div', { class: 'tiny muted', style: 'margin-top:8px', html: 'Lưu ý: bộ lọc chạy trên <b>toàn bộ</b> CW trong snapshot, không chỉ các mã hiển thị.' }));

  panel.appendChild(fcard);

  /* ---------- results ---------- */
  const results = el('div');
  layout.append(panel, results);
  view.appendChild(layout);

  function renderResults() {
    const filteredAll = applyFilters(state.showExpired ? data.allRows() : data.activeRows());
    results.innerHTML = '';
    const recCounts = ['STRONG_BUY', 'BUY', 'HOLD', 'AVOID', 'HIGH_RISK'].map((r) => [r, filteredAll.filter((x) => x.rec === r).length]).filter(([, n]) => n > 0);
    const summary = el('div', { class: 'result-summary' }, [
      el('div', {}, [
        el('div', { class: 'result-count', text: fmt.n(filteredAll.length, 0) }),
        el('div', { class: 'tiny muted', text: `mã thoả điều kiện / ${fmt.n(state.showExpired ? data.allRows().length : data.activeRows().length)}` }),
      ]),
      el('div', { class: 'legend-inline' }, recCounts.map(([r, n]) => el('span', { html: `${badge(r).outerHTML} <b class="mono">${n}</b>` }))),
      el('div', { class: 'spacer' }),
      el('span', { class: 'tiny muted', text: state.conditions.length ? `${state.conditions.length} điều kiện · logic ${state.logic}` : 'Không có điều kiện' }),
    ]);
    results.appendChild(summary);

    const cols = ALL_COLUMNS.filter((c) => c.fixed || state.cols.includes(c.key));
    const tbl = table({
      columns: cols,
      rows: filteredAll,
      onRowClick: (r) => navigate(`#/cw/${r.t}`),
      empty: 'Không có CW nào thoả điều kiện. Thử nới lỏng bộ lọc.',
      compact: true,
    });
    results.appendChild(tbl);
    results.appendChild(el('div', { class: 'tiny muted', style: 'margin-top:8px', text: 'Nhấp vào dòng để mở trang phân tích chi tiết. Điểm và khuyến nghị là thang tương đối trong vũ trụ CW hiện tại — xem tab Phương pháp.' }));

    const navCount = $('#nav-screener-count');
    if (navCount) navCount.textContent = filteredAll.length;
  }

  renderResults();

  function renderSoft() {
    // cập nhật điều kiện không dựng lại toàn trang (giữ focus ô nhập)
    renderResults();
  }
}

function exportCsv(rows) {
  const cols = [
    ['t', 'Mã'], ['u', 'Cơ sở'], ['issName', 'TCPH'], ['price', 'Giá'], ['chg1', '%1P'], ['ret5', '%5P'], ['ret21', '%21P'],
    ['S', 'Giá cơ sở'], ['K', 'Strike'], ['ratio', 'Tỷ lệ'], ['money', 'Moneyness'], ['moneyPct', '%Money'],
    ['premium', 'Premium (%)'], ['dte', 'DTE'], ['iv', 'IV'], ['ivVsHv', 'IV-HV (%)'], ['ivRank', 'IV rank'],
    ['delta', 'Delta'], ['gamma', 'Gamma'], ['theta', 'Theta'], ['vega', 'Vega'], ['fvSmile', 'FV smile'],
    ['upsideSmile', 'Upside (%)'], ['fvHv', 'FV HV'], ['value', 'GT phiên'], ['value20', 'GT 20P'], ['vol', 'KL phiên'],
    ['rsi', 'RSI'], ['sessions', 'Số phiên'], ['score', 'Điểm'], ['dq', 'DQ'], ['rec', 'Khuyến nghị'],
  ];
  const out = rows.map((r) => Object.fromEntries(cols.map(([k, label]) => [label, r[k] ?? ''])));
  downloadCsv(`cw-screener-${data.meta?.asof || ''}.csv`, out);
  toast(`Đã xuất ${rows.length} dòng CSV`);
}

const EXPORT_COLS = [
  ['t', 'Mã'], ['u', 'Cơ sở'], ['issName', 'TCPH'], ['price', 'Giá CW (VND)'], ['chg1', '%1P'], ['ret5', '%5P'], ['ret21', '%21P'],
  ['S', 'Giá cơ sở'], ['K', 'Strike'], ['ratio', 'Tỷ lệ'], ['money', 'Moneyness'], ['moneyPct', '%Money'],
  ['premium', 'Premium (%)'], ['dte', 'DTE'], ['iv', 'IV'], ['ivVsHv', 'IV-HV (%)'], ['ivRank', 'IV rank'],
  ['delta', 'Delta'], ['gamma', 'Gamma'], ['theta', 'Theta'], ['vega', 'Vega'], ['fvSmile', 'FV smile'],
  ['upsideSmile', 'Upside (%)'], ['fvHv', 'FV HV'], ['value', 'GT phiên'], ['value20', 'GT 20P'], ['vol', 'KL phiên'],
  ['rsi', 'RSI'], ['sessions', 'Số phiên'], ['score', 'Điểm'], ['dq', 'DQ'], ['rec', 'Khuyến nghị'],
];

function exportExcel(rows) {
  const cols = EXPORT_COLS.map(([key, title]) => ({ key, title }));
  downloadXls(`cw-screener-${data.meta?.asof || ''}.xls`, rows, cols);
  toast(`Đã xuất ${rows.length} dòng Excel`);
}

function openColumnPicker(after) {
  const body = el('div');
  body.appendChild(el('h3', { text: 'Chọn cột hiển thị', style: 'margin-bottom:10px' }));
  const list = el('div', { class: 'stack' });
  const selected = new Set(state.cols);
  for (const c of ALL_COLUMNS) {
    if (c.fixed) continue;
    const cb = el('input', {
      type: 'checkbox',
      checked: selected.has(c.key),
      onchange: (e) => {
        if (e.target.checked) selected.add(c.key); else selected.delete(c.key);
      },
    });
    list.appendChild(el('label', { class: 'flex', style: 'font-size:12px;cursor:pointer' }, [cb, el('span', { text: c.title })]));
  }
  body.appendChild(list);
  body.appendChild(el('div', { class: 'flex', style: 'margin-top:14px' }, [
    el('button', {
      class: 'btn primary sm', text: 'Áp dụng',
      onclick: () => {
        state.cols = Array.from(selected);
        store.set('screenerCols', state.cols);
        closeDrawer();
        after();
      },
    }),
    el('button', { class: 'btn sm', text: 'Mặc định', onclick: () => { state.cols = DEFAULT_COLS.slice(); store.set('screenerCols', state.cols); closeDrawer(); after(); } }),
  ]));
  openDrawer(body);
}

export default function screener(view) {
  // Đọc tham số từ hash mỗi lần vào trang: #/screener?u=FPT&preset=cheap&rec=BUY
  const raw = decodeURIComponent(location.hash);
  const m = raw.match(/^#\/screener(?:\?(.*))?$/);
  const params = new URLSearchParams(m && m[1] ? m[1] : '');
  state.q = params.get('u') || '';
  state.recFilter = params.get('rec') || '';
  if (params.get('preset') && PRESETS[params.get('preset')]) {
    state.conditions = PRESETS[params.get('preset')].conditions.map((c) => ({ ...c }));
    state.logic = PRESETS[params.get('preset')].logic;
  } else if (params.get('u') || params.get('rec')) {
    // deep-link theo cơ sở/khuyến nghị: bỏ điều kiện cũ để tránh giao thoa khó hiểu
    state.conditions = [];
  }
  render();
}
