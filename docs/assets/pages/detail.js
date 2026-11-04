/* Trang phân tích chi tiết một chứng quyền */
import {
  el, fmt, data, badge, scoreCell, table, watchToggle, navigate, toast, store,
  drawCandles, drawLine, onThemeChange, bsPrice, bsGreeks, sectionHead, openDrawer, closeDrawer,
} from '../core.js';

const TABS = [
  ['overview', 'Tổng quan'],
  ['valuation', 'Định giá & Greeks'],
  ['liquidity', 'Thanh khoản'],
  ['scenario', 'Phân tích kịch bản'],
  ['peers', 'So sánh cùng cơ sở'],
  ['plan', 'Kế hoạch & rủi ro'],
];

const state = { tab: 'overview' };

function statline(items) {
  return el('div', { class: 'statline' }, items.map(([k, v, cls]) => el('div', {}, [
    el('div', { class: 'k', text: k }),
    el('div', { class: 'v ' + (cls || ''), html: v }),
  ])));
}

function lastVal(arr) {
  if (!arr) return null;
  for (let i = arr.length - 1; i >= 0; i--) if (Number.isFinite(arr[i])) return arr[i];
  return null;
}

function chartCard(title, canvas, height = 200, legend = null) {
  const card = el('div', { class: 'card' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: title }), legend]),
    el('div', { class: 'chart-box' }, [canvas]),
  ]);
  canvas.style.height = height + 'px';
  return card;
}

/* ---------------- TAB: TỔNG QUAN ---------------- */
async function tabOverview(host, row, card) {
  const series = await data.cwSeries(row.t);
  const undSeries = await data.undSeries(row.u);

  if (!series) {
    host.appendChild(el('div', { class: 'empty', text: 'Không có chuỗi giá cho mã này (CW đã đáo hạn hoặc chưa đủ dữ liệu).' }));
  } else {
    const canvas = el('canvas');
    const cwCard = el('div', { class: 'card' }, [
      el('div', { class: 'card-title' }, [
        el('h3', { text: `Giá CW ${row.t} — nến ngày, MA20/MA50, khối lượng` }),
        el('div', { class: 'legend-inline' }, [
          el('span', { html: '<i style="background:var(--accent-2)"></i>MA20' }),
          el('span', { html: '<i style="background:var(--violet)"></i>MA50' }),
          el('span', { class: 'muted', text: `(${series.dates.length} phiên)` }),
        ]),
      ]),
      el('div', { class: 'chart-box' }, [canvas]),
    ]);
    host.appendChild(cwCard);
    const paint = () => drawCandles(canvas, series, { height: 340 });
    requestAnimationFrame(paint);
    onThemeChange(paint);
    canvas.style.height = '340px';

    // RSI + MACD
    const rsiCanvas = el('canvas');
    const macdCanvas = el('canvas');
    const indGrid = el('div', { class: 'grid cols-2' }, [
      chartCard('RSI(14)', rsiCanvas, 130),
      chartCard('MACD histogram', macdCanvas, 130),
    ]);
    host.appendChild(indGrid);
    const paintInd = () => {
      drawLine(rsiCanvas, {
        height: 130, labels: series.dates, series: [
          { name: 'RSI', values: series.rsi, color: getComputedStyle(document.documentElement).getPropertyValue('--accent-2').trim() },
          { name: '70', values: series.rsi.map(() => 70), color: getComputedStyle(document.documentElement).getPropertyValue('--down').trim(), width: 0.7 },
          { name: '30', values: series.rsi.map(() => 30), color: getComputedStyle(document.documentElement).getPropertyValue('--up').trim(), width: 0.7 },
        ], yMin: 0, yMax: 100, yFormat: (v) => fmt.n(v, 0),
      });
      drawBarsWrap(macdCanvas, series);
    };
    requestAnimationFrame(paintInd);
    onThemeChange(paintInd);
  }

  // cổ phiếu cơ sở
  if (undSeries) {
    const uCanvas = el('canvas');
    const uCard = el('div', { class: 'card' }, [
      el('div', { class: 'card-title' }, [
        el('h3', { text: `Cổ phiếu cơ sở ${row.u} — giá đóng cửa & MA50` }),
        el('span', { class: 'tiny muted', text: `${undSeries.dates.length} phiên gần nhất` }),
      ]),
      el('div', { class: 'chart-box' }, [uCanvas]),
    ]);
    host.appendChild(uCard);
    const paintU = () => drawLine(uCanvas, {
      height: 170, labels: undSeries.dates,
      series: [
        { name: 'Giá', values: undSeries.c, color: getComputedStyle(document.documentElement).getPropertyValue('--accent').trim(), fill: true },
        { name: 'MA50', values: undSeries.ma50, color: getComputedStyle(document.documentElement).getPropertyValue('--violet').trim(), width: 1 },
      ],
      yFormat: (v) => fmt.px(v),
    });
    requestAnimationFrame(paintU);
    onThemeChange(paintU);
    uCanvas.style.height = '170px';

    // thống kê cổ phiếu cơ sở
    const ret1 = lastVal(undSeries.c) / (undSeries.c[undSeries.c.length - 2] || 1) - 1;
    host.appendChild(el('div', { class: 'grid kpi', style: 'margin-top:12px' }, [
      mini('Giá cơ sở', fmt.px(lastVal(undSeries.c))),
      mini('%1 phiên', fmt.pct(ret1 * 100, 2), ret1 > 0 ? 'up' : 'down'),
      mini('%21 phiên', fmt.pct(row.uRet21, 1), row.uRet21 > 0 ? 'up' : 'down'),
      mini('RSI(14) cơ sở', fmt.n(row.uRsi, 0)),
      mini('HV 1 năm', fmt.pct((row.uHv || 0) * 100, 0, false)),
      mini('Trên MA50', row.uAbove50 ? 'Có' : 'Không', row.uAbove50 ? 'up' : 'down'),
    ]));
  }

  if (card) {
    host.appendChild(el('div', { class: 'notice', html: `<b>Luận điểm mô hình:</b> ${card.thesis.map(esc).join(' ')}` }));
  }
}

