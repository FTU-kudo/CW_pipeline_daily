/* Trang Khuyến nghị + Backtest */
import {
  el, fmt, data, pageHead, sectionHead, badge, scoreCell, table, kpiCard, navigate,
  drawLine, drawBars, onThemeChange, openDrawer, closeDrawer, downloadCsv, toast,
} from '../core.js';

/* ===================== KHUYẾN NGHỊ ===================== */
const recState = { rec: '', q: '', sort: 'score', limit: 60 };

const SORTS = {
  score: { label: 'Điểm cao → thấp', fn: (a, b) => (b.score || 0) - (a.score || 0) },
  upside: { label: 'Upside so FV', fn: (a, b) => (b.metrics?.upside_smile_pct || -999) - (a.metrics?.upside_smile_pct || -999) },
  liquidity: { label: 'Thanh khoản', fn: (a, b) => (b.metrics?.value_med20 || 0) - (a.metrics?.value_med20 || 0) },
  dte: { label: 'Thời gian còn lại', fn: (a, b) => (b.metrics?.days_to_maturity || 0) - (a.metrics?.days_to_maturity || 0) },
  premium: { label: 'Premium thấp', fn: (a, b) => (a.metrics?.premium_be_pct || 999) - (b.metrics?.premium_be_pct || 999) },
};

function recCard(card) {
  const m = card.metrics || {};
  const node = el('div', { class: 'rec-card' });
  node.appendChild(el('div', { class: 'rec-card-head' }, [
    el('div', {}, [
      el('div', { class: 'flex' }, [
        el('span', {
          class: 'tbl-ticker', style: 'font-size:16px;cursor:pointer', text: card.ticker,
          onclick: () => navigate(`#/cw/${card.ticker}`),
        }),
        el('span', { class: 'badge tag', text: card.issuer_name || card.issuer }),
      ]),
      el('div', { class: 'tiny muted', style: 'margin-top:3px', text: `${card.underlying} · ${m.moneyness || ''} · ${fmt.dte(m.days_to_maturity)}` }),
    ]),
    el('div', { class: 'right' }, [
      badge(card.recommendation),
      el('div', { class: 'mono', style: 'font-size:18px;margin-top:4px;text-align:right', text: fmt.n(card.score, 1) }),
      el('div', { class: 'tiny muted', style: 'text-align:right', text: 'CW Score' }),
    ]),
  ]));

  const body = el('div', { class: 'rec-card-body' });
  const stats = el('div', { class: 'kv' }, [
    el('div', { class: 'k', text: 'Giá CW' }), el('div', { class: 'v', text: fmt.px(m.price) }),
    el('div', { class: 'k', text: 'Giá trị hợp lý (smile)' }), el('div', { class: 'v ' + fmt.cls(m.upside_smile_pct), text: `${fmt.px(m.fair_value_smile)} (${fmt.pct(m.upside_smile_pct, 1)})` }),
    el('div', { class: 'k', text: 'Premium hoà vốn' }), el('div', { class: 'v', text: fmt.pct(m.premium_be_pct, 1, false) }),
    el('div', { class: 'k', text: 'IV / HV' }), el('div', { class: 'v', text: `${fmt.pct((m.iv || 0) * 100, 0, false)} / ${fmt.pct((m.hv252 || 0) * 100, 0, false)}` }),
    el('div', { class: 'k', text: 'GT giao dịch TB 20P' }), el('div', { class: 'v', text: fmt.vnd(m.value_med20) }),
    el('div', { class: 'k', text: 'Delta / gearing' }), el('div', { class: 'v', text: `${fmt.n(m.delta, 2)} / ${fmt.n(m.eff_gearing, 1)}×` }),
  ]);
  body.appendChild(stats);

  // thành phần điểm
  const comps = el('div', { class: 'comp-bars' });
  const short = {
    underlying_momentum: 'Động lượng', valuation: 'Định giá', liquidity: 'Thanh khoản',
    risk_reward: 'Rủi ro/LN', technical: 'Kỹ thuật', time_to_maturity: 'Thời gian',
  };
  for (const [k, v] of Object.entries(card.components || {})) {
    comps.appendChild(el('div', { class: 'comp-row' }, [
      el('span', { text: short[k] || k }),
      el('span', { class: 'comp-track' }, [el('i', { style: `width:${Math.max(0, Math.min(100, v || 0))}%` })]),
      el('span', { class: 'comp-score', text: fmt.n(v, 0) }),
    ]));
  }
  body.appendChild(comps);

  body.appendChild(el('div', { class: 'thesis', text: (card.thesis || [])[0] || 'Không có luận điểm nổi bật.' }));

  const warnCount = (card.risk_warnings || []).length;
  const footer = el('div', { class: 'flex', style: 'margin-top:8px' }, [
    el('span', { class: 'tiny muted', text: `${(card.positive_factors || []).length} yếu tố + · ${(card.negative_factors || []).length} yếu tố −` }),
    warnCount ? el('span', { class: 'badge HIGH_RISK', text: `${warnCount} cảnh báo` }) : null,
    el('span', { class: 'spacer' }),
    el('button', { class: 'btn sm', text: 'Chi tiết', onclick: () => showCard(card) }),
    el('button', { class: 'btn sm ghost', text: 'Phân tích →', onclick: () => navigate(`#/cw/${card.ticker}`) }),
  ]);
  body.appendChild(footer);
  node.appendChild(body);
  return node;
}

