/* Trang Tổng quan thị trường */
import {
  el, fmt, data, pageHead, kpiCard, sectionHead, scoreCell, table,
  drawLine, drawBars, onThemeChange, navigate, downloadCsv, toast,
} from '../core.js';
import { bi } from '../i18n.js';

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
    `Phiên dữ liệu cuối <b>${esc(meta.asofLabel || '—')}</b> · ${k.listed || k.active || 0} CW còn hiệu lực `
      + `(${k.traded ?? k.active ?? 0} giao dịch phiên này) · ${k.underlyings || 0} cổ phiếu cơ sở · ${k.issuers || 0} tổ chức phát hành`,
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
  const kpi = el('div', { class: 'grid kpi overview-kpi section' }, [
    kpiCard({
      label: 'CW còn hiệu lực',
      value: fmt.n(k.listed ?? k.active, 0),
      sub: `${fmt.n(k.traded ?? k.active, 0)} giao dịch phiên này · ${fmt.n(k.notTraded || 0)} không giao dịch<br>`
        + `${fmt.n(k.matured ?? k.expired, 0)} đã đáo hạn · tổng ${fmt.n(k.total, 0)} hợp đồng`,
    }),
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
  view.appendChild(lifecycleSection());

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
      // Mỗi câu là một text node riêng để bản dịch EN khớp chính xác (i18n không
      // dịch được câu đã bị cắt vụn bởi thẻ <b>).
      el('div', { text: `Dữ liệu là snapshot cuối phiên ${meta.asofLabel || '—'} `
        + `(cập nhật ${meta.generatedAt || '—'}), không phải realtime.` }),
      el('div', { text: 'CW đã đáo hạn hoặc ngừng giao dịch được tách khỏi snapshot nên không được '
        + 'chấm điểm hay khuyến nghị; mã không khớp lệnh trong 14 phiên cũng không vào snapshot.' }),
      el('div', { text: 'Premium hoà vốn = (K + giá CW × tỷ lệ)/S − 1. '
        + 'Điểm CW là thang tương đối trong vũ trụ hiện tại.' }),
    ]),
    el('div', { class: 'tiny muted', text: 'Nguồn do người dùng cấu hình; provenance và điều khoản gốc cần được kiểm tra trước khi chia sẻ kết quả.' }),
  ]);
  view.appendChild(notes);
}

function lifeChips(rows, key = 't', clickable = true) {
  const list = (rows || []).slice(0, 8);
  return el('div', { class: 'life-chips' }, list.map((r) => {
    const interactive = clickable && key === 't';
    // Nút thật khi có hành động: Enter/Space và screen reader hoạt động như click.
    return el(interactive ? 'button' : 'span', {
      class: 'life-chip' + (interactive ? ' clickable' : ''),
      type: interactive ? 'button' : null,
      text: r[key],
      'aria-label': interactive
        ? `${bi('Mở phân tích chi tiết', 'Open detailed analysis for')} ${r.t}` : null,
      title: [r.u, r.maturity || r.firstTrade, r.dte !== undefined ? `${r.dte} ngày` : null]
        .filter(Boolean).join(' · '),
      onclick: interactive ? () => navigate(`#/cw/${r.t}`) : null,
    });
  }));
}