function drawBarsWrap(canvas, series) {
  const g = getComputedStyle(document.documentElement);
  drawLine(canvas, {
    height: 130, labels: series.dates, zeroLine: true,
    series: [
      { name: 'MACD hist', values: series.macd, color: g.getPropertyValue('--accent').trim() },
    ],
    yFormat: (v) => fmt.n(v, 1),
  });
}

function mini(label, value, cls = '') {
  return el('div', { class: 'kpi-card' }, [
    el('div', { class: 'kpi-label', text: label }),
    el('div', { class: 'kpi-value sm ' + cls, text: value }),
  ]);
}

/* ---------------- TAB: ĐỊNH GIÁ ---------------- */
function tabValuation(host, row, card) {
  const m = card?.metrics || {};
  const grid = el('div', { class: 'grid cols-2' });

  const valRows = [
    ['Giá thị trường', fmt.px(row.price) + ' VND/CW'],
    ['Giá trị hợp lý (smile cùng cơ sở)', fmt.px(row.fvSmile), row.upsideSmile],
    ['Giá trị Black–Scholes @ HV', fmt.px(row.fvHv), row.upsideHv],
    ['Giá trị nội tại', fmt.px(row.intrinsic)],
    ['Giá trị thời gian', fmt.px(row.timeValue)],
    ['Premium hoà vốn', fmt.pct(row.premium, 1, false)],
    ['Điểm hoà vốn (S tại đáo hạn)', fmt.px(row.be) + ' VND'],
    ['Khoảng cách tới hoà vốn', fmt.pct(row.beDist, 1)],
    ['Moneyness', `${row.money} (${fmt.pct(row.moneyPct, 1)})`],
    ['Gearing danh nghĩa', fmt.n(row.gearing, 2) + '×'],
    ['Gearing hiệu dụng', fmt.n(row.effGear, 2) + '×'],
    ['IV / HV', `${fmt.pct((row.iv || 0) * 100, 1, false)} / ${fmt.pct((row.sigma || 0) * 100, 1, false)}`],
    ['IV − HV', fmt.pct(row.ivVsHv, 1)],
    ['IV residual vs đường cong', fmt.pct(row.ivResid, 1)],
    ['IV rank (lịch sử 1 năm)', fmt.n(row.ivRank, 0)],
  ];
  const valTable = el('div', { class: 'kv' });
  for (const [k, v, maybe] of valRows) {
    const cell = el('div', { class: 'v', text: v });
    if (typeof maybe === 'number') cell.className = 'v ' + (maybe >= 0 ? 'up' : 'down');
    valTable.append(el('div', { class: 'k', text: k }), cell);
  }
  grid.appendChild(el('div', { class: 'card' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Bảng định giá' })]),
    valTable,
    el('div', { class: 'notice warn', html: 'Giá trị lý thuyết <b>không phải</b> giá có thể giao dịch. Chênh lệch phản ánh IV, thanh khoản, cung cầu và rủi ro tổ chức phát hành.' }),
  ]));

  const greekRows = [
    ['Delta (theo CW)', fmt.n(row.delta, 4)],
    ['Delta quy đổi cổ phiếu', fmt.n(row.deltaOpt, 3)],
    ['Gamma', fmt.n(row.gamma, 6)],
    ['Theta / ngày (VND)', fmt.n(row.theta, 3)],
    ['Theta / ngày (% giá)', fmt.pct(row.thetaPct, 2)],
    ['Vega (1% σ)', fmt.n(row.vega, 2)],
    ['Tỷ lệ chuyển đổi', fmt.n(row.ratio, 4)],
    ['Strike (đã điều chỉnh)', fmt.px(row.K) + ' VND'],
    ['Số ngày còn lại', fmt.dte(row.dte)],
    ['Số phiên có dữ liệu', fmt.n(row.sessions, 0)],
  ];
  const gTable = el('div', { class: 'kv' });
  for (const [k, v] of greekRows) gTable.append(el('div', { class: 'k', text: k }), el('div', { class: 'v', text: v }));
  grid.appendChild(el('div', { class: 'card' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Greeks & điều khoản' })]),
    gTable,
    el('div', { class: 'formula', style: 'margin-top:10px', text: 'C = [S·N(d1) − K·e^(−rT)·N(d2)] / tỷ lệ ;  d1 = [ln(S/K) + (r + σ²/2)T] / (σ√T)' }),
    el('div', { class: 'tiny muted', style: 'margin-top:6px', text: `σ dùng cho BS = ${fmt.pct((row.sigma || 0) * 100, 1, false)} (HV 1 năm của ${row.u}); r = lãi suất phi rủi ro 10Y. CW kiểu châu Âu, không cổ tức trong công thức.` }),
  ]));
  host.appendChild(grid);

  // biểu đồ premium & IV
  const premCanvas = el('canvas');
  const ivCanvas = el('canvas');
  host.appendChild(el('div', { class: 'grid cols-2' }, [
    chartCard('Lịch sử premium hoà vốn (%)', premCanvas, 170),
    chartCard('IV thị trường vs HV cơ sở', ivCanvas, 170),
  ]));
  data.cwSeries(row.t).then((s) => {
    if (!s) return;
    const paint = () => {
      const g = getComputedStyle(document.documentElement);
      drawLine(premCanvas, {
        height: 170, labels: s.dates,
        series: [{ name: 'Premium %', values: s.premium, color: g.getPropertyValue('--warn').trim(), fill: true }],
        yFormat: (v) => fmt.pct(v, 0, false),
      });
      drawLine(ivCanvas, {
        height: 170, labels: s.dates,
        series: [
          { name: 'IV', values: (s.iv || []).map((v) => (v === null ? null : v * 100)), color: g.getPropertyValue('--accent-2').trim() },
          { name: 'HV', values: (s.sigma || []).map((v) => (v === null ? null : v * 100)), color: g.getPropertyValue('--violet').trim() },
        ],
        yFormat: (v) => fmt.pct(v, 0, false),
      });
    };
    requestAnimationFrame(paint);
    onThemeChange(paint);
  });
}

