/* Heatmap dạng treemap — tô màu theo %thay đổi / điểm / premium / IV / giá trị */
import { el, fmt, data, pageHead, navigate, toast } from '../core.js';

const METRICS = {
  chg1: {
    label: '% thay đổi (1 phiên)',
    get: (r) => r.chg1,
    scale: 'div',
    domain: (rows) => {
      const v = rows.map((r) => Math.abs(r.chg1 || 0)).sort((a, b) => a - b);
      const p = v[Math.floor(v.length * 0.9)] || 5;
      return Math.max(2, Math.min(15, p));
    },
    fmt: (v) => fmt.pct(v, 2),
  },
  chg5: { label: '% thay đổi (5 phiên)', get: (r) => r.ret5, scale: 'div', domain: (rows) => Math.max(5, Math.min(40, percentileAbs(rows.map((r) => r.ret5), 0.9) || 15)), fmt: (v) => fmt.pct(v, 1) },
  score: { label: 'CW Score', get: (r) => r.score, scale: 'score', domain: () => [0, 100], fmt: (v) => fmt.n(v, 1) },
  premium: { label: 'Premium hoà vốn (%)', get: (r) => r.premium, scale: 'asc', domain: (rows) => [0, Math.max(10, Math.min(80, percentileAbs(rows.map((r) => r.premium), 0.9) || 40))], fmt: (v) => fmt.pct(v, 1, false) },
  iv: { label: 'IV (%)', get: (r) => (r.iv === null ? null : r.iv * 100), scale: 'blue', domain: (rows) => [15, Math.min(150, percentileAbs(rows.map((r) => (r.iv || 0) * 100), 0.9) || 80)], fmt: (v) => fmt.pct(v, 0, false) },
  ivVsHv: { label: 'IV − HV (%)', get: (r) => r.ivVsHv, scale: 'div', domain: (rows) => [0, Math.max(20, Math.min(120, percentileAbs(rows.map((r) => r.ivVsHv), 0.9) || 50))], fmt: (v) => fmt.pct(v, 0) },
  value: { label: 'Giá trị giao dịch TB', get: (r) => r.value20, scale: 'intensity', domain: () => null, fmt: (v) => fmt.vnd(v) },
  dte: { label: 'Số ngày còn lại', get: (r) => r.dte, scale: 'maturity', domain: () => [0, 365], fmt: (v) => fmt.dte(v) },
};

const SIZES = {
  value20: { label: 'Giá trị giao dịch TB 20P', get: (r) => Math.max(1, r.value20 || 0) },
  volume: { label: 'Khối lượng phiên', get: (r) => Math.max(1, r.vol || 0) },
  oi: { label: 'Giá trị lưu hành (ước tính)', get: (r) => Math.max(1, (r.value20 || 0) * 3) },
  equal: { label: 'Đều nhau', get: () => 1 },
};

const GROUPS = {
  none: { label: 'Không nhóm', key: () => 'Toàn bộ' },
  u: { label: 'Theo cổ phiếu cơ sở', key: (r) => r.u },
  iss: { label: 'Theo tổ chức phát hành', key: (r) => r.issName || r.iss },
  money: { label: 'Theo moneyness', key: (r) => r.money },
  rec: { label: 'Theo khuyến nghị', key: (r) => fmt.rec(r.rec) },
};

const state = { metric: 'chg1', size: 'value20', group: 'u', q: '', rec: '', minValue: 0, onlyLiquid: true };
let rootEl = null;

function percentileAbs(arr, p) {
  const v = arr.filter((x) => Number.isFinite(x)).map(Math.abs).sort((a, b) => a - b);
  if (!v.length) return 0;
  return v[Math.floor(v.length * p)];
}

function colorFor(value, metric) {
  if (!Number.isFinite(value)) return '#3a4657';
  const { scale, domain } = metric;
  if (scale === 'div') {
    const hi = Array.isArray(domain) ? domain[1] : domain;
    const t = Math.max(-1, Math.min(1, value / (hi || 1)));
    return t >= 0 ? mix('#1b2735', '#00c896', t) : mix('#1b2735', '#ff4d4d', -t);
  }
  if (scale === 'score') {
    const t = Math.max(0, Math.min(1, value / 100));
    return t < 0.45 ? mix('#8a2b2b', '#c9a227', t / 0.45) : mix('#c9a227', '#00c896', (t - 0.45) / 0.55);
  }
  if (scale === 'asc') {
    const [lo, hi] = domain;
    const t = Math.max(0, Math.min(1, (value - lo) / (hi - lo)));
    return mix('#00a87e', '#b03a2e', t);
  }
  if (scale === 'blue') {
    const [lo, hi] = domain;
    const t = Math.max(0, Math.min(1, (value - lo) / (hi - lo)));
    return mix('#123a5c', '#2e9bff', t);
  }
  if (scale === 'maturity') {
    const [lo, hi] = domain;
    const t = Math.max(0, Math.min(1, (value - lo) / (hi - lo)));
    return t < 0.5 ? mix('#a33a2a', '#b58b22', t / 0.5) : mix('#b58b22', '#1f7a5c', (t - 0.5) / 0.5);
  }
  if (scale === 'intensity') {
    const t = Math.max(0, Math.min(1, Math.log10(Math.max(1, value)) / 10));
    return mix('#123039', '#00b894', t);
  }
  return '#3a4657';
}

