/* Trang Thanh khoản — đo lường, cảnh báo và bằng chứng thực nghiệm */
import {
  el, fmt, data, pageHead, sectionHead, table, kpiCard, navigate, drawBars,
  onThemeChange, downloadCsv, toast,
} from '../core.js';

const F = {
  adv: (v) => fmt.vnd(v),
  pct: (v, d = 0) => (v === null || v === undefined ? '—' : fmt.pct(v, d, false)),
  num: (v, d = 2) => fmt.n(v, d),
};

const FLAG_DEFS = [
  { id: 'all', label: 'Tất cả' },
  { id: 'adv', label: 'ADV20 < 5 triệu' },
  { id: 'cov', label: 'Giao dịch < 50% phiên' },
  { id: 'dtl', label: 'Cần > 5 phiên để thoát 50 tr' },
  { id: 'range', label: 'Biên độ high-low > 12%' },
];

function advFlags() {
  const obj = data.liquidity?.universeFlags || {};
  return Object.values(obj).map((r) => ({
    ...r,
    // nhãn hành động: dùng để lọc nhanh, không phải khuyến nghị
    flagAdv: (r.adv20 ?? 0) > 0 && (r.adv20 ?? 0) < 5e6,
    flagCov: (r.covList ?? r.cov20 ?? 100) < 50 && (r.listedSessions ?? 99) >= 20,
    flagDtl: (r.dtl ?? 0) > 5,
    flagRange: (r.range20 ?? 0) > 12,
  }));
}

function renderDistribution(host) {
  const buckets = data.liquidity?.buckets || [];
  const dist = data.liquidity?.distribution || {};
  const adv = dist.adv || {};

  const card = el('div', { class: 'card' });
  card.appendChild(el('div', { class: 'card-title' }, [
    el('h3', { text: 'ADV20 và độ phủ giao dịch theo nhóm' }),
    el('span', { class: 'tiny muted', text: `${data.liquidity?.universe || 0} CW đang lưu hành` }),
  ]));

  const canvas = el('canvas');
  canvas.style.height = '180px';
  card.appendChild(el('div', { class: 'chart-box' }, [canvas]));
  host.appendChild(card);
  const paint = () => drawBars(canvas, {
    height: 180,
    values: buckets.map((b) => b.n),
    labels: buckets.map((b) => b.label.replace('triệu', 'tr').replace('dưới', '<').replace('trên', '>')),
    yFormat: (v) => fmt.n(v, 0),
    tipFormat: (v, i) => `${buckets[i].n} CW · ${buckets[i].sharePct}% vũ trụ · ${buckets[i].valuePct ?? '—'}% giá trị`,
  });
  requestAnimationFrame(paint);
  onThemeChange(paint);

  host.appendChild(el('div', { class: 'grid cols-3', style: 'margin-top:10px' }, [
    kpiCard({ label: 'ADV20 trung vị', value: F.adv(adv.median), sub: `P25 ${F.adv(adv.p25)} · P75 ${F.adv(adv.p75)}` }),
    kpiCard({ label: 'ADV20 P90', value: F.adv(adv.p90), sub: '10% CW thanh khoản nhất' }),
    kpiCard({ label: 'Độ phủ phiên trung vị', value: F.pct(dist.coverage?.median, 0), sub: 'tỷ lệ phiên có khớp lệnh / 20 phiên' }),
  ]));

  host.appendChild(table({
    compact: true,
    columns: [
      { key: 'label', title: 'Nhóm ADV20' },
      { key: 'n', title: 'Số CW', align: 'right' },
      { key: 'sharePct', title: '% vũ trụ', align: 'right', render: (r) => F.pct(r.sharePct, 1) },
      { key: 'valuePct', title: '% giá trị phiên', align: 'right', render: (r) => F.pct(r.valuePct, 1) },
      { key: 'medianCoverage', title: 'Độ phủ trung vị', align: 'right', render: (r) => F.pct(r.medianCoverage, 0) },
    ],
    rows: buckets,
    empty: 'Không có dữ liệu phân bố',
  }));
  host.appendChild(el('div', {
    class: 'tiny muted', style: 'margin-top:6px',
    text: 'ADV20 tính trên lịch giao dịch đầy đủ: phiên CW không khớp lệnh được tính là 0 VND. '
      + 'Vì vậy ADV20 thấp hơn "giá trị giao dịch bình quân" chỉ tính trên các phiên có giao dịch.',
  }));
}