/* ---------------- TAB: KỊCH BẢN ---------------- */
/* ---------------- TAB: THANH KHOẢN ---------------- */
async function tabLiquidity(host, row, card) {
  host.appendChild(statline([
    ['ADV20', fmt.vnd(row.adv20)],
    ['ADV5', fmt.vnd(row.adv5)],
    ['Độ phủ (từ niêm yết)', (row.covList ?? row.cov20) == null ? '—' : fmt.n(row.covList ?? row.cov20, 0) + '%', (row.covList ?? row.cov20 ?? 100) >= 80 ? 'up' : 'down'],
    ['Phiên trắng 20P', fmt.n(row.zero20, 0)],
    ['Amihud20', row.amihud == null ? '—' : fmt.n(row.amihud, 2) + '%/tỷ'],
    ['Biên độ HL 20P', row.range20 == null ? '—' : fmt.n(row.range20, 1) + '%'],
    ['Turnover20', row.turnover == null ? '—' : fmt.n(row.turnover, 2) + '%'],
    ['DTL 50 triệu', row.dtl == null ? '—' : fmt.n(row.dtl, 1) + ' phiên'],
    ['Tác động 50 triệu', row.impact == null ? '—' : fmt.n(row.impact, 2) + '%'],
    ['Nhóm', row.liqBucket || '—'],
  ]));

  const series = await data.cwSeries(row.t);
  if (series?.adv?.length) {
    const advCanvas = el('canvas');
    const covCanvas = el('canvas');
    const cut = Math.max(0, series.adv.length - 160);
    const grid = el('div', { class: 'grid cols-2' }, [
      chartCard('ADV20 theo phiên', advCanvas, 170),
      chartCard('Độ phủ giao dịch 20 phiên (%)', covCanvas, 170),
    ]);
    host.appendChild(grid);
    const paint = () => {
      const g = getComputedStyle(document.documentElement);
      drawLine(advCanvas, {
        height: 170, labels: series.dates.slice(cut),
        series: [{
          name: 'ADV20', values: series.adv.slice(cut),
          color: g.getPropertyValue('--accent').trim(), fill: true,
        }],
        yFormat: (v) => fmt.vnd(v),
      });
      drawLine(covCanvas, {
        height: 170, labels: series.dates.slice(cut),
        series: [{
          name: 'Độ phủ', values: (series.cov || []).slice(cut),
          color: g.getPropertyValue('--accent-2').trim(), fill: true,
        }],
        yMin: 0, yMax: 100, yFormat: (v) => fmt.n(v, 0) + '%',
      });
    };
    requestAnimationFrame(paint);
    onThemeChange(paint);
  }

  host.appendChild(sectionHead('Máy tính thoát vị thế', el('span', {
    class: 'tiny muted', text: 'dựa trên ADV20 và biến động của chính CW này',
  })));
  const posInput = el('input', { class: 'input', type: 'number', value: '50', min: '1', step: '10', style: 'width:120px' });
  const result = el('div', { class: 'grid cols-3', style: 'margin-top:10px' });
  const calc = () => {
    const pos = Number(posInput.value) * 1e6;
    result.innerHTML = '';
    if (!(pos > 0) || !(row.adv20 > 0)) return;
    const part = data.liquidity?.thresholds?.participation || 0.2;
    const eta = data.liquidity?.thresholds?.impactEta || 0.1;
    const sigma = (row.atrPct || 5) / 100;
    const dtl = pos / (part * row.adv20);
    const impact = eta * sigma * Math.sqrt(pos / row.adv20) * 100;
    result.append(
      mini('Số phiên cần thoát', fmt.n(dtl, 1), dtl > 5 ? 'down' : dtl > 1 ? '' : 'up'),
      mini('Tác động giá ước tính', fmt.n(impact, 2) + '%', impact > 1 ? 'down' : ''),
      mini('Quy mô tối đa nên giao dịch', fmt.vnd(0.2 * row.adv20), ''),
    );
  };
  posInput.addEventListener('input', calc);
  host.appendChild(el('div', { class: 'filter-row' }, [
    el('span', { class: 'tiny muted', text: 'Vị thế (triệu VND)' }), posInput,
    el('span', { class: 'tiny muted', text: 'giả định tham gia 20% ADV20 mỗi phiên' }),
  ]));
  host.appendChild(result);
  calc();

  if (card) {
    const liqWarn = (card.risk_warnings || []).filter((w) => /thanh khoản|ADV|phiên|trượt giá|Amihud|biên độ/i.test(w));
    if (liqWarn.length) {
      host.appendChild(el('div', { class: 'notice warn', html: `<b>Cảnh báo:</b><ul style="margin:6px 0 0 18px">${
        liqWarn.map((w) => `<li>${esc(w)}</li>`).join('')}</ul>` }));
    }
  }

  const peers = data.activeRows().filter((r) => r.u === row.u).sort((a, b) => (b.adv20 || 0) - (a.adv20 || 0));
  if (peers.length > 1) {
    host.appendChild(sectionHead(`Thanh khoản các CW cùng ${row.u}`));
    host.appendChild(table({
      compact: true,
      onRowClick: (r) => navigate(`#/cw/${r.t}`),
      columns: [
        { key: 't', title: 'Mã', render: (r) => el('span', { class: 'tbl-ticker', text: r.t }) },
        { key: 'adv20', title: 'ADV20', align: 'right', render: (r) => fmt.vnd(r.adv20) },
        { key: 'cov20', title: 'Phủ TK', align: 'right', render: (r) => { const v = r.covList ?? r.cov20; return v == null ? '—' : fmt.n(v, 0) + '%'; } },
        { key: 'zero20', title: 'Phiên trắng', align: 'right', render: (r) => fmt.n(r.zero20, 0) },
        { key: 'dtl', title: 'DTL 50tr', align: 'right', render: (r) => (r.dtl == null ? '—' : fmt.n(r.dtl, 1)) },
        { key: 'impact', title: 'Tác động', align: 'right', render: (r) => (r.impact == null ? '—' : fmt.n(r.impact, 2) + '%') },
        { key: 'score', title: 'Điểm', align: 'right', render: (r) => fmt.n(r.score, 1) },
      ],
      rows: peers,
    }));
  }
  host.appendChild(el('div', { class: 'tiny muted', style: 'margin-top:8px', text:
    'ADV20 tính trên lịch giao dịch đầy đủ, phiên không khớp lệnh = 0 VND. '
    + 'DTL và tác động giá là ước lượng theo công thức công bố (20% ADV, mô hình căn bậc hai), không phải bảo đảm.' }));
}