function showCard(card) {
  const wrap = el('div');
  wrap.appendChild(el('div', { class: 'drawer-head' }, [
    el('div', {}, [
      el('h2', { text: `${card.ticker} · ${fmt.rec(card.recommendation)} · ${fmt.n(card.score, 1)} điểm`, style: 'font-size:17px' }),
      el('div', { class: 'tiny muted', text: `${card.underlying} · ${card.issuer_name || card.issuer} · DQ ${fmt.n(card.data_quality, 2)} · Rủi ro ${card.risk_level}` }),
    ]),
    el('button', { class: 'icon-btn', text: '✕', onclick: closeDrawer }),
  ]));

  wrap.appendChild(el('div', { class: 'notice' }, [el('span', { html: `<b>Vì sao?</b> ${esc(card.rec_reason || '')}` })]));

  const sec = (title, list, cls) => {
    const box = el('div', { style: 'margin-top:12px' });
    box.appendChild(el('h3', { style: 'font-size:12px;text-transform:uppercase;letter-spacing:.7px;color:var(--text-2);margin-bottom:6px', text: title }));
    if (!list || !list.length) box.appendChild(el('div', { class: 'tiny muted', text: 'Không có.' }));
    else box.appendChild(el('ul', { class: `factor-list ${cls}` }, list.map((t) => el('li', { text: t }))));
    return box;
  };
  wrap.append(
    sec('Luận điểm', card.thesis, 'pos'),
    sec('Yếu tố tích cực', card.positive_factors, 'pos'),
    sec('Yếu tố tiêu cực', card.negative_factors, 'neg'),
    sec('Cảnh báo rủi ro', card.risk_warnings, 'warn'),
    sec('Điều kiện vô hiệu hoá', card.invalidation, 'warn'),
  );

  const plan = card.trading_plan || {};
  const planBox = el('div', { style: 'margin-top:14px' });
  planBox.appendChild(el('h3', { style: 'font-size:12px;text-transform:uppercase;letter-spacing:.7px;color:var(--text-2);margin-bottom:6px', text: 'Kế hoạch giao dịch (mô phỏng)' }));
  if (!plan.available) {
    planBox.appendChild(el('div', { class: 'empty', text: 'Chưa đủ dữ liệu để lập kế hoạch' }));
    planBox.appendChild(el('div', { class: 'tiny muted center', text: plan.reason || '' }));
  } else {
    planBox.appendChild(el('div', { class: 'plan-grid' }, [
      el('div', { class: 'plan-item' }, [el('div', { class: 'k', text: 'Vùng vào' }), el('div', { class: 'v', text: `${fmt.px(plan.entry_zone?.[0])}–${fmt.px(plan.entry_zone?.[1])}` })]),
      el('div', { class: 'plan-item' }, [el('div', { class: 'k', text: 'Cắt lỗ' }), el('div', { class: 'v down', text: `${fmt.px(plan.stop_loss)} (${fmt.pct(plan.stop_loss_pct, 1)})` })]),
      el('div', { class: 'plan-item' }, [el('div', { class: 'k', text: 'Giữ dự kiến' }), el('div', { class: 'v', text: `${plan.expected_holding_days} phiên` })]),
      el('div', { class: 'plan-item' }, [el('div', { class: 'k', text: 'R:R (+5%)' }), el('div', { class: 'v', text: plan.risk_reward ? plan.risk_reward + '×' : '—' })]),
    ]));
    for (const s of plan.take_profit || []) {
      planBox.appendChild(el('div', { class: 'tiny', style: 'margin-top:6px', html: `Nếu ${esc(card.underlying)} ${fmt.pct(s.underlying_move_pct, 0)} sau ${s.holding_sessions} phiên → CW ≈ <b class="mono">${fmt.px(s.estimated_price)}</b> (${fmt.pct(s.estimated_pl_pct, 1)})` }));
    }
    planBox.appendChild(el('div', { class: 'tiny muted', style: 'margin-top:6px', text: plan.rationale || '' }));
  }
  wrap.appendChild(planBox);
  wrap.appendChild(el('div', { class: 'notice danger', style: 'margin-top:14px', html: card.disclaimer }));
  wrap.appendChild(el('div', { class: 'flex', style: 'margin-top:12px' }, [
    el('button', { class: 'btn primary sm', text: 'Mở phân tích chi tiết →', onclick: () => { closeDrawer(); navigate(`#/cw/${card.ticker}`); } }),
  ]));
  openDrawer(wrap);
}