function mix(a, b, t) {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  const p = pa.map((v, i) => Math.round(v + (pb[i] - v) * Math.max(0, Math.min(1, t))));
  return '#' + p.map((v) => v.toString(16).padStart(2, '0')).join('');
}

function worstRatio(row, length) {
  const s = row.reduce((a, b) => a + b, 0);
  if (!s || !length) return Infinity;
  let mx = 0; let mn = Infinity;
  for (const r of row) { if (r > mx) mx = r; if (r < mn) mn = r; }
  return Math.max((length * length * mx) / (s * s), (s * s) / (length * length * mn));
}

function squarify(items, rect) {
  // items: [{area, ...}] đã sắp giảm dần
  const out = [];
  let remaining = items.slice();
  let r = { ...rect };
  while (remaining.length && r.w > 0.5 && r.h > 0.5) {
    const length = Math.min(r.w, r.h);
    const row = [remaining[0].area];
    let i = 1;
    while (i < remaining.length && worstRatio(row.concat([remaining[i].area]), length) <= worstRatio(row, length)) {
      row.push(remaining[i].area); i += 1;
    }
    const s = row.reduce((a, b) => a + b, 0);
    const slice = row.length;
    if (r.w >= r.h) {
      const stripW = s / r.h;
      let yy = r.y;
      for (let k = 0; k < slice; k++) {
        const hh = s ? (row[k] / s) * r.h : 0;
        out.push({ ...remaining[k], x: r.x, y: yy, w: stripW, h: hh });
        yy += hh;
      }
      r = { x: r.x + stripW, y: r.y, w: r.w - stripW, h: r.h };
    } else {
      const stripH = s / r.w;
      let xx = r.x;
      for (let k = 0; k < slice; k++) {
        const ww = s ? (row[k] / s) * r.w : 0;
        out.push({ ...remaining[k], x: xx, y: r.y, w: ww, h: stripH });
        xx += ww;
      }
      r = { x: r.x, y: r.y + stripH, w: r.w, h: r.h - stripH };
    }
    remaining = remaining.slice(slice);
  }
  return out;
}

function rowsFiltered() {
  let rows = data.activeRows();
  if (state.q) {
    const q = state.q.toLowerCase();
    rows = rows.filter((r) => r.t.toLowerCase().includes(q) || r.u.toLowerCase().includes(q) || (r.issName || '').toLowerCase().includes(q));
  }
  if (state.rec) rows = rows.filter((r) => r.rec === state.rec);
  if (state.onlyLiquid) rows = rows.filter((r) => (r.value20 || 0) >= 1e6);
  if (state.minValue) rows = rows.filter((r) => (r.value20 || 0) >= state.minValue);
  return rows;
}