function tabScenario(host, row) {
  const controls = el('div', { class: 'card scenario-controls' });
  const out = el('div', { class: 'card' });
  const grid = el('div', { class: 'scenario-grid' }, [controls, out]);

  const move = el('input', { type: 'range', min: -40, max: 40, step: 1, value: 5 });
  const moveLbl = el('span', { class: 'mono', text: '+5%' });
  const hold = el('input', { type: 'range', min: 1, max: Math.max(5, Math.min(90, row.dte - 1 || 30)), step: 1, value: Math.min(20, Math.max(5, row.dte - 1 || 20)) });
  const holdLbl = el('span', { class: 'mono', text: hold.value + ' phiên' });
  const volMode = el('select', {}, [
    el('option', { value: 'hv', text: 'HV lịch sử (σ mô hình)' }),
    el('option', { value: 'iv', text: 'IV thị trường hiện tại' }),
  ]);
  const volShock = el('input', { type: 'range', min: -50, max: 100, step: 5, value: 0 });
  const volLbl = el('span', { class: 'mono', text: '0%' });

  const wrapRange = (label, input, lbl) => el('label', {}, [
    el('div', { class: 'row' }, [el('span', { text: label }), lbl]),
    input,
  ]);

  controls.append(
    el('div', { class: 'card-title' }, [el('h3', { text: 'Giả định kịch bản' })]),
    wrapRange('Cổ phiếu cơ sở thay đổi', move, moveLbl),
    wrapRange('Thời gian nắm giữ', hold, holdLbl),
    el('label', { style: 'display:block;margin-bottom:10px' }, [
      el('div', { class: 'row' }, [el('span', { text: 'Nguồn biến động' })]),
      volMode,
    ]),
    wrapRange('Sốc biến động (IV/σ)', volShock, volLbl),
    el('div', { class: 'tiny muted', html: 'Mô hình: Black–Scholes châu Âu, không cổ tức. Thời gian còn lại giảm đúng số phiên nắm giữ. '
      + 'Giá trị CW ước tính là <b>giá trị lý thuyết</b>, chưa gồm chênh lệch mua-bán và thanh khoản.' }),
  );

  const tableBox = el('div');
  out.append(
    el('div', { class: 'card-title' }, [el('h3', { text: 'Kết quả ước tính' })]),
    el('div', { id: 'scenario-kpi', class: 'grid kpi', style: 'margin-bottom:12px' }),
    tableBox,
  );

  host.appendChild(grid);

  const compute = () => {
    const S0 = row.S;
    const T0 = Math.max(1e-6, (row.dte || 0) / 365);
    const baseSigma = volMode.value === 'iv' && row.iv ? row.iv : (row.sigma || 0.3);
    const sigma = Math.max(0.01, baseSigma * (1 + Number(volShock.value) / 100));
    const days = Number(hold.value);
    const movePct = Number(move.value) / 100;
    const price = row.price;

    const value = (mv, dd, sg) => {
      const T = Math.max(1e-6, T0 - dd / 365);
      return bsPrice({ S: S0 * (1 + mv), K: row.K, T, r: data.meta?.riskFree?.value ?? 0.044, sigma: sg, ratio: row.ratio });
    };

    const est = value(movePct, days, sigma);
    const base = value(0, 0, sigma);
    const pl = price ? (est / price - 1) * 100 : null;

    const kpiBox = out.querySelector('#scenario-kpi');
    kpiBox.innerHTML = '';
    kpiBox.append(
      mini('Giá cơ sở mới', fmt.px(S0 * (1 + movePct))),
      mini('Giá CW lý thuyết', fmt.px(est)),
      mini('P/L so giá hiện tại', fmt.pct(pl, 1), pl >= 0 ? 'up' : 'down'),
      mini('P/L / 10.000 CW', fmt.n((est - price) * 10000, 0) + ' VND', (est - price) >= 0 ? 'up' : 'down'),
      mini('σ sử dụng', fmt.pct(sigma * 100, 0, false)),
      mini('Giá trị tại t=0 (cùng σ)', fmt.px(base)),
    );

    // lưới kịch bản
    const moves = [-20, -10, -5, 0, 5, 10, 20];
    const holds = [...new Set([5, 10, 20, Math.min(45, Math.max(5, row.dte - 1))])].filter((d) => d < row.dte);
    const tbl = el('table', { class: 'tbl compact scenario-table' });
    const thead = el('thead');
    const hr = el('tr', {}, [el('th', { text: 'Cơ sở / giữ' })]);
    holds.forEach((d) => hr.appendChild(el('th', { class: 'num', text: d + ' phiên' })));
    thead.appendChild(hr); tbl.appendChild(thead);
    const tbody = el('tbody');
    for (const mv of moves) {
      const tr = el('tr');
      tr.appendChild(el('td', { class: 'mono', text: (mv > 0 ? '+' : '') + mv + '%' }));
      for (const d of holds) {
        const v = value(mv / 100, d, sigma);
        const p = price ? (v / price - 1) * 100 : 0;
        tr.appendChild(el('td', {
          class: 'num ' + (p >= 0 ? 'up' : 'down'),
          text: `${fmt.px(v)} (${fmt.pct(p, 0)})`,
        }));
      }
      tbody.appendChild(tr);
    }
    tbl.appendChild(tbody);
    tableBox.innerHTML = '';
    tableBox.appendChild(el('div', { class: 'tiny muted', style: 'margin-bottom:6px', text: 'Giá CW ước tính (P/L so với giá hiện tại) theo mức thay đổi cổ phiếu cơ sở và số phiên nắm giữ:' }));
    tableBox.appendChild(tbl);
  };

  const sync = () => {
    moveLbl.textContent = (Number(move.value) > 0 ? '+' : '') + move.value + '%';
    holdLbl.textContent = hold.value + ' phiên';
    volLbl.textContent = (Number(volShock.value) > 0 ? '+' : '') + volShock.value + '%';
    compute();
  };
  [move, hold, volShock].forEach((i) => i.addEventListener('input', sync));
  volMode.addEventListener('change', compute);
  sync();
}