function renderIssuers(host) {
  const rows = (data.liquidity?.byIssuer || []).map((r) => ({
    ...r,
    share: data.liquidity?.kpi?.top1Share != null ? null : null,
  }));
  const total = rows.reduce((s, r) => s + (r.value || 0), 0) || 1;
  const mapped = rows.map((r) => ({ ...r, valueShare: (r.value || 0) / total * 100 }));
  host.appendChild(sectionHead('Theo tổ chức phát hành', el('span', {
    class: 'tiny muted', text: 'giá trị giao dịch phiên gần nhất và ADV20 trung vị',
  })));
  host.appendChild(table({
    compact: true,
    onRowClick: (r) => navigate(`#/screener?iss=${encodeURIComponent(r.key)}`),
    columns: [
      { key: 'key', title: 'Tổ chức phát hành' },
      { key: 'n', title: 'Số CW', align: 'right' },
      { key: 'advMedian', title: 'ADV20 trung vị', align: 'right', render: (r) => F.adv(r.advMedian) },
      { key: 'coverageMedian', title: 'Độ phủ trung vị', align: 'right', render: (r) => F.pct(r.coverageMedian, 0) },
      { key: 'valueShare', title: '% giá trị phiên', align: 'right', render: (r) => F.pct(r.valueShare, 1) },
    ],
    rows: mapped,
    empty: 'Không có dữ liệu nhà phát hành',
  }));
}

function renderUnderlyings(host) {
  const rows = (data.liquidity?.byUnderlying || []).slice(0, 22);
  const total = rows.reduce((s, r) => s + (r.advSum || 0), 0) || 1;
  host.appendChild(sectionHead('Theo cổ phiếu cơ sở', el('span', {
    class: 'tiny muted', text: 'tổng ADV20 của các CW cùng cơ sở',
  })));
  host.appendChild(table({
    compact: true,
    columns: [
      { key: 'key', title: 'Cơ sở' },
      { key: 'n', title: 'Số CW', align: 'right' },
      { key: 'advMedian', title: 'ADV20 trung vị / CW', align: 'right', render: (r) => F.adv(r.advMedian) },
      { key: 'advSum', title: 'Tổng ADV20', align: 'right', render: (r) => F.adv(r.advSum) },
      { key: 'share', title: '% tổng ADV', align: 'right', render: (r) => F.pct((r.advSum || 0) / total * 100, 1) },
    ],
    rows,
    empty: 'Không có dữ liệu cổ phiếu cơ sở',
  }));
}

