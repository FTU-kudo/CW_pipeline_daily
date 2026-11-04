/* Trang Tổng quan thị trường */
import {
  el, fmt, data, pageHead, kpiCard, sectionHead, scoreCell, table,
  drawLine, drawBars, onThemeChange, navigate, downloadCsv, toast,
} from '../core.js';

let state = { topTab: 'gainers' };

const TOP_TABS = [
  ['gainers', 'Tăng mạnh nhất'],
  ['losers', 'Giảm mạnh nhất'],
  ['value', 'Giá trị giao dịch'],
  ['liquidity_improving', 'Thanh khoản cải thiện'],
  ['unusual', 'Biến động bất thường'],
];

function topTable(kind) {
  const rows = data.market?.top?.[kind] || [];
  return table({
    compact: true,
    rows,
    empty: 'Không có dữ liệu',
    onRowClick: (r) => navigate(`#/cw/${r.t}`),
    columns: [
      { key: 't', title: 'Mã', render: (r) => el('span', { class: 'tbl-ticker', text: r.t }) },
      { key: 'u', title: 'Cơ sở' },
      { key: 'chg', title: '%Ngày', align: 'right', render: (r) => el('span', { class: fmt.cls(r.chg), text: fmt.pct(r.chg, 2) }) },
      { key: 'price', title: 'Giá', align: 'right', render: (r) => fmt.px(r.price) },
      {
        key: kind === 'value' || kind === 'liquidity_improving' ? 'value' : 'chg',
        title: 'GT/phiên',
        align: 'right',
        render: (r) => fmt.vnd(r.value),
        sortValue: (r) => r.value,
      },
      { key: 'score', title: 'Điểm', align: 'right', render: (r) => scoreCell(r.score) },
    ],
  });
}

function distributionCard() {
  const box = el('div', { class: 'card' });
  box.appendChild(el('div', { class: 'card-title' }, [el('h3', { text: 'Phân bố điểm CW (active)' })]));
  const canvas = el('canvas', { style: 'height:150px' });
  const holder = el('div', { class: 'chart-box', style: 'height:150px' }, [canvas]);
  box.appendChild(holder);
  const labels = ['0–30', '30–45', '45–65', '65–80', '80–100'];
  const values = data.market?.distributions?.score || [];
  const colors = ['var(--down)', '#ff8a3d', 'var(--warn)', 'var(--accent-2)', 'var(--up)'];
  requestAnimationFrame(() => drawBars(canvas, {
    height: 150, labels, values,
    colors: colors.map((c) => (c.startsWith('var(') ? getComputedStyle(document.documentElement).getPropertyValue(c.slice(4, -1)).trim() : c)),
    tipFormat: (v, i) => `${v} CW`,
  }));
  onThemeChange(() => drawBars(canvas, {
    height: 150, labels, values,
    colors: colors.map((c) => (c.startsWith('var(') ? getComputedStyle(document.documentElement).getPropertyValue(c.slice(4, -1)).trim() : c)),
    tipFormat: (v) => `${v} CW`,
  }));
  return box;
}

function premiumDistCard() {
  const box = el('div', { class: 'card' });
  box.appendChild(el('div', { class: 'card-title' }, [el('h3', { text: 'Phân bố premium hoà vốn (%)' })]));
  const canvas = el('canvas', { style: 'height:150px' });
  box.appendChild(el('div', { class: 'chart-box', style: 'height:150px' }, [canvas]));
  const labels = ['<0', '0–10', '10–20', '20–30', '30–50', '>50'];
  const values = data.market?.distributions?.premium || [];
  const paint = () => drawBars(canvas, { height: 150, labels, values, tipFormat: (v) => `${v} CW` });
  requestAnimationFrame(paint);
  onThemeChange(paint);
  return box;
}

function issuerTable() {
  const rows = data.market?.by_issuer || [];
  return table({
    compact: true,
    rows,
    columns: [
      {
        key: 'key',
        title: 'Tổ chức phát hành',
        render: (r) => el('span', { text: fmt.issuer(r.key) }),
        sortValue: (r) => r.count,
      },
      { key: 'count', title: 'Số CW', align: 'right' },
      { key: 'up', title: 'Tăng', align: 'right', render: (r) => el('span', { class: 'up', text: r.up }) },
      { key: 'down', title: 'Giảm', align: 'right', render: (r) => el('span', { class: 'down', text: r.down }) },
      { key: 'value', title: 'GT/phiên', align: 'right', render: (r) => fmt.vnd(r.value), sortValue: (r) => r.value },
      { key: 'avgPremium', title: 'Premium', align: 'right', render: (r) => fmt.pct(r.avgPremium, 1, false) },
      { key: 'avgScore', title: 'Điểm TB', align: 'right', render: (r) => fmt.n(r.avgScore, 1) },
    ],
  });
}