/* ---------------- TAB: SO SÁNH ---------------- */
function tabPeers(host, row) {
  const peers = data.activeRows().filter((r) => r.u === row.u);
  peers.sort((a, b) => (b.score || 0) - (a.score || 0));
  host.appendChild(el('div', { class: 'notice' }, [
    el('span', { html: `Có <b>${peers.length}</b> CW đang giao dịch trên <b>${esc(row.u)}</b>. So sánh trực tiếp premium/IV giúp tránh mua CW đắt hơn các mã cùng cơ sở.` }),
  ]));
  host.appendChild(table({
    compact: true,
    rows: peers,
    onRowClick: (r) => { if (r.t !== row.t) navigate(`#/cw/${r.t}`); },
    columns: [
      { key: 't', title: 'Mã', render: (r) => el('span', { class: 'tbl-ticker', style: r.t === row.t ? 'color:var(--accent)' : null, text: r.t + (r.t === row.t ? ' ◂' : '') }) },
      { key: 'issName', title: 'TCPH' },
      { key: 'price', title: 'Giá', align: 'right', render: (r) => fmt.px(r.price) },
      { key: 'money', title: 'Money', render: (r) => el('span', { class: `badge ${r.money}`, text: r.money }) },
      { key: 'premium', title: 'Premium', align: 'right', render: (r) => fmt.pct(r.premium, 1, false) },
      { key: 'iv', title: 'IV', align: 'right', render: (r) => fmt.pct((r.iv || 0) * 100, 0, false) },
      { key: 'ivVsHv', title: 'IV−HV', align: 'right', render: (r) => el('span', { class: fmt.cls(-(r.ivVsHv || 0)), text: fmt.pct(r.ivVsHv, 0) }) },
      { key: 'deltaOpt', title: 'Delta', align: 'right', render: (r) => fmt.n(r.deltaOpt, 2) },
      { key: 'dte', title: 'DTE', align: 'right' },
      { key: 'upsideSmile', title: 'Upside FV', align: 'right', render: (r) => el('span', { class: fmt.cls(r.upsideSmile), text: fmt.pct(r.upsideSmile, 0) }) },
      { key: 'value20', title: 'GT 20P', align: 'right', render: (r) => fmt.vnd(r.value20) },
      { key: 'score', title: 'Điểm', align: 'right', render: (r) => scoreCell(r.score) },
      { key: 'rec', title: 'Khuyến nghị', render: (r) => badge(r.rec) },
    ],
  }));
}