function renderFlags(host) {
  const all = advFlags().sort((a, b) => (a.adv20 ?? 0) - (b.adv20 ?? 0));
  let filter = 'all';
  const wrap = el('div');
  const chips = el('div', { class: 'preset-row', style: 'margin-bottom:10px' });
  const body = el('div');

  const matches = (r) => {
    switch (filter) {
      case 'adv': return r.flagAdv;
      case 'cov': return r.flagCov;
      case 'dtl': return r.flagDtl;
      case 'range': return r.flagRange;
      default: return r.flagAdv || r.flagCov || r.flagDtl || r.flagRange;
    }
  };

  const paint = () => {
    const rows = all.filter(matches);
    body.innerHTML = '';
    body.appendChild(el('div', { class: 'result-count', text: `${rows.length} CW cần lưu ý thanh khoản` }));
    body.appendChild(table({
      compact: true,
      onRowClick: (r) => navigate(`#/cw/${r.t}`),
      columns: [
        { key: 't', title: 'Mã', render: (r) => el('span', { class: 'tbl-ticker', text: r.t }) },
        { key: 'u', title: 'Cơ sở' },
        { key: 'adv20', title: 'ADV20', align: 'right', render: (r) => F.adv(r.adv20) },
        { key: 'cov20', title: 'Phủ từ niêm yết', align: 'right', render: (r) => F.pct(r.covList ?? r.cov20, 0) },
        { key: 'zero20', title: 'Phiên trắng', align: 'right', render: (r) => fmt.n(r.zero20, 0) },
        { key: 'amihud', title: 'Amihud (%/tỷ)', align: 'right', render: (r) => F.num(r.amihud, 2) },
        { key: 'range20', title: 'Biên độ HL', align: 'right', render: (r) => F.pct(r.range20, 1) },
        { key: 'dtl', title: 'DTL 50tr', align: 'right', render: (r) => (r.dtl == null ? '—' : `${fmt.n(r.dtl, 1)} phiên`) },
        { key: 'score', title: 'Điểm', align: 'right', render: (r) => fmt.n(r.score, 1) },
        { key: 'rec', title: 'Khuyến nghị' },
      ],
      rows,
      empty: 'Không có CW nào vi phạm ngưỡng cảnh báo.',
    }));
  };

  FLAG_DEFS.forEach((f) => chips.appendChild(el('button', {
    class: 'chip' + (f.id === filter ? ' on' : ''),
    text: f.label,
    onclick: (ev) => {
      filter = f.id;
      chips.querySelectorAll('.chip').forEach((c) => c.classList.remove('on'));
      ev.currentTarget.classList.add('on');
      paint();
    },
  })));

  wrap.appendChild(sectionHead('Cảnh báo thanh khoản', el('button', {
    class: 'btn sm ghost', text: '⇩ CSV',
    onclick: () => {
      const rows = all.filter(matches).map((r) => ({
        Ma: r.t, CoSo: r.u, TCPH: r.iss, ADV20: r.adv20, DoPhu20: r.cov20, PhuTuNiemYet: r.covList,
        PhienTrang: r.zero20, Amihud: r.amihud, BienDoHL: r.range20, PhuTuNiemYet: r.covList,
        DTL50tr: r.dtl, Nhom: r.bucket, Diem: r.score, KhuyenNghi: r.rec,
      }));
      downloadCsv(`cw-thanh-khoan-${data.meta?.asof || ''}.csv`, rows);
      toast(`Đã xuất ${rows.length} dòng`);
    },
  })));
  wrap.append(chips, body);
  host.appendChild(wrap);
  paint();
}

function renderIdle(host) {
  const idle = data.liquidity?.idle || [];
  if (!idle.length) return;
  host.appendChild(sectionHead('Niêm yết nhưng không giao dịch', el('span', {
    class: 'tiny muted', text: `không có khớp lệnh trong 14 phiên gần nhất — ${idle.length} CW`,
  })));
  host.appendChild(el('div', { class: 'notice warn', html:
    `Có <b>${idle.length}/${data.liquidity?.kpi?.listedActive || '—'}</b> CW đang niêm yết nhưng không phát sinh giao dịch `
    + 'trong 14 phiên gần nhất, nên không xuất hiện trong snapshot khuyến nghị. '
    + 'Đây là nhóm rủi ro thanh khoản cao nhất: giá trên bảng có thể không khớp được ở quy mô thực tế.' }));
  host.appendChild(table({
    compact: true,
    onRowClick: (r) => navigate(`#/cw/${r.t}`),
    columns: [
      { key: 't', title: 'Mã', render: (r) => el('span', { class: 'tbl-ticker', text: r.t }) },
      { key: 'u', title: 'Cơ sở' },
      { key: 'iss', title: 'TCPH' },
      { key: 'lastDate', title: 'Phiên giao dịch gần nhất', render: (r) => fmt.date(r.lastDate) },
      { key: 'daysSince', title: 'Số ngày kể từ đó', align: 'right', render: (r) => (r.daysSince == null ? '—' : `${r.daysSince} ngày`) },
    ],
    rows: idle.slice(0, 80),
    empty: 'Không có CW nào rơi vào trạng thái này.',
  }));
  if (idle.length > 80) {
    host.appendChild(el('div', { class: 'tiny muted', text: `Hiển thị 80/${idle.length}; xuất CSV ở đầu trang để xem đủ.` }));
  }
}