function underlyingTable() {
  const items = data.underlyings?.items || [];
  const rows = items.slice(0, 14);
  return table({
    compact: true,
    rows,
    onRowClick: (r) => navigate(`#/screener?u=${encodeURIComponent(r.u)}`),
    columns: [
      { key: 'u', title: 'Cơ sở', render: (r) => el('span', { class: 'tbl-ticker', text: r.u }) },
      { key: 'close', title: 'Giá', align: 'right', render: (r) => fmt.px(r.close) },
      { key: 'ret1', title: '%Ngày', align: 'right', render: (r) => el('span', { class: fmt.cls(r.ret1), text: fmt.pct(r.ret1, 2) }) },
      { key: 'ret21', title: '%21P', align: 'right', render: (r) => el('span', { class: fmt.cls(r.ret21), text: fmt.pct(r.ret21, 1) }) },
      { key: 'rsi', title: 'RSI', align: 'right', render: (r) => fmt.n(r.rsi, 0) },
      { key: 'hv252', title: 'HV', align: 'right', render: (r) => fmt.pct((r.hv252 || 0) * 100, 0, false) },
      { key: 'nCw', title: 'Số CW', align: 'right' },
      { key: 'bestCw', title: 'CW tốt nhất', render: (r) => (r.bestCw ? el('span', { class: 'tbl-ticker', text: r.bestCw }) : '—') },
      { key: 'bestScore', title: 'Điểm', align: 'right', render: (r) => scoreCell(r.bestScore) },
    ],
  });
}

function breadthCharts() {
  const wrap = el('div', { class: 'grid cols-2' });
  const breadth = data.market?.breadth || [];
  const labels = breadth.map((b) => fmt.date(b.date).slice(0, 5));

  const c1 = el('canvas');
  const box1 = el('div', { class: 'card' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Độ rộng thị trường — số CW tăng/giảm' })]),
    el('div', { class: 'chart-box' }, [c1]),
    el('div', { class: 'legend-inline', style: 'margin-top:6px' }, [
      el('span', { html: '<i style="background:var(--up)"></i>Tăng giá' }),
      el('span', { html: '<i style="background:var(--down)"></i>Giảm giá' }),
    ]),
  ]);
  const c2 = el('canvas');
  const box2 = el('div', { class: 'card' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Tổng giá trị giao dịch CW theo phiên' })]),
    el('div', { class: 'chart-box' }, [c2]),
  ]);

  const paint = () => {
    drawLine(c1, {
      height: 190, labels,
      series: [
        { name: 'Tăng', values: breadth.map((b) => b.up), color: getComputedStyle(document.documentElement).getPropertyValue('--up').trim() },
        { name: 'Giảm', values: breadth.map((b) => b.down), color: getComputedStyle(document.documentElement).getPropertyValue('--down').trim() },
      ],
      zeroLine: true, yFormat: (v) => fmt.n(v, 0),
    });
    drawBars(c2, {
      height: 190, labels,
      values: breadth.map((b) => b.value),
      colors: breadth.map(() => getComputedStyle(document.documentElement).getPropertyValue('--accent-2').trim()),
      yFormat: (v) => fmt.compact(v),
      tipFormat: (v) => fmt.vnd(v),
    });
  };
  requestAnimationFrame(paint);
  onThemeChange(paint);
  wrap.append(box1, box2);
  return wrap;
}