/* ---------------- TAB: KẾ HOẠCH ---------------- */
function tabPlan(host, row, card) {
  if (!card) {
    host.appendChild(el('div', { class: 'empty', text: 'Không có card khuyến nghị cho mã này (có thể đã đáo hạn hoặc thiếu dữ liệu).' }));
  } else {
    const grid = el('div', { class: 'grid cols-2' });

    // trụ cột điểm
    const compCard = el('div', { class: 'card' }, [el('div', { class: 'card-title' }, [el('h3', { text: 'Cấu thành điểm CW Score' })])]);
    const bars = el('div', { class: 'comp-bars' });
    const LABELS = {
      underlying_momentum: 'Động lượng cơ sở (25%)', valuation: 'Định giá (20%)', liquidity: 'Thanh khoản (15%)',
      risk_reward: 'Rủi ro/lợi nhuận (20%)', technical: 'Kỹ thuật (10%)', time_to_maturity: 'Thời gian (10%)',
    };
    for (const [k, v] of Object.entries(card.components || {})) {
      const conf = card.component_confidence?.[k];
      bars.appendChild(el('div', { class: 'comp-row', title: `Độ tin cậy ${conf === undefined ? '—' : fmt.n(conf * 100, 0) + '%'}` }, [
        el('span', { text: LABELS[k] || k }),
        el('span', { class: 'comp-track' }, [el('i', { style: `width:${Math.max(0, Math.min(100, v || 0))}%` })]),
        el('span', { class: 'comp-score', text: fmt.n(v, 0) }),
      ]));
    }
    compCard.appendChild(bars);
    compCard.appendChild(el('div', { class: 'tiny muted', text: 'Thanh bar thể hiện điểm thành phần 0–100; độ mờ của nhãn phản ánh độ tin cậy dữ liệu (rê chuột để xem).' }));

    // trading plan
    const planCard = el('div', { class: 'card' }, [el('div', { class: 'card-title' }, [el('h3', { text: 'Kế hoạch giao dịch (mô phỏng)' })])]);
    const plan = card.trading_plan || {};
    if (!plan.available) {
      planCard.appendChild(el('div', { class: 'empty', text: 'Chưa đủ dữ liệu để lập kế hoạch' }));
      planCard.appendChild(el('div', { class: 'tiny muted center', text: plan.reason || 'Thiếu ATR/điều khoản/giá.' }));
    } else {
      planCard.appendChild(el('div', { class: 'plan-grid' }, [
        planItem('Vùng vào lệnh', `${fmt.px(plan.entry_zone?.[0])} – ${fmt.px(plan.entry_zone?.[1])}`),
        planItem('Cắt lỗ', `${fmt.px(plan.stop_loss)} (${fmt.pct(plan.stop_loss_pct, 1)})`),
        planItem('Nắm giữ dự kiến', `${plan.expected_holding_days} phiên`),
        planItem('R:R (kịch bản +5%)', plan.risk_reward ? fmt.n(plan.risk_reward, 2) + '×' : '—'),
      ]));
      const tpTable = el('table', { class: 'tbl compact', style: 'margin-top:8px' });
      tpTable.innerHTML = `<thead><tr><th>Cơ sở tăng</th><th class="num">Giữ</th><th class="num">Giá CW ước tính</th><th class="num">P/L</th></tr></thead>`;
      const tb = el('tbody');
      for (const s of plan.take_profit || []) {
        tb.appendChild(el('tr', {}, [
          el('td', { text: fmt.pct(s.underlying_move_pct, 0) }),
          el('td', { class: 'num', text: s.holding_sessions + ' phiên' }),
          el('td', { class: 'num', text: fmt.px(s.estimated_price) }),
          el('td', { class: 'num ' + (s.estimated_pl_pct >= 0 ? 'up' : 'down'), text: fmt.pct(s.estimated_pl_pct, 1) }),
        ]));
      }
      tpTable.appendChild(tb);
      planCard.appendChild(tpTable);
      planCard.appendChild(el('div', { class: 'tiny muted', style: 'margin-top:8px', text: plan.rationale || '' }));
      if (plan.atr_source === 'ret_std20') {
        planCard.appendChild(el('div', { class: 'tiny muted', text: 'ATR dự phòng = giá × độ lệch chuẩn lợi suất 20 phiên (CW chưa đủ 14 phiên để tính ATR14).' }));
      }
    }
    grid.append(compCard, planCard);

    // luận điểm & yếu tố
    const factorCard = (title, list, cls) => el('div', { class: 'card' }, [
      el('div', { class: 'card-title' }, [el('h3', { text: title })]),
      list && list.length
        ? el('ul', { class: `factor-list ${cls}` }, list.map((t) => el('li', { text: t })))
        : el('div', { class: 'tiny muted', text: 'Không có.' }),
    ]);
    grid.append(
      factorCard('Yếu tố tích cực', card.positive_factors, 'pos'),
      factorCard('Yếu tố tiêu cực', card.negative_factors, 'neg'),
    );
    grid.append(
      factorCard('Cảnh báo rủi ro', card.risk_warnings, 'warn'),
      el('div', { class: 'card' }, [
        el('div', { class: 'card-title' }, [el('h3', { text: 'Điều kiện vô hiệu hoá luận điểm' })]),
        el('ul', { class: 'factor-list warn' }, (card.invalidation || []).map((t) => el('li', { text: t }))),
      ]),
    );
    host.appendChild(grid);

    host.appendChild(el('div', { class: 'notice danger', html: card.disclaimer }));
  }

  // nguồn dữ liệu
  host.appendChild(el('div', { class: 'card', style: 'margin-top:12px' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Nguồn gốc & chất lượng dữ liệu' })]),
    el('div', { class: 'kv' }, [
      el('div', { class: 'k', text: 'Ngày dữ liệu (as-of)' }), el('div', { class: 'v', text: fmt.date(data.meta?.asof) }),
      el('div', { class: 'k', text: 'Số phiên có dữ liệu' }), el('div', { class: 'v', text: fmt.n(row.sessions, 0) }),
      el('div', { class: 'k', text: 'Điểm chất lượng dữ liệu' }), el('div', { class: 'v', text: fmt.n(row.dq, 2) + ' / 1.00' }),
      el('div', { class: 'k', text: 'Chất lượng IV' }), el('div', { class: 'v', text: row.ivQuality || '—' }),
      el('div', { class: 'k', text: 'Điều khoản đã điều chỉnh' }), el('div', { class: 'v', text: row.termsAdj ? 'Có' : 'Không' }),
      el('div', { class: 'k', text: 'Tuổi giá (phiên)' }), el('div', { class: 'v', text: fmt.n(row.stale, 0) }),
      el('div', { class: 'k', text: 'Lãi suất phi rủi ro' }), el('div', { class: 'v', text: fmt.pct((data.meta?.riskFree?.value || 0) * 100, 2, false) }),
    ]),
  ]));
}