function renderEvidence(host) {
  const bt = data.backtest;
  const sec = el('div');
  sec.appendChild(sectionHead('Bằng chứng thực nghiệm', el('span', {
    class: 'tiny muted', text: '20 phiên nắm giữ · đã trừ chi phí 2 chiều',
  })));

  const quint = bt?.liquidity?.quintiles || [];
  if (!quint.length) {
    sec.appendChild(el('div', { class: 'empty', text: 'Chưa có dữ liệu backtest thanh khoản trong artifact hiện tại.' }));
    host.appendChild(sec);
    return;
  }

  const canvas = el('canvas');
  canvas.style.height = '190px';
  const chartCard = el('div', { class: 'card' }, [
    el('div', { class: 'card-title' }, [
      el('h3', { text: 'Lợi nhuận 20 phiên theo nhóm ADV20 (toàn vũ trụ)' }),
      el('span', { class: 'tiny muted', text: 'không chỉ top-5 theo điểm' }),
    ]),
    el('div', { class: 'chart-box' }, [canvas]),
  ]);
  sec.appendChild(chartCard);
  const paint = () => drawBars(canvas, {
    height: 190,
    values: quint.map((q) => q.avg_ret_pct),
    labels: quint.map((q) => `Q${q.quintile}`),
    colors: quint.map((q) => (q.avg_ret_pct >= 0
      ? getComputedStyle(document.documentElement).getPropertyValue('--up').trim()
      : getComputedStyle(document.documentElement).getPropertyValue('--down').trim())),
    yFormat: (v) => `${fmt.n(v, 0)}%`,
    tipFormat: (v, i) => `${quint[i].n} quan sát · ADV ${F.adv(quint[i].advLow)}–${F.adv(quint[i].advHigh)}`
      + ` · thắng ${quint[i].win_rate_pct}%`,
  });
  requestAnimationFrame(paint);
  onThemeChange(paint);

  sec.appendChild(table({
    compact: true,
    columns: [
      { key: 'quintile', title: 'Nhóm', render: (r) => `Q${r.quintile}` },
      { key: 'advLow', title: 'ADV20 từ', align: 'right', render: (r) => F.adv(r.advLow) },
      { key: 'advHigh', title: 'đến', align: 'right', render: (r) => F.adv(r.advHigh) },
      { key: 'n', title: 'Quan sát', align: 'right' },
      { key: 'avg_ret_pct', title: 'TB 20 phiên', align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_ret_pct), text: fmt.pct(r.avg_ret_pct, 2) }) },
      { key: 'median_ret_pct', title: 'Trung vị', align: 'right', render: (r) => fmt.pct(r.median_ret_pct, 2) },
      { key: 'win_rate_pct', title: 'Tỷ lệ lãi', align: 'right', render: (r) => F.pct(r.win_rate_pct, 1) },
    ],
    rows: quint,
  }));

  const gates = bt?.liquidity?.gates || [];
  if (gates.length) {
    sec.appendChild(el('div', { class: 'hr' }));
    sec.appendChild(el('div', { class: 'tiny muted', style: 'margin-bottom:6px', text: 'Nếu chỉ mua CW có ADV20 ≥ ngưỡng (phần còn lại bị loại):' }));
    sec.appendChild(table({
      compact: true,
      columns: [
        { key: 'adv', title: 'Ngưỡng ADV20', align: 'right', render: (r) => F.adv(r.adv) },
        { key: 'share_pct', title: '% quan sát còn lại', align: 'right', render: (r) => F.pct(r.share_pct, 1) },
        { key: 'n', title: 'Quan sát', align: 'right' },
        { key: 'avg_ret_pct', title: 'TB 20 phiên', align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_ret_pct), text: fmt.pct(r.avg_ret_pct, 2) }) },
        { key: 'win_rate_pct', title: 'Tỷ lệ lãi', align: 'right', render: (r) => F.pct(r.win_rate_pct, 1) },
      ],
      rows: gates,
    }));
  }

  const filters = (bt?.filter_sensitivity || []).filter((f) => /ADV|Amihud|biên độ|Độ phủ/i.test(f.filter));
  if (filters.length) {
    sec.appendChild(el('div', { class: 'hr' }));
    sec.appendChild(el('div', { class: 'tiny muted', style: 'margin-bottom:6px', text: 'Chiến lược top-5 với bộ lọc thanh khoản (so với dòng "Cơ sở"):' }));
    sec.appendChild(table({
      compact: true,
      columns: [
        { key: 'filter', title: 'Bộ lọc' },
        { key: 'n_trades', title: 'Số lệnh', align: 'right' },
        { key: 'avg_trade_ret_pct', title: 'TB/lệnh', align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_trade_ret_pct), text: fmt.pct(r.avg_trade_ret_pct, 2) }) },
        { key: 'win_rate_pct', title: 'Tỷ lệ lãi', align: 'right', render: (r) => F.pct(r.win_rate_pct, 1) },
        { key: 'profit_factor', title: 'Profit factor', align: 'right', render: (r) => fmt.n(r.profit_factor, 2) },
        { key: 'total_return_pct', title: 'Tổng', align: 'right', render: (r) => el('span', { class: fmt.cls(r.total_return_pct), text: fmt.pct(r.total_return_pct, 1) }) },
      ],
      rows: filters,
    }));
  }

  const corr = data.liquidity?.rankCorr || {};
  const corrKeys = Object.keys(corr);
  if (corrKeys.length) {
    sec.appendChild(el('div', { class: 'hr' }));
    sec.appendChild(el('div', { class: 'tiny muted', style: 'margin-bottom:6px', text: 'Tương quan hạng trong mặt cắt hiện tại (không phải dự báo):' }));
    sec.appendChild(table({
      compact: true,
      columns: [
        { key: 'pair', title: 'Cặp biến', render: (r) => r.pair.replace('~', ' × ') },
        { key: 'value', title: 'Spearman', align: 'right', render: (r) => el('span', { class: fmt.cls(r.value), text: fmt.n(r.value, 3) }) },
      ],
      rows: corrKeys.map((k) => ({ pair: k, value: corr[k] })),
    }));
  }

  sec.appendChild(el('div', { class: 'notice warn', html:
    '<b>Đọc đúng con số:</b> lợi nhuận trung bình của <i>mọi</i> nhóm đều âm trong giai đoạn 2023–2026 — '
    + 'đây là đặc điểm của thị trường CW Việt Nam (theta + premium cao), không phải lỗi mô hình. '
    + 'Thanh khoản <b>không tạo ra alpha dương</b>; nó làm giảm mức lỗ kỳ vọng và đặc biệt giảm rủi ro '
    + 'không thoát được vị thế. Xem thêm trang Backtest và tài liệu RESEARCH_LIQUIDITY.md.' }));
  host.appendChild(sec);
}

