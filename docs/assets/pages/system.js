/* Trang Chất lượng dữ liệu + Phương pháp */
import { el, fmt, data, pageHead, kpiCard, sectionHead, table } from '../core.js';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* ===================== CHẤT LƯỢNG DỮ LIỆU ===================== */
export function dataPage(view) {
  const q = data.quality || { summary: {}, checks: [] };
  const meta = data.meta || {};
  const s = q.summary || {};

  view.appendChild(pageHead(
    'Chất lượng dữ liệu',
    `Kiểm tra tự động trên toàn bộ chuỗi dữ liệu tại phiên <b>${esc(meta.asofLabel || '')}</b> · sinh lúc ${esc(meta.generatedAt || '')}`,
    [],
  ));

  view.appendChild(el('div', { class: 'grid kpi section' }, [
    kpiCard({ label: 'Đạt', value: fmt.n(s.ok, 0), sub: `trên ${fmt.n(s.total, 0)} kiểm tra`, valueClass: 'up' }),
    kpiCard({ label: 'Cảnh báo', value: fmt.n(s.warn, 0), valueClass: 'warn', sub: 'không chặn pipeline' }),
    kpiCard({ label: 'Lỗi', value: fmt.n(s.error, 0), valueClass: s.error ? 'down' : '', sub: 'chặn phát hành khuyến nghị' }),
    kpiCard({ label: 'Tuổi dữ liệu', value: `${fmt.n(meta.dataAgeDays, 0)} phiên`, sub: meta.stale ? 'DỮ LIỆU CŨ' : 'trong ngưỡng cho phép' }),
    kpiCard({ label: 'Vũ trụ', value: fmt.n(meta.universe?.total, 0), sub: `${fmt.n(meta.universe?.active, 0)} active · ${fmt.n(meta.universe?.expired, 0)} đáo hạn` }),
    kpiCard({ label: 'Phiên bản phương pháp', value: esc(meta.methodologyVersion || '—'), sub: `model ${esc(meta.version || '')}` }),
  ]));

  if ((q.headline || []).length) {
    view.appendChild(el('div', { class: 'card section' }, [
      el('div', { class: 'card-title' }, [el('h3', { text: 'Điểm cần lưu ý' })]),
      el('ul', { class: 'factor-list warn' }, q.headline.map((h) => el('li', { text: h }))),
    ]));
  }

  const card = el('div', { class: 'card section' });
  card.appendChild(el('div', { class: 'card-title' }, [el('h3', { text: 'Danh sách kiểm tra' })]));
  for (const c of q.checks || []) {
    const dot = c.status === 'ok' ? 'ok' : c.status === 'warn' ? 'warn' : 'error';
    const val = c.value == null ? '' : Object.entries(c.value).slice(0, 4).map(([k, v]) => `${k}: ${typeof v === 'number' ? fmt.n(v, Number.isInteger(v) ? 0 : 2) : JSON.stringify(v)}`).join(' · ');
    card.appendChild(el('div', { class: 'check-row' }, [
      el('div', { style: 'padding-top:4px' }, [el('span', { class: 'status-dot ' + dot })]),
      el('div', {}, [
        el('div', { class: 'check-title', text: c.title }),
        el('div', { class: 'check-detail', text: c.detail || '' }),
      ]),
      el('div', { class: 'check-value', text: val }),
    ]));
  }
  view.appendChild(card);

  // provenance
  const prov = el('div', { class: 'grid cols-2 section' });
  prov.appendChild(el('div', { class: 'card' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Nguồn dữ liệu' })]),
    el('ul', { class: 'factor-list pos', style: 'padding-left:0' }, (meta.dataSources || []).map((d) => el('li', { text: d }))),
    el('div', { class: 'kv', style: 'margin-top:10px' }, [
      el('div', { class: 'k', text: 'Lãi suất phi rủi ro' }), el('div', { class: 'v', text: fmt.pct((meta.riskFree?.value || 0) * 100, 2, false) }),
      el('div', { class: 'k', text: 'Nguồn lãi suất' }), el('div', { class: 'v', text: meta.riskFree?.source || '—' }),
      el('div', { class: 'k', text: 'Ngày lãi suất' }), el('div', { class: 'v', text: fmt.date(meta.riskFree?.date) }),
      el('div', { class: 'k', text: 'Phiên dữ liệu' }), el('div', { class: 'v', text: fmt.date(meta.asof) }),
    ]),
  ]));
  const sizeRows = Object.entries(meta.files || {}).filter(([k]) => !k.startsWith('series/')).map(([k, v]) => ({ file: k, bytes: v }));
  prov.appendChild(el('div', { class: 'card' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Tệp phát hành' })]),
    table({
      compact: true, rows: sizeRows,
      columns: [
        { key: 'file', title: 'Tệp', render: (r) => el('span', { class: 'mono', text: r.file }) },
        { key: 'bytes', title: 'Kích thước', align: 'right', render: (r) => fmt.n(r.bytes / 1024, 0) + ' KB' },
      ],
    }),
    el('div', { class: 'tiny muted', style: 'margin-top:8px', text: `Chuỗi giá: ${fmt.n(meta.seriesBytes ? meta.seriesBytes / 1024 / 1024 : 0, 1)} MB cho ${fmt.n(meta.seriesTickers?.length || 0, 0)} mã (chỉ CW đang giao dịch hoặc giao dịch trong 365 ngày).` }),
  ]));
  view.appendChild(prov);

  view.appendChild(el('div', { class: 'notice warn' }, [
    el('div', { text: 'Nguyên tắc công bố: mọi trang đều hiển thị ngày dữ liệu. Không có dữ liệu realtime.' }),
    el('div', { text: 'Bản build luôn so asof với phiên đã đóng gần nhất (giờ Việt Nam, sau 15:10). '
      + 'Lệch 1 phiên → banner vàng; lệch từ 2 phiên → banner đỏ và cổng "session_lag" báo động '
      + 'trong danh sách kiểm tra ở trên.' }),
  ]));
}