export async function recommendationsPage(view) {
  const payload = data.recommendations || { cards: [] };
  const cards = payload.cards || [];
  const byRec = {};
  for (const c of cards) byRec[c.recommendation] = (byRec[c.recommendation] || 0) + 1;

  view.appendChild(pageHead(
    'Khuyến nghị định lượng',
    `Mỗi khuyến nghị là kết quả của CW Score (0–100) + cổng chất lượng. Phiên dữ liệu <b>${esc(data.meta?.asofLabel || '')}</b>.`,
    [
      el('button', { class: 'btn sm', text: '⇩ CSV', onclick: () => exportCards(cards) }),
      el('button', { class: 'btn sm', text: 'Phương pháp →', onclick: () => navigate('#/method') }),
    ],
  ));

  view.appendChild(el('div', { class: 'grid kpi section' }, [
    kpiCard({ label: 'MUA MẠNH', value: fmt.n(byRec.STRONG_BUY || 0, 0), sub: 'điểm ≥ 80 và đạt mọi cổng', valueClass: 'up' }),
    kpiCard({ label: 'MUA', value: fmt.n(byRec.BUY || 0, 0), sub: 'điểm 65–79', valueClass: 'up' }),
    kpiCard({ label: 'THEO DÕI', value: fmt.n(byRec.HOLD || 0, 0), sub: 'điểm 45–64' }),
    kpiCard({ label: 'TRÁNH', value: fmt.n(byRec.AVOID || 0, 0), sub: 'điểm 30–44', valueClass: 'down' }),
    kpiCard({ label: 'RỦI RO CAO', value: fmt.n(byRec.HIGH_RISK || 0, 0), sub: 'điểm < 30', valueClass: 'down' }),
    kpiCard({ label: 'Chưa đủ dữ liệu', value: fmt.n(byRec.NO_DATA || 0, 0), sub: 'DQ < 45%' }),
  ]));

  // cổng chất lượng
  const gates = payload.gates || {};
  const gateCard = el('div', { class: 'card section' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Cổng chất lượng — không bao giờ MUA MẠNH khi vi phạm' })]),
    el('div', { class: 'tiny muted', style: 'margin-bottom:8px', text: 'Điểm cao vẫn bị hạ hạng nếu không đạt các điều kiện dưới đây. Đây là lý do nhiều CW có điểm khá nhưng chỉ ở mức THEO DÕI.' }),
  ]);
  const gtable = el('table', { class: 'tbl compact' });
  gtable.innerHTML = '<thead><tr><th>Cổng</th><th>MUA MẠNH</th><th>MUA</th></tr></thead>';
  const gbody = el('tbody');
  const labels = {
    min_liquidity: 'Điểm thanh khoản tối thiểu', min_data_quality: 'Chất lượng dữ liệu tối thiểu',
    min_days_to_maturity: 'Số ngày tới đáo hạn tối thiểu', min_median_value_vnd: 'Giá trị giao dịch TB 20P tối thiểu',
    max_iv_vs_hv_pct: 'IV vượt HV tối đa (%)', min_sessions: 'Số phiên lịch sử tối thiểu',
  };
  for (const key of Object.keys(labels)) {
    const f = (v) => {
      if (v === undefined || v === null) return '—';
      if (key === 'min_median_value_vnd') return fmt.vnd(v);
      if (key === 'max_iv_vs_hv_pct') return fmt.pct(v, 0, false);
      if (key === 'min_data_quality') return fmt.pct(v * 100, 0, false);
      return fmt.n(v, 0);
    };
    gbody.appendChild(el('tr', {}, [
      el('td', { text: labels[key] }),
      el('td', { class: 'num', text: f(gates.STRONG_BUY?.[key]) }),
      el('td', { class: 'num', text: f(gates.BUY?.[key]) }),
    ]));
  }
  gtable.appendChild(gbody);
  gateCard.appendChild(gtable);
  view.appendChild(gateCard);

  // bộ lọc
  const bar = el('div', { class: 'filterbar' });
  const q = el('input', { type: 'search', placeholder: 'Tìm mã / cơ sở / TCPH', style: 'min-width:230px' });
  q.value = recState.q;
  q.oninput = () => { recState.q = q.value.trim(); renderList(); };
  const chips = el('div', { class: 'flex flex-wrap' });
  const chipDefs = [['', 'Tất cả'], ['STRONG_BUY', 'MUA MẠNH'], ['BUY', 'MUA'], ['HOLD', 'THEO DÕI'], ['AVOID', 'TRÁNH'], ['HIGH_RISK', 'RỦI RO CAO']];
  for (const [key, label] of chipDefs) {
    chips.appendChild(el('span', {
      class: 'chip' + (recState.rec === key ? ' on' : ''),
      text: label + (byRec[key || 'ALL'] ? '' : ''),
      onclick: () => { recState.rec = key; Array.from(chips.children).forEach((c) => c.classList.remove('on')); chips.children[chipDefs.findIndex(([k]) => k === key)].classList.add('on'); renderList(); },
    }));
  }
  const sort = el('select', {}, Object.entries(SORTS).map(([k, v]) => el('option', { value: k, text: v.label, selected: recState.sort === k })));
  sort.onchange = () => { recState.sort = sort.value; renderList(); };
  bar.append(q, chips, el('span', { class: 'spacer' }), sort);
  view.appendChild(el('div', { class: 'section' }, [sectionHead('Danh sách khuyến nghị'), bar]));

  const list = el('div', { class: 'rec-grid' });
  const moreWrap = el('div', { class: 'center', style: 'margin-top:12px' });
  view.append(list, moreWrap);

  function renderList() {
    list.innerHTML = '';
    let filtered = cards.filter((c) => {
      if (recState.rec && c.recommendation !== recState.rec) return false;
      if (recState.q) {
        const s = recState.q.toLowerCase();
        if (!c.ticker.toLowerCase().includes(s) && !(c.underlying || '').toLowerCase().includes(s) && !(c.issuer_name || '').toLowerCase().includes(s)) return false;
      }
      return true;
    });
    filtered.sort(SORTS[recState.sort].fn);
    const shown = filtered.slice(0, recState.limit);
    moreWrap.innerHTML = '';
    if (!filtered.length) {
      list.appendChild(el('div', { class: 'empty', text: 'Không có khuyến nghị phù hợp bộ lọc.' }));
      return;
    }
    for (const c of shown) list.appendChild(recCard(c));
    if (filtered.length > shown.length) {
      moreWrap.appendChild(el('button', {
        class: 'btn', text: `Xem thêm (${filtered.length - shown.length})`,
        onclick: () => { recState.limit += 60; renderList(); },
      }));
    } else {
      moreWrap.appendChild(el('div', { class: 'tiny muted', text: `Hiển thị ${shown.length}/${filtered.length} khuyến nghị` }));
    }
  }
  renderList();

  // lịch sử khuyến nghị từ backtest
  const bt = await data.backtestData();
  const history = el('div', { class: 'section', style: 'margin-top:20px' });
  history.appendChild(sectionHead('Lịch sử khuyến nghị — kiểm chứng walk-forward', el('button', { class: 'btn sm', text: 'Xem backtest đầy đủ →', onclick: () => navigate('#/backtest') })));
  history.appendChild(el('div', { class: 'notice', html: 'Mỗi dòng là một khuyến nghị trong quá khứ: giá vào lệnh (phiên kế tiếp), điểm, hạng, lợi nhuận sau đó, MFE/MAE và việc chạm stop/take-profit. '
    + 'Bảng này dùng để đánh giá mô hình, <b>không</b> phải danh sách khuyến nghị hiện tại.' }));
  const trades = (bt.trades || []).slice().sort((a, b) => (b.signal_date || '').localeCompare(a.signal_date || '')).slice(0, 80);
  history.appendChild(table({
    compact: true,
    rows: trades,
    empty: 'Chưa có dữ liệu backtest.',
    columns: [
      { key: 'signal_date', title: 'Ngày tín hiệu', render: (r) => fmt.date(r.signal_date) },
      { key: 'ticker', title: 'Mã', render: (r) => el('span', { class: 'tbl-ticker', text: r.ticker }) },
      { key: 'underlying', title: 'Cơ sở' },
      { key: 'score', title: 'Điểm', align: 'right', render: (r) => fmt.n(r.score, 1) },
      { key: 'recommendation', title: 'Hạng', render: (r) => badge(r.recommendation) },
      { key: 'entry', title: 'Giá vào', align: 'right', render: (r) => fmt.px(r.entry) },
      { key: 'exit', title: 'Giá ra', align: 'right', render: (r) => fmt.px(r.exit) },
      { key: 'ret_pct', title: 'Lợi nhuận', align: 'right', render: (r) => el('span', { class: fmt.cls(r.ret_pct), text: fmt.pct(r.ret_pct, 1) }) },
      { key: 'mfe_pct', title: 'MFE', align: 'right', render: (r) => el('span', { class: 'up', text: fmt.pct(r.mfe_pct, 1) }) },
      { key: 'mae_pct', title: 'MAE', align: 'right', render: (r) => el('span', { class: 'down', text: fmt.pct(r.mae_pct, 1) }) },
      { key: 'holding_sessions', title: 'Phiên giữ', align: 'right' },
      { key: 'exit_reason', title: 'Lý do thoát' },
    ],
  }));
  view.appendChild(history);
}