export default function overview(view) {
  const k = data.market?.kpi || {};
  const meta = data.meta || {};
  const breadth = data.market?.breadth || [];
  const lastBreadth = breadth[breadth.length - 1];
  const prevBreadth = breadth[breadth.length - 2];

  view.appendChild(pageHead(
    'Tổng quan thị trường chứng quyền',
    `Phiên dữ liệu <b>${esc(meta.asofLabel || '—')}</b> · ${k.active || 0} CW đang giao dịch · ${k.underlyings || 0} cổ phiếu cơ sở · ${k.issuers || 0} tổ chức phát hành`,
    [
      el('button', {
        class: 'btn sm',
        text: '⇩ Xuất tổng quan (CSV)',
        onclick: () => {
          const rows = (data.market?.by_underlying || []).map((r) => ({
            'Cổ phiếu cơ sở': r.key, 'Số CW': r.count, 'Giá trị/phiên (VND)': r.value,
            'Tăng': r.up, 'Giảm': r.down, 'Premium TB (%)': r.avgPremium, 'Điểm TB': r.avgScore,
          }));
          downloadCsv(`cw-market-${meta.asof || ''}.csv`, rows);
          toast('Đã xuất CSV');
        },
      }),
      el('button', { class: 'btn sm primary', text: 'Mở Screener →', onclick: () => navigate('#/screener') }),
    ],
  ));

  // KPI
  const kpi = el('div', { class: 'grid kpi section' }, [
    kpiCard({ label: 'CW đang giao dịch', value: fmt.n(k.active, 0), sub: `${fmt.n(k.expired, 0)} đã đáo hạn · tổng ${fmt.n(k.total, 0)}` }),
    kpiCard({
      label: 'Tăng / Giảm',
      value: `${fmt.n(k.up, 0)} / ${fmt.n(k.down, 0)}`,
      sub: lastBreadth ? `phiên trước: ${prevBreadth ? `${prevBreadth.up}/${prevBreadth.down}` : '—'}` : '',
      delta: k.up + k.down ? fmt.pct((k.up / Math.max(1, k.up + k.down)) * 100, 0, false) : '',
      deltaClass: (k.up || 0) >= (k.down || 0) ? 'up' : 'down',
    }),
    kpiCard({ label: 'Giá trị giao dịch/phiên', value: fmt.vnd(k.totalValue), sub: 'tổng giá trị các CW có giao dịch' }),
    kpiCard({ label: 'Khối lượng/phiên', value: fmt.compact(k.totalVolume), sub: 'tổng khối lượng khớp lệnh' }),
    kpiCard({
      label: 'ITM / ATM / OTM',
      value: `${k.itm || 0} / ${k.atm || 0} / ${k.otm || 0}`,
      sub: 'theo strike đã điều chỉnh',
    }),
    kpiCard({ label: 'Thanh khoản cao', value: fmt.n(k.liquid, 0), sub: '≥ 300 triệu VND/phiên (TB 20P)' }),
    kpiCard({
      label: 'Tín hiệu tích cực',
      value: fmt.n(k.positiveRec, 0),
      sub: `${k.strongBuy || 0} MUA MẠNH · ${k.noData || 0} chưa đủ dữ liệu`,
      valueClass: 'up',
    }),
    kpiCard({ label: 'Premium hoà vốn TB', value: fmt.pct(k.medianPremium, 1, false), sub: `trung vị · TB ${fmt.pct(k.avgPremium, 1, false)}` }),
    kpiCard({ label: 'IV trung vị / HV', value: `${fmt.pct((k.avgIv || 0) * 100, 0, false)} / ${fmt.pct((k.avgHv || 0) * 100, 0, false)}`, sub: 'IV cao hơn HV ⇒ CW đắt so với biến động thực tế' }),
    kpiCard({ label: 'Điểm TB toàn thị trường', value: fmt.n(k.avgScore, 1), sub: `${k.scoreAbove65 || 0} mã ≥ 65 điểm` }),
  ]);
  view.appendChild(kpi);

  // breadth + distribution
  view.appendChild(breadthCharts());
  view.appendChild(el('div', { class: 'grid cols-2 section' }, [distributionCard(), premiumDistCard()]));

  // top lists
  const topSection = el('div', { class: 'section' });
  topSection.appendChild(sectionHead('Top CW nổi bật', el('span', { class: 'small muted', text: 'Lọc CW có giá trị giao dịch ≥ 5 triệu/phiên' })));
  const tabs = el('div', { class: 'tabs' });
  const topBody = el('div');
  const paintTabs = () => {
    tabs.innerHTML = '';
    for (const [key, label] of TOP_TABS) {
      tabs.appendChild(el('div', {
        class: 'tab' + (state.topTab === key ? ' on' : ''),
        text: label,
        onclick: () => { state.topTab = key; paintTabs(); paintTop(); },
      }));
    }
  };
  const paintTop = () => { topBody.innerHTML = ''; topBody.appendChild(topTable(state.topTab)); };
  paintTabs(); paintTop();
  topSection.append(tabs, topBody);
  view.appendChild(topSection);

  // distributions by issuer/underlying
  view.appendChild(el('div', { class: 'grid cols-2 section' }, [
    el('div', {}, [sectionHead('Phân bố theo tổ chức phát hành'), issuerTable()]),
    el('div', {}, [sectionHead('Cổ phiếu cơ sở (theo động lượng 21 phiên)'), underlyingTable()]),
  ]));

  // notes
  const notes = el('div', { class: 'card' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Ghi chú dữ liệu' })]),
    el('div', { class: 'notice' }, [
      el('div', {
        html: `Dữ liệu là <b>snapshot cuối phiên ${esc(meta.asofLabel)}</b> (cập nhật ${esc(meta.generatedAt)}), không phải realtime. `
          + `Các mã không giao dịch trong 14 phiên bị loại khỏi thống kê tổng quan. `
          + `Premium hoà vốn = (K + giá CW × tỷ lệ)/S − 1. Điểm CW là <b>thang tương đối</b> trong vũ trụ hiện tại.`,
      }),
    ]),
    el('div', { class: 'tiny muted', html: `Nguồn: Vietstock (điều khoản) · vnstock VCI/KBS (OHLCV) · HNX/VBMA (lãi suất phi rủi ro 10Y = ${fmt.pct((meta.riskFree?.value || 0) * 100, 2, false)}).` }),
  ]);
  view.appendChild(notes);
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