/* ===================== PHƯƠNG PHÁP ===================== */
export function methodPage(view) {
  const m = data.methodology || {};
  view.appendChild(pageHead(
    'Phương pháp luận',
    `Phiên bản <b>${esc(m.version || '')}</b> — công thức, trọng số, cổng chất lượng và giới hạn của mô hình.`,
    [],
  ));

  // units
  const units = m.currency_units || {};
  view.appendChild(el('div', { class: 'card section' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Quy ước đơn vị' })]),
    el('div', { class: 'grid cols-4' }, Object.entries(units).map(([k, v]) => el('div', { class: 'kpi-card' }, [
      el('div', { class: 'kpi-label', text: k }),
      el('div', { class: 'small', style: 'margin-top:4px', text: v }),
    ]))),
  ]));

  // conventions
  const conv = el('div', { class: 'section' });
  conv.appendChild(sectionHead('Công thức & quy ước'));
  const convCard = el('div', { class: 'card' });
  for (const c of m.conventions || []) {
    convCard.appendChild(el('div', { style: 'padding:9px 0;border-bottom:1px solid var(--border)' }, [
      el('div', { class: 'flex' }, [el('strong', { text: c.title }), el('span', { class: 'spacer' }), el('span', { class: 'tiny muted', text: c.id })]),
      el('div', { class: 'formula', style: 'margin-top:5px', text: c.formula }),
      c.note ? el('div', { class: 'tiny muted', style: 'margin-top:4px', text: c.note }) : null,
    ]));
  }
  conv.appendChild(convCard);
  view.appendChild(conv);

  // scoring
  const sc = m.scoring || {};
  const scCard = el('div', { class: 'card section' });
  scCard.appendChild(el('div', { class: 'card-title' }, [el('h3', { text: 'CW Score — trọng số & thành phần' })]));
  const weights = sc.weights || {};
  const wTable = el('table', { class: 'tbl compact' });
  wTable.innerHTML = '<thead><tr><th>Thành phần</th><th class="num">Trọng số</th><th>Đo lường</th></tr></thead>';
  const wb = el('tbody');
  const compDesc = {
    underlying_momentum: 'Percentile return 21/63 phiên + vị thế so MA20/MA50 + RSI cổ phiếu cơ sở',
    valuation: 'Percentile premium hoà vốn, IV residual so đường cong cùng cơ sở, IV/HV, IV rank, dải delta',
    liquidity: 'log giá trị giao dịch TB 20 phiên, tỷ lệ phiên có giao dịch, tăng tốc khối lượng',
    risk_reward: 'Theta/ngày, khoảng cách hoà vốn, thời gian đáo hạn, biến động, gearing hiệu dụng',
    technical: 'RSI, MACD histogram & độ dốc, trên MA20/MA50, breakout 20 phiên (giảm độ tin cậy nếu <30 phiên)',
    time_to_maturity: 'Số ngày còn lại, ưu tiên 45–180 ngày',
  };
  for (const [k, w] of Object.entries(weights)) {
    wb.appendChild(el('tr', {}, [
      el('td', { text: k }),
      el('td', { class: 'num', text: fmt.pct(w * 100, 0, false) }),
      el('td', { class: 'small', text: compDesc[k] || '' }),
    ]));
  }
  wTable.appendChild(wb);
  scCard.appendChild(wTable);
  scCard.appendChild(el('div', { class: 'formula', style: 'margin-top:8px', text: sc.formula || 'Score = Σ(w_i × s_i × c_i) / Σ(w_i × c_i) — c_i là độ tin cậy dữ liệu của thành phần.' }));
  scCard.appendChild(el('div', { class: 'tiny muted', style: 'margin-top:6px', text: sc.note || '' }));
  view.appendChild(scCard);

  // recommendation
  const rec = m.recommendation || {};
  const recCard = el('div', { class: 'card section' });
  recCard.appendChild(el('div', { class: 'card-title' }, [el('h3', { text: 'Phân loại khuyến nghị & cổng chất lượng' })]));
  const th = el('div', { class: 'grid cols-4' });
  const tiers = [['MUA MẠNH', '80–100'], ['MUA', '65–79'], ['THEO DÕI', '45–64'], ['TRÁNH', '30–44'], ['RỦI RO CAO', '0–29']];
  for (const [label, range] of tiers) {
    th.appendChild(el('div', { class: 'kpi-card' }, [
      el('div', { class: 'kpi-label', text: label }),
      el('div', { class: 'kpi-value sm', text: range }),
    ]));
  }
  recCard.appendChild(th);
  const gates = rec.gates || {};
  if (Object.keys(gates).length) {
    const gt = el('table', { class: 'tbl compact', style: 'margin-top:10px' });
    gt.innerHTML = '<thead><tr><th>Cổng</th><th>MUA MẠNH</th><th>MUA</th></tr></thead>';
    const gb = el('tbody');
    const keys = new Set();
    Object.values(gates).forEach((g) => Object.keys(g || {}).forEach((k) => keys.add(k)));
    for (const k of keys) {
      gb.appendChild(el('tr', {}, [
        el('td', { text: k }),
        el('td', { class: 'num', text: String(gates.STRONG_BUY?.[k] ?? '—') }),
        el('td', { class: 'num', text: String(gates.BUY?.[k] ?? '—') }),
      ]));
    }
    gt.appendChild(gb);
    recCard.appendChild(gt);
  }
  if (rec.note) recCard.appendChild(el('div', { class: 'tiny muted', style: 'margin-top:8px', text: rec.note }));
  view.appendChild(recCard);

  // backtest
  const bt = m.backtest || {};
  const btCard = el('div', { class: 'card section' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Phương pháp backtest' })]),
    el('div', { class: 'kv' }, Object.entries(bt).filter(([, v]) => typeof v !== 'object').map(([k, v]) => [
      el('div', { class: 'k', text: k }), el('div', { class: 'v', text: String(v) }),
    ]).flat()),
  ]);
  view.appendChild(btCard);

  // limitations
  view.appendChild(el('div', { class: 'card section' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Giới hạn đã biết' })]),
    el('ul', { class: 'factor-list warn' }, (m.limitations || []).map((l) => el('li', { text: typeof l === 'string' ? l : JSON.stringify(l) }))),
  ]));

  // sources
  view.appendChild(el('div', { class: 'card section' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Nguồn & tham chiếu' })]),
    el('ul', { class: 'factor-list pos' }, (m.sources || []).map((l) => el('li', { text: typeof l === 'string' ? l : JSON.stringify(l) }))),
  ]));

  // deploy notes
  view.appendChild(el('div', { class: 'card section' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Vận hành & triển khai' })]),
    el('div', { class: 'small', style: 'line-height:1.7' }, [
      el('p', { html: '<b>Kiến trúc:</b> GitHub Actions chạy hằng ngày → ingestion (Vietstock/vnstock) → validation & chuẩn hoá → panel đặc trưng → quant (BS/Greeks/IV) → scoring → recommendation → xuất JSON tĩnh vào <code>docs/data/</code> → GitHub Pages phục vụ SPA này.' }),
      el('p', { html: '<b>Không có backend:</b> dashboard chỉ đọc JSON tĩnh, nên không thể đặt lệnh hay gửi Telegram trực tiếp. Cảnh báo chạy trên trình duyệt; muốn gửi Telegram/email cần thêm workflow định kỳ gọi bot API.' }),
      el('p', { html: '<b>Tính tái lập:</b> mọi phép biến đổi nằm trong <code>cwintel/</code>, có test; build in ra metadata phiên bản và thời điểm sinh. Không có số liệu nào được nhập tay.' }),
      el('p', { html: '<b>Bảo mật:</b> không có API key trong repo; workflow dùng GitHub Secrets khi cần.' }),
    ]),
  ]));

  view.appendChild(el('div', { class: 'notice danger', html:
    '<b>Miễn trừ trách nhiệm:</b> CW Intelligence là công cụ phân tích và giáo dục, không phải công ty chứng khoán, không đưa ra lời khuyên đầu tư cá nhân hoá. '
    + 'Chứng quyền có thể mất toàn bộ giá trị khi đáo hạn OTM. Nhà đầu tư tự chịu trách nhiệm với quyết định của mình.' }));
}