function planItem(k, v) {
  return el('div', { class: 'plan-item' }, [el('div', { class: 'k', text: k }), el('div', { class: 'v', text: v })]);
}

/* ---------------- PAGE ---------------- */
export default async function detail(view, ticker) {
  const row = data.row(ticker);
  if (!row) {
    view.appendChild(el('div', { class: 'page-head' }, [el('div', {}, [el('h1', { text: ticker || 'Không tìm thấy' }), el('div', { class: 'sub', text: 'Mã không tồn tại trong snapshot hiện tại.' })])]));
    view.appendChild(el('div', { class: 'empty' }, [
      el('div', { text: 'Không có dữ liệu cho mã này.' }),
      el('button', { class: 'btn sm', style: 'margin-top:10px', text: '← Về screener', onclick: () => navigate('#/screener') }),
    ]));
    return;
  }
  const card = data.card(ticker);

  // header
  const head = el('div', { class: 'detail-head' });
  head.appendChild(el('div', {}, [
    el('div', { class: 'detail-id' }, [
      el('h1', { text: row.t }),
      el('span', { class: 'badge tag', text: row.issName || row.iss }),
      el('span', { class: `badge ${row.money}`, text: row.money }),
      badge(row.rec),
      el('span', { class: 'badge tag', text: `${fmt.n(row.score, 1)} điểm` }),
      row.active ? null : el('span', { class: 'badge NO_DATA', text: 'ĐÃ ĐÁO HẠN' }),
    ]),
    el('div', { class: 'detail-meta' }, [
      el('span', { html: `Cơ sở <b>${esc(row.u)}</b>` }),
      el('span', { html: `Strike <b>${fmt.px(row.K)}</b>` }),
      el('span', { html: `Tỷ lệ <b>${fmt.n(row.ratio, 4)}</b>` }),
      el('span', { html: `Đáo hạn <b>${fmt.date(row.mat)}</b> (${fmt.dte(row.dte)})` }),
      el('span', { html: `Cập nhật <b>${fmt.date(row.date)}</b>` }),
    ]),
  ]));
  const priceBlock = el('div', {}, [
    el('div', { class: 'detail-price ' + fmt.cls(row.chg1), text: fmt.px(row.price) + ' VND' }),
    el('div', { class: 'small ' + fmt.cls(row.chg1), text: `${fmt.pct(row.chg1, 2)} hôm nay · ${fmt.vnd(row.value)} GT` }),
  ]);
  head.appendChild(el('div', { class: 'flex' }, [
    priceBlock,
    watchToggle(row.t),
    el('button', { class: 'btn sm', text: '← Screener', onclick: () => navigate('#/screener') }),
  ]));
  view.appendChild(head);

  // stats
  view.appendChild(statline([
    ['Điểm CW', fmt.n(row.score, 1)],
    ['Khuyến nghị', fmt.rec(row.rec), row.rec === 'BUY' || row.rec === 'STRONG_BUY' ? 'up' : row.rec === 'AVOID' || row.rec === 'HIGH_RISK' ? 'down' : ''],
    ['Premium hoà vốn', fmt.pct(row.premium, 1, false)],
    ['IV', fmt.pct((row.iv || 0) * 100, 1, false)],
    ['IV − HV', fmt.pct(row.ivVsHv, 1), (row.ivVsHv || 0) <= 0 ? 'up' : 'down'],
    ['Delta', fmt.n(row.delta, 3)],
    ['Gearing hiệu dụng', fmt.n(row.effGear, 2) + '×'],
    ['GT 20 phiên', fmt.vnd(row.value20)],
    ['DTE', fmt.dte(row.dte)],
    ['DQ', fmt.n(row.dq, 2)],
  ]));

  // tabs
  const tabs = el('div', { class: 'tabs', style: 'margin-top:14px' });
  const body = el('div');
  view.append(tabs, body);

  const painters = [];
  const paint = () => {
    tabs.innerHTML = '';
    TABS.forEach(([key, label]) => tabs.appendChild(el('div', {
      class: 'tab' + (state.tab === key ? ' on' : ''),
      text: label,
      onclick: () => { state.tab = key; paint(); },
    })));
    body.innerHTML = '';
    if (state.tab === 'overview') tabOverview(body, row, card);
    else if (state.tab === 'valuation') tabValuation(body, row, card);
    else if (state.tab === 'liquidity') tabLiquidity(body, row, card);
    else if (state.tab === 'scenario') tabScenario(body, row);
    else if (state.tab === 'peers') tabPeers(body, row);
    else tabPlan(body, row, card);
  };
  paint();
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