function renderMethod(host) {
  const t = data.liquidity?.thresholds || {};
  host.appendChild(sectionHead('Cách đo và giới hạn', el('span', { class: 'tiny muted', text: 'định nghĩa dùng xuyên suốt hệ thống' })));
  host.appendChild(table({
    compact: true,
    columns: [
      { key: 'name', title: 'Chỉ tiêu' },
      { key: 'def', title: 'Định nghĩa' },
      { key: 'use', title: 'Dùng để' },
    ],
    rows: [
      { name: 'ADV20 / ADV5', def: 'Tổng giá trị giao dịch 20/5 phiên ÷ số phiên, trên lịch đầy đủ (phiên trắng = 0)', use: 'Độ sâu thị trường' },
      { name: 'Độ phủ (coverage20)', def: '% số phiên thực sự có khớp lệnh trong 20 phiên', use: 'Rủi ro không thoát được hàng' },
      { name: 'Amihud20', def: 'Trung vị |lợi suất ngày| ÷ giá trị giao dịch × 1e9 (% giá trên 1 tỷ VND)', use: 'Tác động giá' },
      { name: 'Biên độ high-low', def: 'Trung vị (high − low)/close trong 20 phiên', use: 'Proxy chênh lệch mua-bán / trượt giá' },
      { name: 'Turnover20', def: 'Khối lượng ÷ lượng CW lưu hành, bình quân 20 phiên', use: 'Mức độ sang tay' },
      { name: 'DTL', def: `Vị thế ÷ (${Math.round((t.participation || 0.2) * 100)}% × ADV20)`, use: 'Số phiên cần để thoát hàng' },
      { name: 'Tác động ước tính', def: `η·σ·√(Q/ADV) với η = ${t.impactEta ?? 0.1}, Q = ${fmt.vnd(t.positionVnd || 5e7)}`, use: 'Chi phí trượt giá' },
    ],
  }));
  host.appendChild(el('div', { class: 'notice', html:
    '<b>Quy định thị trường ảnh hưởng trực tiếp:</b> CW có bước giá 10 VND và giá sàn 10 VND; lô khớp tối thiểu 100 CW; '
    + 'tổ chức phát hành có nghĩa vụ yết giá trong 5 phút khi lệnh một chiều/không có lệnh/chênh lệch >5%, khối lượng mỗi lệnh tối thiểu 100 CW, '
    + 'và được miễn khi giá lý thuyết ≤ 10 VND. Vì vậy CW giá rất thấp thường "có giá mà không có thanh khoản" — '
    + 'đúng nhóm mà cảnh báo ADV20/độ phủ nhắm tới.' }));
  host.appendChild(el('div', { class: 'notice warn', html:
    '<b>Giới hạn dữ liệu:</b> (1) Không có dữ liệu sổ lệnh/bid-ask, nên chênh lệch mua-bán chỉ được suy ra từ biên độ high-low; '
    + '(2) volume bao gồm giao dịch của tổ chức tạo lập thị trường — có thể thổi phồng độ sâu thực tế; '
    + '(3) DTL giả định tham gia đều 20% ADV mỗi phiên và thanh khoản không xấu đi; '
    + '(4) vũ trụ chỉ gồm CW còn niêm yết trong dữ liệu, các CW huỷ niêm yết sớm có thể không được phản ánh đầy đủ.' }));
}