function exportCards(cards) {
  const rows = cards.map((c) => ({
    Ma: c.ticker, 'Co so': c.underlying, 'TCPH': c.issuer_name, 'Diem': c.score,
    'Khuyen nghi': fmt.rec(c.recommendation), 'Ly do': c.rec_reason,
    'Gia': c.metrics?.price, 'FV smile': c.metrics?.fair_value_smile,
    'Upside (%)': c.metrics?.upside_smile_pct, 'Premium (%)': c.metrics?.premium_be_pct,
    'DTE': c.metrics?.days_to_maturity, 'IV': c.metrics?.iv, 'HV': c.metrics?.hv252,
    'GT 20P': c.metrics?.value_med20, 'DQ': c.data_quality, 'Rui ro': c.risk_level,
    'Luan diem': (c.thesis || []).join(' | '),
  }));
  downloadCsv(`cw-recommendations-${data.meta?.asof || ''}.csv`, rows);
  toast('Đã xuất CSV khuyến nghị');
}

/* ===================== BACKTEST ===================== */
function metricCard(labelKey, label, value, sub, cls) {
  return kpiCard({ label, value, sub, valueClass: cls });
}

export async function backtestPage(view) {
  const bt = await data.backtestData();
  const s = bt.summary || {};
  const ts = bt.trade_stats || {};
  const strat = s.score_top || {};

  view.appendChild(pageHead(
    'Backtest walk-forward',
    `Tín hiệu chấm điểm tại ngày T, vào lệnh phiên T+1, nắm giữ ${bt.config?.holding_sessions || '—'} phiên. `
    + `Chi phí ${bt.config?.cost_per_side_bps ? (bt.config.cost_per_side_bps / 100).toFixed(2) : '—'}%/chiều (bid-ask + phí + trượt giá).`,
    [el('button', { class: 'btn sm', text: '⇩ Tải trades (CSV)', onclick: () => exportTrades(bt) })],
  ));

  view.appendChild(el('div', { class: 'notice danger', html: '<b>Kết quả được báo cáo trung thực, kể cả khi xấu.</b> Chiến lược top-5 theo CW Score <b>thua lỗ</b> trong giai đoạn kiểm định — nguyên nhân chính là cấu trúc giảm giá của CW Việt Nam (theta + IV cao). '
    + 'Điều này không bị che giấu; các bộ lọc có kỳ vọng dương được trình bày trong bảng độ nhạy bên dưới.' }));

  view.appendChild(el('div', { class: 'grid kpi section' }, [
    kpiCard({ label: 'Tổng lợi nhuận — top-5 Score', value: fmt.pct(strat.total_return_pct, 1), sub: `CAGR ${fmt.pct(strat.cagr_pct, 1)}`, valueClass: strat.total_return_pct >= 0 ? 'up' : 'down' }),
    kpiCard({ label: 'Sharpe', value: fmt.n(strat.sharpe, 2), sub: `Vol ${fmt.pct(strat.ann_vol_pct, 1, false)}` }),
    kpiCard({ label: 'Max drawdown', value: fmt.pct(strat.max_drawdown_pct, 1), sub: `${bt.config?.n_signal_dates || 0} kỳ tái cấu trúc`, valueClass: 'down' }),
    kpiCard({ label: 'Tỷ lệ thắng', value: fmt.pct(ts.win_rate_pct, 1, false), sub: `${ts.n_trades} lệnh` }),
    kpiCard({ label: 'Profit factor', value: fmt.n(ts.profit_factor, 2), sub: `TB thắng ${fmt.pct(ts.avg_win_pct, 1)} / lỗ ${fmt.pct(ts.avg_loss_pct, 1)}` }),
    kpiCard({ label: 'Lợi nhuận TB/lệnh', value: fmt.pct(ts.avg_return_pct, 2), sub: `trung vị ${fmt.pct(ts.median_return_pct, 1)}`, valueClass: ts.avg_return_pct >= 0 ? 'up' : 'down' }),
    kpiCard({ label: 'Stop / TP hit', value: `${fmt.pct(ts.stop_hit_rate_pct, 0, false)} / ${fmt.pct(ts.tp_hit_rate_pct, 0, false)}`, sub: `giữ TB ${fmt.n(ts.avg_holding_sessions, 1)} phiên` }),
    kpiCard({ label: 'Benchmark cổ phiếu cơ sở', value: fmt.pct(s.underlying_ew?.total_return_pct, 1), sub: `Sharpe ${fmt.n(s.underlying_ew?.sharpe, 2)}`, valueClass: s.underlying_ew?.total_return_pct >= 0 ? 'up' : 'down' }),
  ]));

  // equity curve
  const curve = bt.curve || [];
  const eqCanvas = el('canvas');
  const eqCard = el('div', { class: 'card section' }, [
    el('div', { class: 'card-title' }, [
      el('h3', { text: 'Đường vốn — 4 chiến lược (base 100)' }),
      el('div', { class: 'legend-inline' }, [
        el('span', { html: '<i style="background:var(--accent)"></i>Top-5 Score' }),
        el('span', { html: '<i style="background:var(--accent-2)"></i>Toàn vũ trụ' }),
        el('span', { html: '<i style="background:var(--violet)"></i>Ngẫu nhiên' }),
        el('span', { html: '<i style="background:var(--warn)"></i>Cổ phiếu cơ sở' }),
      ]),
    ]),
    el('div', { class: 'chart-box' }, [eqCanvas]),
  ]);
  view.appendChild(eqCard);
  const eqPaint = () => {
    const g = getComputedStyle(document.documentElement);
    drawLine(eqCanvas, {
      height: 300, labels: curve.map((c) => fmt.date(c.date)),
      series: [
        { name: 'Top-5 Score', values: curve.map((c) => c.eq_score), color: g.getPropertyValue('--accent').trim() },
        { name: 'Toàn vũ trụ', values: curve.map((c) => c.eq_ew), color: g.getPropertyValue('--accent-2').trim() },
        { name: 'Ngẫu nhiên', values: curve.map((c) => c.eq_random), color: g.getPropertyValue('--violet').trim() },
        { name: 'Cổ phiếu cơ sở', values: curve.map((c) => c.eq_underlying), color: g.getPropertyValue('--warn').trim() },
      ],
      yFormat: (v) => fmt.n(v, 0),
    });
  };
  requestAnimationFrame(eqPaint);
  onThemeChange(eqPaint);
  eqCanvas.style.height = '300px';

  // summary table + monthly
  const sumTable = table({
    compact: true,
    rows: Object.entries(s).map(([k, v]) => ({ k, ...v })),
    columns: [
      { key: 'k', title: 'Chiến lược', render: (r) => ({ score_top: 'Top-5 theo CW Score', ew_universe: 'Toàn vũ trụ CW', random: 'Ngẫu nhiên', underlying_ew: 'Cổ phiếu cơ sở (EW)' }[r.k] || r.k) },
      { key: 'total_return_pct', title: 'Tổng LN', align: 'right', render: (r) => el('span', { class: fmt.cls(r.total_return_pct), text: fmt.pct(r.total_return_pct, 1) }) },
      { key: 'cagr_pct', title: 'CAGR', align: 'right', render: (r) => fmt.pct(r.cagr_pct, 1) },
      { key: 'ann_vol_pct', title: 'Vol', align: 'right', render: (r) => fmt.pct(r.ann_vol_pct, 1, false) },
      { key: 'sharpe', title: 'Sharpe', align: 'right', render: (r) => fmt.n(r.sharpe, 2) },
      { key: 'max_drawdown_pct', title: 'MDD', align: 'right', render: (r) => el('span', { class: 'down', text: fmt.pct(r.max_drawdown_pct, 1) }) },
      { key: 'avg_period_ret_pct', title: 'TB/kỳ', align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_period_ret_pct), text: fmt.pct(r.avg_period_ret_pct, 2) }) },
      { key: 'positive_periods_pct', title: '% kỳ dương', align: 'right', render: (r) => fmt.pct(r.positive_periods_pct, 1, false) },
    ],
  });

  const monthly = bt.monthly || [];
  const mCanvas = el('canvas');
  const mCard = el('div', { class: 'card' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Lợi nhuận theo tháng — top-5 Score' })]),
    el('div', { class: 'chart-box' }, [mCanvas]),
  ]);
  view.appendChild(el('div', { class: 'grid cols-2 section' }, [
    el('div', {}, [sectionHead('So sánh chiến lược'), sumTable]),
    mCard,
  ]));
  const mPaint = () => drawBars(mCanvas, {
    height: 220, labels: monthly.map((m) => m.month.slice(2)),
    values: monthly.map((m) => m.ret_pct),
    colors: monthly.map((m) => (m.ret_pct >= 0
      ? getComputedStyle(document.documentElement).getPropertyValue('--up').trim()
      : getComputedStyle(document.documentElement).getPropertyValue('--down').trim())),
    tipFormat: (v) => fmt.pct(v, 2),
  });
  requestAnimationFrame(mPaint);
  onThemeChange(mPaint);
  mCanvas.style.height = '220px';

  // theo chế độ thị trường (suy ra từ benchmark cổ phiếu cơ sở của từng kỳ)
  const regimeRows = (() => {
    const groups = { 'Cơ sở TĂNG': [], 'Cơ sở GIẢM': [] };
    for (const c of curve) {
      if (!Number.isFinite(c.score_top) || !Number.isFinite(c.underlying_ew)) continue;
      (c.underlying_ew > 0 ? groups['Cơ sở TĂNG'] : groups['Cơ sở GIẢM']).push(c.score_top);
    }
    return Object.entries(groups).map(([label, arr]) => {
      if (!arr.length) return { label, n: 0 };
      const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
      const wins = arr.filter((v) => v > 0).length;
      return {
        label, n: arr.length,
        avg: mean * 100,
        median: [...arr].sort((a, b) => a - b)[Math.floor(arr.length / 2)] * 100,
        win: (wins / arr.length) * 100,
      };
    });
  })();

  // buckets
  const buckets = bt.buckets || [];
  const bCanvas = el('canvas');
  const bCard = el('div', { class: 'card' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Lợi nhuận 20 phiên tới theo nhóm điểm (toàn bộ CW)' })]),
    el('div', { class: 'chart-box' }, [bCanvas]),
    el('div', { class: 'tiny muted', text: 'Đây là kiểm định tính đơn điệu của thang điểm: nhóm điểm cao phải có lợi nhuận kỳ vọng tốt hơn. Chênh lệch hiện còn yếu.' }),
  ]);
  view.appendChild(el('div', { class: 'grid cols-2 section' }, [bCard, (() => {
    const card = el('div', { class: 'card' });
    card.appendChild(el('div', { class: 'card-title' }, [el('h3', { text: 'Thống kê theo nhóm điểm' })]));
    card.appendChild(table({
      compact: true,
      rows: buckets,
      columns: [
        { key: 'bucket', title: 'Nhóm điểm' },
        { key: 'n', title: 'n', align: 'right' },
        { key: 'avg_ret_pct', title: 'TB', align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_ret_pct), text: fmt.pct(r.avg_ret_pct, 1) }) },
        { key: 'median_ret_pct', title: 'Trung vị', align: 'right', render: (r) => el('span', { class: fmt.cls(r.median_ret_pct), text: fmt.pct(r.median_ret_pct, 1) }) },
        { key: 'win_rate_pct', title: 'Win rate', align: 'right', render: (r) => fmt.pct(r.win_rate_pct, 1, false) },
      ],
    }));
    return card;
  })()]));
  const bPaint = () => drawBars(bCanvas, {
    height: 200, labels: buckets.map((b) => b.bucket),
    values: buckets.map((b) => b.avg_ret_pct),
    colors: buckets.map((b) => (b.avg_ret_pct >= 0
      ? getComputedStyle(document.documentElement).getPropertyValue('--up').trim()
      : getComputedStyle(document.documentElement).getPropertyValue('--down').trim())),
    tipFormat: (v, i) => `${fmt.pct(v, 2)} · win ${fmt.pct(buckets[i].win_rate_pct, 1, false)} · n=${buckets[i].n}`,
    yFormat: (v) => fmt.pct(v, 0),
  });
  requestAnimationFrame(bPaint);
  onThemeChange(bPaint);
  bCanvas.style.height = '200px';

  // regime
  const regimeCard = el('div', { class: 'card section' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Kết quả theo chế độ thị trường' })]),
    el('div', { class: 'tiny muted', style: 'margin-bottom:8px', text: 'Chia 43 kỳ tái cấu trúc theo dấu lợi nhuận của cổ phiếu cơ sở trong cùng kỳ — cho thấy chiến lược có phụ thuộc vào xu hướng thị trường hay không.' }),
    table({
      compact: true, rows: regimeRows,
      columns: [
        { key: 'label', title: 'Chế độ' },
        { key: 'n', title: 'Số kỳ', align: 'right' },
        { key: 'avg', title: 'TB/kỳ', align: 'right', render: (r) => (r.n ? el('span', { class: fmt.cls(r.avg), text: fmt.pct(r.avg, 2) }) : '—') },
        { key: 'median', title: 'Trung vị', align: 'right', render: (r) => (r.n ? el('span', { class: fmt.cls(r.median), text: fmt.pct(r.median, 2) }) : '—') },
        { key: 'win', title: '% kỳ dương', align: 'right', render: (r) => (r.n ? fmt.pct(r.win, 1, false) : '—') },
      ],
    }),
  ]);
  view.appendChild(regimeCard);

  // sensitivity
  const sensCard = el('div', { class: 'card section' });
  sensCard.appendChild(el('div', { class: 'card-title' }, [el('h3', { text: 'Độ nhạy & kiểm định bộ lọc' })]));
  const sensTables = el('div', { class: 'grid cols-2' });
  sensTables.appendChild(el('div', {}, [
    el('div', { class: 'tiny muted', style: 'margin-bottom:4px', text: 'Thời gian nắm giữ' }),
    table({
      compact: true,
      rows: bt.holding_sensitivity || [],
      columns: [
        { key: 'holding_sessions', title: 'Phiên giữ', align: 'right' },
        { key: 'n_trades', title: 'Số lệnh', align: 'right' },
        { key: 'avg_trade_ret_pct', title: 'TB/lệnh', align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_trade_ret_pct), text: fmt.pct(r.avg_trade_ret_pct, 2) }) },
        { key: 'win_rate_pct', title: 'Win', align: 'right', render: (r) => fmt.pct(r.win_rate_pct, 1, false) },
        { key: 'total_return_pct', title: 'Tổng', align: 'right', render: (r) => el('span', { class: fmt.cls(r.total_return_pct), text: fmt.pct(r.total_return_pct, 1) }) },
      ],
    }),
  ]));
  sensTables.appendChild(el('div', {}, [
    el('div', { class: 'tiny muted', style: 'margin-bottom:4px', text: 'Ngưỡng điểm tối thiểu' }),
    table({
      compact: true,
      rows: bt.gate_sensitivity || [],
      columns: [
        { key: 'score_gate', title: 'Ngưỡng', align: 'right' },
        { key: 'n_trades', title: 'Số lệnh', align: 'right' },
        { key: 'avg_trade_ret_pct', title: 'TB/lệnh', align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_trade_ret_pct), text: fmt.pct(r.avg_trade_ret_pct, 2) }) },
        { key: 'win_rate_pct', title: 'Win', align: 'right', render: (r) => fmt.pct(r.win_rate_pct, 1, false) },
        { key: 'total_return_pct', title: 'Tổng', align: 'right', render: (r) => el('span', { class: fmt.cls(r.total_return_pct), text: fmt.pct(r.total_return_pct, 1) }) },
      ],
    }),
  ]));
  sensTables.appendChild(el('div', {}, [
    el('div', { class: 'tiny muted', style: 'margin-bottom:4px', text: 'Chi phí mỗi chiều' }),
    table({
      compact: true,
      rows: bt.cost_sensitivity || [],
      columns: [
        { key: 'cost_per_side_pct', title: '%/chiều', align: 'right', render: (r) => fmt.pct(r.cost_per_side_pct, 2, false) },
        { key: 'avg_trade_ret_pct', title: 'TB/lệnh', align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_trade_ret_pct), text: fmt.pct(r.avg_trade_ret_pct, 2) }) },
        { key: 'win_rate_pct', title: 'Win', align: 'right', render: (r) => fmt.pct(r.win_rate_pct, 1, false) },
      ],
    }),
  ]));
  sensTables.appendChild(el('div', {}, [
    el('div', { class: 'tiny muted', style: 'margin-bottom:4px', text: 'Bộ lọc bổ sung (mỗi lệnh)' }),
    table({
      compact: true,
      rows: bt.filter_sensitivity || [],
      columns: [
        { key: 'filter', title: 'Bộ lọc' },
        { key: 'n_trades', title: 'n', align: 'right' },
        { key: 'avg_trade_ret_pct', title: 'TB', align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_trade_ret_pct), text: fmt.pct(r.avg_trade_ret_pct, 2) }) },
        { key: 'win_rate_pct', title: 'Win', align: 'right', render: (r) => fmt.pct(r.win_rate_pct, 1, false) },
        { key: 'profit_factor', title: 'PF', align: 'right', render: (r) => fmt.n(r.profit_factor, 2) },
        { key: 'total_return_pct', title: 'Tổng', align: 'right', render: (r) => el('span', { class: fmt.cls(r.total_return_pct), text: fmt.pct(r.total_return_pct, 1) }) },
      ],
    }),
  ]));
  sensCard.appendChild(sensTables);
  sensCard.appendChild(el('div', { class: 'notice ok', html: 'Bộ lọc <b>IV ≤ HV</b> (mua khi IV không cao hơn biến động lịch sử) là biến thể duy nhất có kỳ vọng dương trên mỗi lệnh trong giai đoạn này, tuy tổng lợi nhuận vẫn âm do chi phí và đuôi rủi ro. '
    + 'Đây là lý do cổng <b>IV ≤ HV + 40%</b> được đưa vào điều kiện MUA/MUA MẠNH.' }));
  view.appendChild(sensCard);

  // by issuer/underlying
  view.appendChild(el('div', { class: 'grid cols-2 section' }, [
    el('div', {}, [sectionHead('Kết quả theo tổ chức phát hành'), table({
      compact: true, rows: bt.by_issuer || [],
      columns: [
        { key: 'key', title: 'TCPH' },
        { key: 'n', title: 'Số lệnh', align: 'right' },
        { key: 'avg_ret_pct', title: 'TB/lệnh', align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_ret_pct), text: fmt.pct(r.avg_ret_pct, 2) }) },
        { key: 'win_rate_pct', title: 'Win', align: 'right', render: (r) => fmt.pct(r.win_rate_pct, 1, false) },
      ],
    })]),
    el('div', {}, [sectionHead('Kết quả theo cổ phiếu cơ sở'), table({
      compact: true, rows: bt.by_underlying || [],
      columns: [
        { key: 'key', title: 'Cơ sở' },
        { key: 'n', title: 'Số lệnh', align: 'right' },
        { key: 'avg_ret_pct', title: 'TB/lệnh', align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_ret_pct), text: fmt.pct(r.avg_ret_pct, 2) }) },
        { key: 'win_rate_pct', title: 'Win', align: 'right', render: (r) => fmt.pct(r.win_rate_pct, 1, false) },
      ],
    })]),
  ]));

  // trades
  const tradesSection = el('div', { class: 'section' });
  tradesSection.appendChild(sectionHead(`Toàn bộ lệnh (${(bt.trades || []).length})`));
  tradesSection.appendChild(table({
    compact: true,
    rows: (bt.trades || []).slice().reverse(),
    columns: [
      { key: 'entry_date', title: 'Vào', render: (r) => fmt.date(r.entry_date) },
      { key: 'exit_date', title: 'Ra', render: (r) => fmt.date(r.exit_date) },
      { key: 'ticker', title: 'Mã', render: (r) => el('span', { class: 'tbl-ticker', text: r.ticker }) },
      { key: 'underlying', title: 'Cơ sở' },
      { key: 'score', title: 'Điểm', align: 'right', render: (r) => fmt.n(r.score, 1) },
      { key: 'entry', title: 'Giá vào', align: 'right', render: (r) => fmt.px(r.entry) },
      { key: 'ret_pct', title: 'LN', align: 'right', render: (r) => el('span', { class: fmt.cls(r.ret_pct), text: fmt.pct(r.ret_pct, 1) }) },
      { key: 'mfe_pct', title: 'MFE', align: 'right', render: (r) => el('span', { class: 'up', text: fmt.pct(r.mfe_pct, 1) }) },
      { key: 'mae_pct', title: 'MAE', align: 'right', render: (r) => el('span', { class: 'down', text: fmt.pct(r.mae_pct, 1) }) },
      { key: 'holding_sessions', title: 'Phiên', align: 'right' },
      { key: 'exit_reason', title: 'Thoát' },
    ],
  }));
  view.appendChild(tradesSection);

  // caveats + config
  view.appendChild(el('div', { class: 'card' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: 'Giả định, giới hạn và chống thiên lệch' })]),
    el('ul', { class: 'factor-list warn', style: 'padding-left:0' }, (bt.caveats || []).map((c) => el('li', { text: c }))),
    el('div', { class: 'formula', style: 'margin-top:8px', text: `start=${bt.config?.start} · end=${bt.config?.end} · rebalance=${bt.config?.rebalance} phiên · top_n=${bt.config?.top_n} · chi phí=${(bt.config?.cost_per_side_bps / 100).toFixed(2)}%/chiều · r=${bt.config?.risk_free}` }),
    el('div', { class: 'tiny muted', style: 'margin-top:6px', text: 'Chi phí: ' + (bt.config?.cost_breakdown || 'n/a') }),
  ]));
}

function exportTrades(bt) {
  downloadCsv(`cw-backtest-trades-${bt.config?.end || ''}.csv`, bt.trades || []);
  toast('Đã xuất CSV trades');
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