function renderHeat() {
  const host = rootEl.querySelector('#heat-host');
  const stats = rootEl.querySelector('#heat-stats');
  if (!host) return;
  host.innerHTML = '';
  const rows = rowsFiltered();
  const metric = METRICS[state.metric];
  const size = SIZES[state.size];
  const group = GROUPS[state.group];
  const domain = metric.domain(rows);

  const width = host.clientWidth || 900;
  const height = Math.max(420, Math.min(720, Math.round(window.innerHeight * 0.62)));
  const inner = { x: 0, y: 0, w: width, h: height };

  const enriched = rows.map((r) => ({ row: r, weight: size.get(r), value: metric.get(r) }));
  const groupMap = new Map();
  for (const it of enriched) {
    const key = group.key(it.row);
    if (!groupMap.has(key)) groupMap.set(key, []);
    groupMap.get(key).push(it);
  }
  const groups = Array.from(groupMap.entries()).map(([key, items]) => ({
    key,
    items: items.sort((a, b) => b.weight - a.weight),
    weight: items.reduce((a, b) => a + b.weight, 0),
  })).sort((a, b) => b.weight - a.weight);

  const totalW = groups.reduce((a, b) => a + b.weight, 0) || 1;
  const areaScale = (width * height) / totalW;

  const tree = el('div', { class: 'treemap', style: `height:${height}px` });
  const placedGroups = state.group === 'none'
    ? [{ key: null, rect: inner, items: groups[0]?.items || [] }]
    : squarify(groups.map((g) => ({ ...g, area: g.weight * areaScale })), inner)
      .map((g) => ({ key: g.key, rect: { x: g.x, y: g.y, w: g.w, h: g.h }, items: g.items }));

  for (const g of placedGroups) {
    if (state.group !== 'none') {
      tree.appendChild(el('div', {
        style: `position:absolute;left:${g.rect.x}px;top:${g.rect.y}px;width:${g.rect.w}px;height:${g.rect.h}px;`
          + 'border:1px solid var(--border-2);border-radius:4px;pointer-events:none;box-sizing:border-box;',
      }, [
        el('div', {
          class: 'tiny',
          style: 'position:absolute;top:0;left:0;right:0;height:15px;overflow:hidden;padding:1px 4px;'
            + 'color:var(--text-2);background:var(--surface-2);font-family:var(--font-mono);',
          text: g.key,
        }),
      ]));
    }
    const pad = state.group === 'none' ? 0 : 16;
    const innerRect = {
      x: g.rect.x + 1, y: g.rect.y + pad + 1,
      w: Math.max(0, g.rect.w - 2), h: Math.max(0, g.rect.h - pad - 2),
    };
    if (innerRect.w < 2 || innerRect.h < 2) continue;
    const items = g.items;
    const gw = items.reduce((a, b) => a + b.weight, 0) || 1;
    const gscale = (innerRect.w * innerRect.h) / gw;
    const cells = squarify(items.map((it) => ({ ...it, area: it.weight * gscale })), innerRect);
    for (const cell of cells) {
      const r = cell.row;
      const val = cell.value;
      const color = colorFor(val, metric);
      const box = el('div', {
        class: 'tm-cell' + (cell.w < 46 || cell.h < 34 ? ' tiny-cell' : ''),
        style: `left:${cell.x}px;top:${cell.y}px;width:${cell.w}px;height:${cell.h}px;background:${color}`,
        title: `${r.t} · ${r.u}\n${metric.label}: ${metric.fmt(val)}\nGiá: ${fmt.px(r.price)} · ${fmt.pct(r.chg1, 2)}\n`
          + `Điểm: ${fmt.n(r.score, 1)} (${fmt.rec(r.rec)})\nPremium: ${fmt.pct(r.premium, 1, false)}\n`
          + `DTE: ${r.dte} · GT/phiên: ${fmt.vnd(r.value)}`,
        onclick: () => navigate(`#/cw/${r.t}`),
      }, [
        el('span', { class: 'tm-t', text: r.t }),
        el('span', { class: 'tm-v', text: metric.fmt(val) }),
        cell.h > 52 ? el('span', { class: 'tm-s', text: `${fmt.n(r.score, 0)} đ · ${r.money}` }) : null,
      ]);
      tree.appendChild(box);
    }
  }

  host.appendChild(tree);

  // stats
  const up = rows.filter((r) => (r.chg1 || 0) > 0).length;
  const down = rows.filter((r) => (r.chg1 || 0) < 0).length;
  const totalValue = rows.reduce((a, r) => a + (r.value20 || 0), 0);
  stats.innerHTML = '';
  for (const [k, v] of [
    ['Số CW', fmt.n(rows.length, 0)],
    ['Tăng / Giảm', `${up} / ${down}`],
    ['GT TB 20P', fmt.vnd(totalValue)],
    ['Nhóm', String(groupMap.size)],
  ]) {
    stats.appendChild(el('span', { html: `<span class="muted">${k}:</span> <b class="mono">${v}</b>` }));
  }

  // legend
  const legend = rootEl.querySelector('#heat-legend');
  legend.innerHTML = '';
  const [lo, hi] = metric.domain === METRICS.score.domain
    ? [0, 100]
    : (Array.isArray(domain) ? domain : [-Math.abs(domain || 1), Math.abs(domain || 1)]);
  const stops = Array.from({ length: 7 }, (_, i) => {
    const t = i / 6;
    const v = lo + (hi - lo) * t;
    return colorFor(metric.scale === 'div' ? (t * 2 - 1) * hi : v, metric);
  });
  const lowLabel = metric.scale === 'div' ? `−${fmt.n(hi, 1)}`
    : metric.scale === 'intensity' ? 'thấp' : metric.fmt(lo);
  const highLabel = metric.scale === 'div' ? `+${fmt.n(hi, 1)}`
    : metric.scale === 'intensity' ? 'cao' : metric.fmt(hi);
  legend.appendChild(el('span', { text: lowLabel }));
  legend.appendChild(el('div', {
    class: 'scale',
    style: `background:linear-gradient(90deg,${stops.join(',')})`,
  }));
  legend.appendChild(el('span', { text: highLabel }));
}