function renderCalculator(host) {
  const rows = data.activeRows().filter((r) => (r.adv20 ?? 0) > 0);
  const sorted = rows.slice().sort((a, b) => (a.adv20 ?? 0) - (b.adv20 ?? 0));
  const out = el('div', { class: 'grid cols-3', style: 'margin-top:10px' });

  const select = el('select', { class: 'input', style: 'min-width:220px' });
  for (const r of sorted) {
    select.appendChild(el('option', { value: r.t, text: `${r.t} · ${r.u} · ADV20 ${fmt.vnd(r.adv20)}` }));
  }
  const posInput = el('input', { class: 'input', type: 'number', value: '50', min: '1', step: '10', style: 'width:120px' });

  const calc = () => {
    const r = data.row(select.value);
    const pos = Number(posInput.value) * 1e6;
    out.innerHTML = '';
    if (!r || !(pos > 0)) return;
    const participation = data.liquidity?.thresholds?.participation || 0.2;
    const eta = data.liquidity?.thresholds?.impactEta || 0.1;
    const adv = r.adv20 || 0;
    const sigma = (r.atrPct ? r.atrPct / 100 : 0.05);
    const dtl = adv > 0 ? pos / (participation * adv) : null;
    const impact = adv > 0 ? eta * sigma * Math.sqrt(pos / adv) * 100 : null;
    const days = Math.ceil(dtl ?? 0);
    out.append(
      kpiCard({ label: 'Số phiên cần để thoát', value: dtl == null ? '—' : `${fmt.n(dtl, 1)} phiên`, sub: `ở mức ${Math.round(participation * 100)}% ADV20 mỗi phiên` }),
      kpiCard({ label: 'Tác động giá ước tính', value: impact == null ? '—' : fmt.pct(impact, 2, false), sub: `η=${eta} · σ=${fmt.pct(sigma * 100, 1, false)} · √(Q/ADV)` }),
      kpiCard({ label: 'Nếu thoát trong 1 phiên', value: fmt.pct(impact == null ? null : impact * Math.sqrt(Math.max(1, dtl)), 2, false), sub: 'tác động tăng theo căn bậc hai của khối lượng' }),
    );
    const verdict = dtl == null ? '—'
      : dtl <= 1 ? 'Vị thế nhỏ so với thanh khoản: có thể thoát trong phiên.'
        : dtl <= 5 ? `Cần khoảng ${days} phiên, chia nhỏ lệnh để tránh đẩy giá.`
          : `Rất khó thoát: ${fmt.n(dtl, 0)} phiên ở mức 20% ADV. Nên giảm quy mô vị thế.`;
    out.appendChild(el('div', { class: 'notice', style: 'grid-column:1/-1', text: verdict }));
    if ((r.covList ?? r.cov20 ?? 100) < 60 && (r.listedSessions ?? 99) >= 20) {
      out.appendChild(el('div', { class: 'notice warn', style: 'grid-column:1/-1', html:
        `Mã này chỉ giao dịch <b>${fmt.pct(r.covList ?? r.cov20, 0, false)}</b> số phiên kể từ khi niêm yết — `
        + 'DTL ở trên là cận dưới lạc quan, thực tế có thể lâu hơn nhiều.' }));
    }
  };

  select.addEventListener('change', calc);
  posInput.addEventListener('input', calc);
  host.appendChild(sectionHead('Máy tính thoát vị thế', el('span', {
    class: 'tiny muted', text: 'công thức công bố, tính trực tiếp từ ADV20 của phiên dữ liệu',
  })));
  host.appendChild(el('div', { class: 'filter-row' }, [
    el('span', { class: 'tiny muted', text: 'Mã CW' }), select,
    el('span', { class: 'tiny muted', text: 'Vị thế (triệu VND)' }), posInput,
  ]));
  host.appendChild(out);
  if (sorted.length) {
    select.value = sorted[sorted.length - 1].t;
    calc();
  }
}