function lifecycleSection() {
  const lc = data.lifecycle;
  const u = data.meta?.universe || data.market?.kpi || {};
  const c = lc?.counts || {
    total: u.total, listed: u.listed ?? u.active, traded: u.traded ?? u.active,
    notTraded: u.notTraded || 0, matured: u.matured ?? u.expired,
    delistedEarly: u.delistedEarly || 0, pending: u.pending || 0,
  };
  const sessions = lc?.recentSessions || 10;
  const since = fmt.date(lc?.recentSince);
  const up = lc?.upcoming || {};
  const d30 = up.d30 || { count: 0, rows: [] };
  const next = lc?.nextMaturity;
  const wrap = el('div', { class: 'section' });
  wrap.appendChild(sectionHead(
    'Vòng đời chứng quyền',
    el('span', { class: 'small muted', text: `${sessions} phiên gần nhất · từ ${since}` }),
  ));

  const card = (label, value, sub, rows, clickable = true) => el('div', { class: 'card life-card' }, [
    el('div', { class: 'kpi-label', text: label }),
    el('div', { class: 'kpi-value', text: fmt.n(value, 0) }),
    el('div', { class: 'kpi-sub', html: sub }),
    rows && rows.length ? lifeChips(rows, 't', clickable) : null,
  ]);

  wrap.appendChild(el('div', { class: 'grid cols-4 section' }, [
    card('Niêm yết mới', lc?.newListings?.count ?? c.newListings ?? 0,
      `${sessions} phiên · ${c.listed || 0} mã đang còn hiệu lực`, lc?.newListings?.rows),
    card('Vừa đáo hạn', lc?.recentMaturities?.count ?? c.maturedRecent ?? 0,
      `${sessions} phiên · tổng đã đáo hạn ${fmt.n(c.matured, 0)}`, lc?.recentMaturities?.rows, false),
    card('Sắp đáo hạn', d30.count,
      `≤ 30 ngày · ${(up.d60 || {}).count || 0} mã trong 60 ngày · ${(up.d90 || {}).count || 0} trong 90 ngày`,
      d30.rows, true),
    card('Ngừng giao dịch sớm', c.delistedEarly || lc?.earlyDelistings?.count || 0,
      (c.delistedEarly || 0) ? 'còn hạn nhưng không còn khớp lệnh' : 'không có mã nào bị ngừng sớm',
      lc?.earlyDelistings?.rows, false),
  ]));

  if (next) {
    wrap.appendChild(el('div', { class: 'notice tiny', text:
      `Hợp đồng gần đáo hạn nhất: ${next.t} (${next.u || ''}) — ${fmt.date(next.maturity)}, `
      + `còn ${next.dte} ngày. Sau ngày đáo hạn mã này tự chuyển sang danh sách đã đáo hạn `
      + `và không còn được khuyến nghị.` }));
  }

  // Lịch niêm yết / đáo hạn theo tháng
  const cal = lc?.calendar || [];
  if (cal.length) {
    const curIdx = cal.findIndex((m) => m.isCurrent);
    const start = Math.max(0, (curIdx < 0 ? 0 : curIdx) - 6);
    const rows = cal.slice(start, start + 19);
    const maxListed = Math.max(1, ...rows.map((r) => r.listedNow || 0));
    wrap.appendChild(el('div', { class: 'card section' }, [
      el('div', { class: 'card-title' }, [el('h3', { text: 'Lịch niêm yết & đáo hạn theo tháng' })]),
      table({
        compact: true,
        rows,
        empty: 'Không có dữ liệu lịch',
        columns: [
          { key: 'label', title: 'Tháng', render: (r) => el('span', { class: r.isCurrent ? 'mono strong' : 'mono', text: r.label + (r.isCurrent ? ' ◂' : '') }) },
          { key: 'listings', title: 'Niêm yết', align: 'right', render: (r) => fmt.n(r.listings, 0) },
          { key: 'maturities', title: 'Đáo hạn', align: 'right', render: (r) => fmt.n(r.maturities, 0) },
          {
            key: 'listedNow', title: 'Còn hiệu lực, đáo hạn trong tháng', align: 'right',
            render: (r) => el('span', { class: 'life-bar-cell' }, [
              el('span', { class: 'life-bar', style: `width:${Math.round((r.listedNow || 0) / maxListed * 100)}%` }),
              el('span', { class: 'mono', text: fmt.n(r.listedNow || 0, 0) }),
            ]),
          },
        ],
      }),
      el('div', { class: 'tiny muted', style: 'margin-top:8px', text:
        `Tổng vũ trụ ${fmt.n(c.total, 0)} hợp đồng = còn hiệu lực ${fmt.n(c.listed, 0)}`
        + ` + đã đáo hạn ${fmt.n(c.matured, 0)}`
        + (c.delistedEarly ? ` + ngừng giao dịch sớm ${fmt.n(c.delistedEarly, 0)}` : '')
        + (c.pending ? ` + chờ niêm yết ${fmt.n(c.pending, 0)}` : '')
        + (lc?.identity?.ok === false ? ' — LỆCH, xem báo cáo chất lượng' : '') }),
    ]));
  }
  return wrap;
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