function control(label, selectEl) {
  return el('label', { class: 'field', style: 'min-width:170px' }, [el('span', { text: label }), selectEl]);
}

export default function heatmap(view) {
  view.appendChild(pageHead(
    'Heatmap thị trường',
    'Diện tích = quy mô giao dịch · Màu = chỉ số đang chọn · Nhấp vào ô để mở phân tích chi tiết',
    [el('button', { class: 'btn sm', text: '⇩ Ảnh chụp nhanh (CSV)', onclick: () => { exportRows(); } })],
  ));
  rootEl = el('div');

  const metricSel = el('select', {}, Object.entries(METRICS).map(([k, v]) => el('option', { value: k, text: v.label, selected: state.metric === k })));
  const sizeSel = el('select', {}, Object.entries(SIZES).map(([k, v]) => el('option', { value: k, text: v.label, selected: state.size === k })));
  const groupSel = el('select', {}, Object.entries(GROUPS).map(([k, v]) => el('option', { value: k, text: v.label, selected: state.group === k })));
  const recSel = el('select', {}, [
    el('option', { value: '', text: 'Tất cả khuyến nghị' }),
    ...['STRONG_BUY', 'BUY', 'HOLD', 'AVOID', 'HIGH_RISK'].map((r) => el('option', { value: r, text: fmt.rec(r), selected: state.rec === r })),
  ]);
  const search = el('input', { type: 'search', placeholder: 'Lọc mã / cơ sở / TCPH', value: state.q, style: 'height:28px' });
  const liquidChip = el('span', { class: 'chip' + (state.onlyLiquid ? ' on' : ''), text: 'Chỉ mã có GT ≥ 1 triệu/phiên' });

  metricSel.onchange = () => { state.metric = metricSel.value; renderHeat(); };
  sizeSel.onchange = () => { state.size = sizeSel.value; renderHeat(); };
  groupSel.onchange = () => { state.group = groupSel.value; renderHeat(); };
  recSel.onchange = () => { state.rec = recSel.value; renderHeat(); };
  search.oninput = () => { state.q = search.value.trim(); renderHeat(); };
  liquidChip.onclick = () => { state.onlyLiquid = !state.onlyLiquid; liquidChip.classList.toggle('on', state.onlyLiquid); renderHeat(); };

  rootEl.appendChild(el('div', { class: 'heat-controls' }, [
    control('Màu theo', metricSel),
    control('Kích thước theo', sizeSel),
    control('Nhóm', groupSel),
    control('Khuyến nghị', recSel),
    control('Tìm kiếm', search),
    el('div', { style: 'display:flex;gap:8px;align-items:center;padding-bottom:2px' }, [liquidChip]),
  ]));
  rootEl.appendChild(el('div', { class: 'heat-wrap' }, [el('div', { id: 'heat-host' })]));
  rootEl.appendChild(el('div', { id: 'heat-stats', class: 'heat-stats' }));
  rootEl.appendChild(el('div', { id: 'heat-legend', class: 'heat-legend' }));
  rootEl.appendChild(el('div', { class: 'notice', html: 'Màu xanh = diễn biến tích cực/điểm cao/rẻ hơn; đỏ = tiêu cực/điểm thấp/đắt hơn. '
    + 'Với IV, màu xanh chỉ thể hiện độ lớn, không hàm ý tốt/xấu. Kích thước theo giá trị giao dịch trung bình 20 phiên giúp tránh ảo giác thanh khoản từ một phiên đột biến.' }));

  view.appendChild(rootEl);
  requestAnimationFrame(renderHeat);
  window.addEventListener('resize', renderHeat, { passive: true });

  function exportRows() {
    const rows = rowsFiltered();
    import('../core.js').then(({ downloadCsv }) => {
      downloadCsv(`cw-heatmap-${data.meta?.asof || ''}.csv`, rows.map((r) => ({
        Ma: r.t, 'Co so': r.u, 'TCPH': r.issName, Gia: r.price, 'Chg1 (%)': r.chg1,
        'Ret5 (%)': r.ret5, 'Score': r.score, 'Rec': fmt.rec(r.rec), 'Premium (%)': r.premium,
        'DTE': r.dte, 'Gia tri 20P': r.value20,
      })));
      toast('Đã xuất CSV heatmap');
    });
  }
}