export default async function liquidityPage(view) {
  if (!data.liquidity) {
    try { data.liquidity = await (await fetch('data/liquidity.json')).json(); } catch { /* ignore */ }
  }
  // backtest.json chỉ tải khi cần (98 KB) — trang này dùng khối `liquidity` bên trong
  try { await data.backtestData(); } catch { /* ignore */ }
  const liq = data.liquidity;
  view.appendChild(pageHead(
    'Thanh khoản',
    `Độ sâu, độ phủ phiên, tác động giá và rủi ro thoát vị thế · số liệu phiên <b>${data.meta?.asofLabel || '—'}</b>`,
    [el('button', {
      class: 'btn sm', text: '⇩ Xuất toàn bộ',
      onclick: () => {
        const rows = advFlags().map((r) => ({
          Ma: r.t, CoSo: r.u, TCPH: r.iss, ADV20: r.adv20, DoPhu20: r.cov20,
          PhienTrang: r.zero20, Amihud: r.amihud, BienDoHL: r.range20,
          DTL50tr: r.dtl, Nhom: r.bucket, Diem: r.score, KhuyenNghi: r.rec,
        }));
        downloadCsv(`cw-thanh-khoan-day-du-${data.meta?.asof || ''}.csv`, rows);
        toast(`Đã xuất ${rows.length} dòng`);
      },
    })],
  ));

  if (!liq) {
    view.appendChild(el('div', { class: 'empty', text: 'Chưa có data/liquidity.json. Chạy python -m cwintel.build để tạo artifact này.' }));
    return;
  }

  const k = liq.kpi || {};
  const flagged = k.flagged || {};
  view.appendChild(el('div', { class: 'grid kpi' }, [
    kpiCard({ label: 'ADV20 trung vị', value: F.adv(k.advMedian), sub: `trung bình ${F.adv(k.advMean)}` }),
    kpiCard({ label: 'Độ phủ phiên 20P', value: F.pct(k.coverageMedian, 0), sub: `${k.shareCoverageBelow50 ?? '—'}% CW giao dịch < 50% phiên` }),
    kpiCard({
      label: 'CW thanh khoản rất thấp', value: fmt.n(flagged.advBelow5m, 0),
      sub: `ADV20 < 5 triệu VND/phiên · ${k.idleCount ?? '—'} CW không giao dịch 14 phiên`,
    }),
    kpiCard({ label: 'Amihud20 trung vị', value: F.num(k.amihudMedian, 2), sub: '% giá / 1 tỷ VND giao dịch' }),
    kpiCard({ label: 'Biên độ high-low 20P', value: F.pct(k.rangeMedian, 1), sub: 'proxy chênh lệch mua-bán' }),
    kpiCard({ label: 'Tập trung giá trị', value: F.pct(k.top10Share, 1), sub: `top-1 ${F.pct(k.top1Share, 1)} · top-5 ${F.pct(k.top5Share, 1)}` }),
  ]));

  const dist = el('div');
  renderDistribution(dist);
  view.appendChild(dist);

  const iss = el('div', { class: 'section' });
  renderIssuers(iss);
  view.appendChild(iss);

  const und = el('div', { class: 'section' });
  renderUnderlyings(und);
  view.appendChild(und);

  const flags = el('div', { class: 'section' });
  renderFlags(flags);
  view.appendChild(flags);

  const idle = el('div', { class: 'section' });
  renderIdle(idle);
  view.appendChild(idle);

  const calc = el('div', { class: 'section' });
  renderCalculator(calc);
  view.appendChild(calc);

  const ev = el('div', { class: 'section' });
  renderEvidence(ev);
  view.appendChild(ev);

  const method = el('div', { class: 'section' });
  renderMethod(method);
  view.appendChild(method);
}
