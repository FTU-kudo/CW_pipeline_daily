/* Trang Khuyến nghị + Backtest */
import {
  el, fmt, data, pageHead, sectionHead, badge, scoreCell, table, kpiCard, navigate,
  drawLine, onThemeChange, openDrawer, closeDrawer, downloadCsv, toast,
} from '../core.js';
import { bi, getLang } from '../i18n.js';

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

/** Song ngữ cho câu có số liệu: EN mode → tiếng Anh, VI+EN → cả hai. */
const T = (vi, en) => (getLang() === 'both' ? `${vi} · ${en}` : bi(vi, en));

const STRAT_LABEL = {
  score_top: ['Top-5 theo CW Score (sau phí)', 'Top-5 by CW Score (net)'],
  score_top_gross: ['Top-5 theo CW Score (trước phí)', 'Top-5 by CW Score (gross)'],
  ew_universe: ['Toàn vũ trụ CW (EW)', 'Whole CW universe (EW)'],
  random: ['Ngẫu nhiên 5 mã (10 seed)', 'Random 5 warrants (10 seeds)'],
  underlying_ew: ['Cổ phiếu cơ sở (EW)', 'Underlying stocks (EW)'],
};

const EXIT_LABEL = {
  horizon: ['Hết hạn giữ', 'Holding period end'],
  stop: ['Stop-loss', 'Stop-loss'],
  take_profit: ['Take-profit', 'Take-profit'],
  data_end: ['Hết dữ liệu', 'No more data'],
};

export async function backtestPage(view) {
  const bt = await data.backtestData();
  const cfg = bt.config || {};
  const s = bt.summary || {};
  const ts = bt.trade_stats || {};
  const net = s.score_top || {};
  const gross = s.score_top_gross || {};
  const ew = s.ew_universe || {};
  const rnd = s.random || {};
  const bench = s.underlying_ew || {};
  const curve = bt.curve || [];
  const monthly = bt.monthly || [];
  const buckets = bt.buckets || [];
  const regime = bt.regime || {};
  const caveats = bt.caveats || [];
  const caveatsEn = bt.caveats_en || [];
  const bestFilter = (bt.filter_sensitivity || [])
    .filter((r) => Number.isFinite(r.total_return_pct))
    .reduce((a, b) => (!a || b.total_return_pct > a.total_return_pct ? b : a), null);
  const bestFilterLabel = bestFilter ? T(bestFilter.filter, bestFilter.filter_en || bestFilter.filter) : '';

  view.appendChild(pageHead(
    'Backtest walk-forward',
    T(
      `Chấm điểm tại ngày T · vào lệnh phiên T+1 · tái cân bằng ${cfg.rebalance || '—'} · `
        + `top-${cfg.top_n || '—'} · chi phí ${fmt.n(cfg.cost_per_side_pct, 2)}%/chiều `
        + `(${fmt.n(cfg.round_trip_pct, 1)}%/vòng) · ${fmt.date(cfg.start)} → ${fmt.date(cfg.end)}`,
      `Score on day T · enter on session T+1 · rebalance ${cfg.rebalance_sessions
        ? `every ${cfg.rebalance_sessions} sessions` : '—'} · top-${cfg.top_n || '—'} · `
        + `cost ${fmt.n(cfg.cost_per_side_pct, 2)}%/side (${fmt.n(cfg.round_trip_pct, 1)}%/round trip) · `
        + `${fmt.date(cfg.start)} → ${fmt.date(cfg.end)}`,
    ),
    [el('button', {
      class: 'btn sm', text: '⇩ Tải trades (CSV)', onclick: () => exportTrades(bt),
    }), el('button', {
      class: 'btn sm', text: 'Phương pháp →', onclick: () => navigate('#/method'),
    })],
  ));

  /* ---------- 1. Kết luận ---------- */
  view.appendChild(el('div', { class: 'card bt-verdict' }, [
    el('div', { class: 'bt-verdict-row' }, [
      el('span', { class: 'bt-verdict-tag down', text: T('Kết quả thật', 'The honest result') }),
      el('div', { class: 'bt-verdict-text', text: T(
        `Top-5 theo CW Score đạt ${fmt.pct(net.total_return_pct, 1)} sau phí và `
          + `${fmt.pct(gross.total_return_pct, 1)} trước phí — chi phí giao dịch ăn `
          + `${fmt.pct(bt.cost_drag_pct, 1)}. Cùng kỳ, rổ cổ phiếu cơ sở equal-weight đạt `
          + `${fmt.pct(bench.total_return_pct, 1)}.`,
        `The top-5 by CW Score returned ${fmt.pct(net.total_return_pct, 1)} after costs and `
          + `${fmt.pct(gross.total_return_pct, 1)} before costs — trading costs consumed `
          + `${fmt.pct(bt.cost_drag_pct, 1)}. Over the same period the equal-weight underlying `
          + `basket returned ${fmt.pct(bench.total_return_pct, 1)}.`,
      ) }),
    ]),
    bestFilter ? el('div', { class: 'bt-verdict-text', text: T(
      `Bộ lọc duy nhất cho tổng lợi nhuận dương: “${bestFilterLabel}” → `
        + `${fmt.pct(bestFilter.total_return_pct, 1)} tổng, ${fmt.pct(bestFilter.avg_trade_ret_pct, 2)}/lệnh, `
        + `nhưng chỉ ${fmt.n(bestFilter.n_trades, 0)} lệnh — quá ít để coi là bằng chứng. Xem bảng bộ lọc bên dưới.`,
      `The only filter with a positive total return: “${bestFilterLabel}” → `
        + `${fmt.pct(bestFilter.total_return_pct, 1)} total, ${fmt.pct(bestFilter.avg_trade_ret_pct, 2)}/trade, `
        + `but only ${fmt.n(bestFilter.n_trades, 0)} trades — far too few to treat as evidence. `
        + `See the filter table below.`) }) : null,
    el('div', { class: 'bt-verdict-text muted', text: T(
      'Chiến lược thua lỗ trong giai đoạn kiểm định và điều đó không bị che giấu. Ba mục dưới đây '
        + 'tách rõ tín hiệu yếu, chi phí và beta thị trường — để biết phần nào có thể cải thiện và '
        + 'phần nào là bản chất của chứng quyền.',
      'The strategy lost money over the test period and that is not hidden. The three sections below '
        + 'separate weak signal, costs and market beta — so you can see which part can be improved and '
        + 'which part is the nature of warrants.',
    ) }),
  ]));

  /* ---------- 2. KPI ---------- */
  const kpi = (vi, en, value, sub, cls) => kpiCard({ label: T(vi, en), value, sub, valueClass: cls });
  view.appendChild(el('div', { class: 'grid kpi section' }, [
    kpi('Tổng lợi nhuận (sau phí)', 'Total return (net)', fmt.pct(net.total_return_pct, 1),
      T(`vốn cuối kỳ ${fmt.n(net.final_equity, 0)} trên 100`,
        `final equity ${fmt.n(net.final_equity, 0)} per 100`),
      (net.total_return_pct || 0) >= 0 ? 'up' : 'down'),
    kpi('Trước phí giao dịch', 'Before trading costs', fmt.pct(gross.total_return_pct, 1),
      T(`chi phí ăn ${fmt.pct(bt.cost_drag_pct, 1)}`, `costs ate ${fmt.pct(bt.cost_drag_pct, 1)}`),
      (gross.total_return_pct || 0) >= 0 ? 'up' : 'down'),
    kpi('CAGR (sau phí)', 'CAGR (net)', fmt.pct(net.cagr_pct, 1),
      `Sharpe ${fmt.n(net.sharpe, 2)} · Sortino ${fmt.n(net.sortino, 2)}`,
      (net.cagr_pct || 0) >= 0 ? 'up' : 'down'),
    kpi('Drawdown lớn nhất', 'Maximum drawdown', fmt.pct(net.max_drawdown_pct, 1),
      T(`theo đường vốn từng phiên (${fmt.n(cfg.n_sessions, 0)} phiên)`,
        `from the daily equity path (${fmt.n(cfg.n_sessions, 0)} sessions)`), 'down'),
    kpi('Tỷ lệ thắng (lệnh)', 'Win rate (trades)', fmt.pct(ts.win_rate_pct, 1, false),
      T(`${fmt.n(ts.n_trades, 0)} lệnh · PF ${fmt.n(ts.profit_factor, 2)}`,
        `${fmt.n(ts.n_trades, 0)} trades · PF ${fmt.n(ts.profit_factor, 2)}`)),
    kpi('Lãi TB mỗi lệnh', 'Average P&L per trade', fmt.pct(ts.avg_return_pct, 2),
      T(`trung vị ${fmt.pct(ts.median_return_pct, 1)} · payoff ${fmt.n(ts.payoff_ratio, 2)}`,
        `median ${fmt.pct(ts.median_return_pct, 1)} · payoff ${fmt.n(ts.payoff_ratio, 2)}`),
      (ts.avg_return_pct || 0) >= 0 ? 'up' : 'down'),
    kpi('Cổ phiếu cơ sở (EW)', 'Underlying (EW)', fmt.pct(bench.total_return_pct, 1),
      `Sharpe ${fmt.n(bench.sharpe, 2)} · MDD ${fmt.pct(bench.max_drawdown_pct, 1)}`,
      (bench.total_return_pct || 0) >= 0 ? 'up' : 'down'),
    kpi('Toàn vũ trụ CW', 'Whole CW universe', fmt.pct(ew.total_return_pct, 1),
      T(`ngẫu nhiên ${fmt.pct(rnd.total_return_pct, 1)} · top-5 hơn EW `
          + `${fmt.pct((net.total_return_pct || 0) - (ew.total_return_pct || 0), 1)}`,
        `random ${fmt.pct(rnd.total_return_pct, 1)} · top-5 beats EW by `
          + `${fmt.pct((net.total_return_pct || 0) - (ew.total_return_pct || 0), 1)}`),
      (ew.total_return_pct || 0) >= 0 ? 'up' : 'down'),
  ]));

  /* ---------- 3. Đường vốn + drawdown ---------- */
  const eqCanvas = el('canvas');
  const ddCanvas = el('canvas');
  view.appendChild(el('div', { class: 'card section' }, [
    el('div', { class: 'card-title' }, [
      el('h3', { text: T('Đường vốn theo phiên (base 100)', 'Daily equity path (base 100)') }),
      el('span', { class: 'tiny muted', text: T('Đánh dấu theo giá đóng cửa từng phiên',
        'Marked to market at each session close') }),
    ]),
    el('div', { class: 'chart-box' }, [eqCanvas]),
  ]));
  view.appendChild(el('div', { class: 'card section' }, [
    el('div', { class: 'card-title' }, [
      el('h3', { text: T('Drawdown của chiến lược top-5', 'Drawdown of the top-5 strategy') }),
      el('span', { class: 'tiny muted', text: T(`đáy ${fmt.pct(net.max_drawdown_pct, 1)}`,
        `trough ${fmt.pct(net.max_drawdown_pct, 1)}`) }),
    ]),
    el('div', { class: 'chart-box' }, [ddCanvas]),
  ]));

  const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const labels = curve.map((c) => fmt.date(c.date));
  const eqPaint = () => drawLine(eqCanvas, {
    height: 300,
    labels,
    series: [
      { name: STRAT_LABEL.score_top[getLang() === 'en' ? 1 : 0], values: curve.map((c) => c.eq_score), color: cssVar('--accent'), width: 2.2 },
      { name: STRAT_LABEL.score_top_gross[getLang() === 'en' ? 1 : 0], values: curve.map((c) => c.eq_gross), color: cssVar('--accent-2') },
      { name: STRAT_LABEL.ew_universe[getLang() === 'en' ? 1 : 0], values: curve.map((c) => c.eq_ew), color: cssVar('--violet') },
      { name: STRAT_LABEL.random[getLang() === 'en' ? 1 : 0], values: curve.map((c) => c.eq_random), color: cssVar('--text-3') },
      { name: STRAT_LABEL.underlying_ew[getLang() === 'en' ? 1 : 0], values: curve.map((c) => c.eq_underlying), color: cssVar('--warn'), width: 2.2 },
    ],
    yFormat: (v) => fmt.n(v, 0),
  });
  const ddPaint = () => drawLine(ddCanvas, {
    height: 150,
    labels,
    series: [{ name: 'Drawdown', values: curve.map((c) => c.dd_score), color: cssVar('--down'), fill: true, width: 1.4 }],
    zeroLine: true,
    yFormat: (v) => fmt.pct(v, 0, false),
  });
  requestAnimationFrame(() => { eqPaint(); ddPaint(); });
  onThemeChange(() => { eqPaint(); ddPaint(); });

  /* ---------- 4. So sánh chiến lược ---------- */
  const stratRows = Object.keys(STRAT_LABEL).filter((k) => s[k]).map((k) => ({ k, ...s[k] }));
  view.appendChild(el('div', { class: 'section' }, [
    sectionHead('So sánh chiến lược', el('span', { class: 'tiny muted',
      text: T('CAGR/Sharpe tính theo kỳ tái cân bằng · MDD theo phiên',
        'CAGR/Sharpe from rebalance periods · MDD from daily path') })),
    table({
      compact: true,
      rows: stratRows,
      columns: [
        { key: 'k', title: T('Chiến lược', 'Strategy'), render: (r) => el('span', { class: 'strong', text: T(...(STRAT_LABEL[r.k] || [r.k, r.k])) }) },
        { key: 'total_return_pct', title: T('Tổng LN', 'Total'), align: 'right', render: (r) => el('span', { class: fmt.cls(r.total_return_pct), text: fmt.pct(r.total_return_pct, 1) }) },
        { key: 'cagr_pct', title: 'CAGR', align: 'right', render: (r) => fmt.pct(r.cagr_pct, 1) },
        { key: 'ann_vol_pct', title: T('Vol/năm', 'Vol p.a.'), align: 'right', render: (r) => fmt.pct(r.ann_vol_pct, 1, false) },
        { key: 'sharpe', title: 'Sharpe', align: 'right', render: (r) => fmt.n(r.sharpe, 2) },
        { key: 'max_drawdown_pct', title: 'MDD', align: 'right', render: (r) => el('span', { class: 'down', text: fmt.pct(r.max_drawdown_pct, 1) }) },
        { key: 'positive_periods_pct', title: T('% kỳ dương', '% positive periods'), align: 'right', render: (r) => fmt.pct(r.positive_periods_pct, 0, false) },
        { key: 'final_equity', title: T('Vốn cuối (100)', 'Final equity (100)'), align: 'right', render: (r) => el('span', { class: 'mono', text: fmt.n(r.final_equity, 1) }) },
      ],
    }),
  ]));

  /* ---------- 5. Lợi nhuận theo tháng (heatmap) ---------- */
  view.appendChild(el('div', { class: 'card section' }, [
    el('div', { class: 'card-title' }, [
      el('h3', { text: T('Lợi nhuận theo tháng — top-5 Score (sau phí)',
        'Monthly returns — top-5 by score (net)') }),
      heatSummary(monthly),
    ]),
    monthlyHeatmap(monthly),
    el('div', { class: 'tiny muted', style: 'margin-top:8px', text: T(
      'Mỗi ô là lợi nhuận của tháng đó tính từ đường vốn theo phiên (không phải trung bình các kỳ). '
        + 'Ô “·” = tháng không có phiên giao dịch.',
      'Each cell is that month’s return from the daily equity path (not an average of periods). '
        + 'A “·” cell means no trading session that month.') }),
  ]));

  /* ---------- 6. Thang điểm có dự báo được? ---------- */
  const bucketRows = buckets.filter((b) => b && (b.n || 0) > 0);
  const emptyBuckets = buckets.filter((b) => b && !(b.n || 0));
  const maxAbs = Math.max(1, ...bucketRows.map((b) => Math.abs(b.avg_ret_pct || 0)));
  const bucketBars = el('div', { class: 'bt-bars' }, bucketRows.map((b) => el('div', { class: 'bt-bar-row' }, [
    el('span', { class: 'mono bt-bar-name', text: b.bucket }),
    el('div', { class: 'bt-bar-track' }, [
      el('span', { class: 'bt-bar ' + ((b.avg_ret_pct || 0) >= 0 ? 'pos' : 'neg'), style: `width:${Math.max(2, Math.round(Math.abs(b.avg_ret_pct || 0) / maxAbs * 100))}%` }),
    ]),
    el('span', { class: 'mono bt-bar-val ' + fmt.cls(b.avg_ret_pct), text: fmt.pct(b.avg_ret_pct, 1) }),
    el('span', { class: 'tiny muted bt-bar-n', text: `n=${fmt.n(b.n, 0)}` }),
  ])));

  view.appendChild(el('div', { class: 'section' }, [
    sectionHead(
      T('Thang điểm có dự báo được lợi nhuận?', 'Does the score predict returns?'),
      el('span', { class: 'tiny muted', text: T(
        `Lợi nhuận ${cfg.holding_sessions || 20} phiên của toàn bộ CW đủ điều kiện, trước phí`,
        `${cfg.holding_sessions || 20}-session return of every eligible warrant, before costs`) }),
    ),
    el('div', { class: 'grid cols-2' }, [
      el('div', { class: 'card' }, [
        el('div', { class: 'card-title' }, [el('h3', { text: T('Lợi nhuận TB theo nhóm điểm', 'Average return by score bucket') })]),
        bucketBars,
        emptyBuckets.length ? el('div', { class: 'tiny muted', style: 'margin-top:8px', text: T(
          `${emptyBuckets.map((b) => b.bucket).join(', ')}: không đủ quan sát để kết luận.`,
          `${emptyBuckets.map((b) => b.bucket).join(', ')}: not enough observations to conclude.`) }) : null,
      ]),
      el('div', { class: 'card' }, [
        el('div', { class: 'card-title' }, [el('h3', { text: T('Thống kê chi tiết', 'Detailed statistics') })]),
        table({
          compact: true,
          rows: bucketRows,
          columns: [
            { key: 'bucket', title: T('Nhóm điểm', 'Score bucket'), render: (r) => el('span', { class: 'mono', text: r.bucket }) },
            { key: 'n', title: T('Số quan sát', 'Observations'), align: 'right', render: (r) => fmt.n(r.n, 0) },
            { key: 'avg_ret_pct', title: T('TB 20 phiên', 'Avg 20-session'), align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_ret_pct), text: fmt.pct(r.avg_ret_pct, 1) }) },
            { key: 'median_ret_pct', title: T('Trung vị', 'Median'), align: 'right', render: (r) => el('span', { class: fmt.cls(r.median_ret_pct), text: fmt.pct(r.median_ret_pct, 1) }) },
            { key: 'win_rate_pct', title: T('Tỷ lệ thắng', 'Win rate'), align: 'right', render: (r) => fmt.pct(r.win_rate_pct, 0, false) },
            { key: 'profit_factor', title: 'PF', align: 'right', render: (r) => fmt.n(r.profit_factor, 2) },
          ],
        }),
      ]),
    ]),
    el('div', { class: 'notice tiny', style: 'margin-top:8px', text: T(
      'Đây là kiểm định tính đơn điệu của thang điểm, không phải hiệu quả chiến lược: nếu thang điểm tốt, '
        + 'nhóm điểm cao phải có lợi nhuận kỳ vọng cao hơn nhóm thấp. Chênh lệch hiện tại còn yếu và không đơn điệu.',
      'This tests score monotonicity, not strategy performance: for a good score, the top bucket must carry a '
        + 'higher expected return than the bottom one. The current spread is weak and non-monotonic.') }),
  ]));

  /* ---------- 7. Chế độ thị trường + vì sao lỗ ---------- */
  view.appendChild(el('div', { class: 'grid cols-2 section' }, [
    el('div', { class: 'card' }, [
      el('div', { class: 'card-title' }, [el('h3', { text: 'Kết quả theo chế độ thị trường' })]),
      el('div', { class: 'tiny muted', style: 'margin-bottom:8px', text: T(
        'Chia các kỳ tái cân bằng theo dấu lợi nhuận của rổ cổ phiếu cơ sở trong cùng kỳ — cho thấy '
          + 'chiến lược phụ thuộc vào xu hướng thị trường tới mức nào.',
        'Rebalance periods split by the sign of the underlying basket’s return in the same period — '
          + 'showing how much the strategy depends on the market trend.') }),
      table({
        compact: true,
        rows: [{ key: 'Cơ sở TĂNG', ...(regime.up || {}) }, { key: 'Cơ sở GIẢM', ...(regime.down || {}) }],
        columns: [
          { key: 'key', title: T('Chế độ', 'Regime') },
          { key: 'n_periods', title: T('Số kỳ', 'Periods'), align: 'right', render: (r) => fmt.n(r.n_periods, 0) },
          { key: 'avg_bench_pct', title: T('Cơ sở TB/kỳ', 'Underlying avg'), align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_bench_pct), text: fmt.pct(r.avg_bench_pct, 2) }) },
          { key: 'avg_ret_pct', title: T('Chiến lược TB/kỳ', 'Strategy avg'), align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_ret_pct), text: fmt.pct(r.avg_ret_pct, 2) }) },
          { key: 'win_rate_pct', title: T('% kỳ dương', '% positive'), align: 'right', render: (r) => fmt.pct(r.win_rate_pct, 0, false) },
        ],
      }),
    ]),
    explainerCard(bt, cfg),
  ]));

  /* ---------- 8. Độ nhạy ---------- */
  view.appendChild(el('div', { class: 'section' }, [
    sectionHead('Độ nhạy & kiểm định bộ lọc', el('span', { class: 'tiny muted',
      text: T('Mỗi dòng chạy lại toàn bộ mô phỏng với một giả định khác',
        'Each row re-runs the whole simulation under one different assumption') })),
    el('div', { class: 'grid cols-2' }, [
      sensitivityCard(
        T('Chi phí mỗi chiều', 'Cost per side'),
        T('Dòng đậm là giả định đang dùng.', 'The bold row is the assumption in use.'),
        bt.cost_sensitivity || [],
        [
          { key: 'cost_per_side_pct', title: T('%/chiều', '%/side'), render: (r) => el('span', { class: r.is_default ? 'strong' : 'mono', text: fmt.pct(r.cost_per_side_pct, 2, false) }) },
          { key: 'round_trip_pct', title: T('%/vòng', '%/round trip'), align: 'right', render: (r) => fmt.pct(r.round_trip_pct, 2, false) },
          { key: 'total_return_pct', title: T('Tổng LN', 'Total'), align: 'right', render: (r) => el('span', { class: fmt.cls(r.total_return_pct) + (r.is_default ? ' strong' : ''), text: fmt.pct(r.total_return_pct, 1) }) },
        ],
      ),
      sensitivityCard(
        T('Thời gian nắm giữ', 'Holding period'),
        T('Giữ càng lâu, theta bào mòn càng nhiều.', 'The longer the hold, the more theta erodes value.'),
        bt.holding_sensitivity || [],
        [
          { key: 'holding_sessions', title: T('Phiên', 'Sessions'), align: 'right', render: (r) => el('span', { class: r.holding_sessions === cfg.holding_sessions ? 'strong mono' : 'mono', text: fmt.n(r.holding_sessions, 0) }) },
          { key: 'n_trades', title: T('Số lệnh', 'Trades'), align: 'right', render: (r) => fmt.n(r.n_trades, 0) },
          { key: 'avg_trade_ret_pct', title: T('TB/lệnh', 'Avg/trade'), align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_trade_ret_pct), text: fmt.pct(r.avg_trade_ret_pct, 2) }) },
          { key: 'total_return_pct', title: T('Tổng LN', 'Total'), align: 'right', render: (r) => el('span', { class: fmt.cls(r.total_return_pct), text: fmt.pct(r.total_return_pct, 1) }) },
        ],
      ),
      sensitivityCard(
        T('Ngưỡng điểm tối thiểu', 'Minimum score gate'),
        T('Chỉ mua khi điểm ≥ ngưỡng.', 'Only buy when the score reaches the gate.'),
        bt.gate_sensitivity || [],
        [
          { key: 'score_gate', title: T('Điểm ≥', 'Score ≥'), align: 'right' },
          { key: 'n_trades', title: T('Số lệnh', 'Trades'), align: 'right', render: (r) => fmt.n(r.n_trades, 0) },
          { key: 'avg_trade_ret_pct', title: T('TB/lệnh', 'Avg/trade'), align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_trade_ret_pct), text: fmt.pct(r.avg_trade_ret_pct, 2) }) },
          { key: 'total_return_pct', title: T('Tổng LN', 'Total'), align: 'right', render: (r) => el('span', { class: fmt.cls(r.total_return_pct), text: fmt.pct(r.total_return_pct, 1) }) },
        ],
      ),
      sensitivityCard(
        T('Stop-loss / take-profit', 'Stop-loss / take-profit'),
        T('Stop −2 ATR, TP +2R, khớp thận trọng khi giá mở cửa gap qua ngưỡng.',
          'Stop −2 ATR, TP +2R, filled conservatively when the open gaps through a level.'),
        bt.stop_sensitivity || [],
        [
          { key: 'variant', title: T('Biến thể', 'Variant'), render: (r) => el('span', { class: r.with_stops ? 'strong' : '', text: r.with_stops ? T('Có stop/TP (mặc định)', 'With stop/TP (default)') : T('Không stop/TP', 'No stop/TP') }) },
          { key: 'n_trades', title: T('Số lệnh', 'Trades'), align: 'right', render: (r) => fmt.n(r.n_trades, 0) },
          { key: 'avg_trade_ret_pct', title: T('TB/lệnh', 'Avg/trade'), align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_trade_ret_pct), text: fmt.pct(r.avg_trade_ret_pct, 2) }) },
          { key: 'total_return_pct', title: T('Tổng LN', 'Total'), align: 'right', render: (r) => el('span', { class: fmt.cls(r.total_return_pct), text: fmt.pct(r.total_return_pct, 1) }) },
          { key: 'max_drawdown_pct', title: 'MDD', align: 'right', render: (r) => el('span', { class: 'down', text: fmt.pct(r.max_drawdown_pct, 1) }) },
        ],
      ),
    ]),
  ]));

  /* ---------- 8b. Bộ lọc bổ sung ---------- */
  view.appendChild(el('div', { class: 'card section' }, [
    el('div', { class: 'card-title' }, [
      el('h3', { text: T('Kiểm định bộ lọc bổ sung', 'Additional filter tests') }),
      el('span', { class: 'tiny muted', text: T('Xếp theo tổng lợi nhuận sau phí',
        'Sorted by total return after costs') }),
    ]),
    table({
      compact: true,
      rows: bt.filter_sensitivity || [],
      columns: [
        {
          key: 'filter', title: T('Bộ lọc', 'Filter'),
          render: (r) => el('span', { class: (r.avg_trade_ret_pct || 0) > 0 ? 'strong' : '', text: T(r.filter, r.filter_en || r.filter) }),
        },
        { key: 'n_trades', title: T('Số lệnh', 'Trades'), align: 'right', render: (r) => fmt.n(r.n_trades, 0) },
        { key: 'avg_trade_ret_pct', title: T('TB/lệnh', 'Avg/trade'), align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_trade_ret_pct), text: fmt.pct(r.avg_trade_ret_pct, 2) }) },
        { key: 'win_rate_pct', title: T('Tỷ lệ thắng', 'Win rate'), align: 'right', render: (r) => fmt.pct(r.win_rate_pct, 1, false) },
        { key: 'profit_factor', title: 'PF', align: 'right', render: (r) => fmt.n(r.profit_factor, 2) },
        { key: 'total_return_pct', title: T('Tổng LN', 'Total'), align: 'right', render: (r) => el('span', { class: fmt.cls(r.total_return_pct), text: fmt.pct(r.total_return_pct, 1) }) },
      ],
    }),
    el('div', { class: 'bt-filter-rows' }, positiveFilterNotes(bt)),
    el('div', { class: 'notice tiny', style: 'margin-top:8px', text: T(
      'Bộ lọc dùng chung một tập tín hiệu nên rất dễ overfit; bộ lọc có lợi nhuận dương cũng chỉ dựa trên '
        + 'vài chục lệnh và tập trung ở một giai đoạn. Muốn dùng thật, phải kiểm định ngoài mẫu (walk-forward '
        + 'cuốn tiếp) và kiểm tra độ ổn định theo thời gian.',
      'All filters share one signal set, so they overfit easily; even the profitable one rests on a few dozen '
        + 'trades concentrated in one stretch of history. Real use requires out-of-sample validation and a '
        + 'stability check over time.') }),
  ]));

  /* ---------- 9. Theo TCPH / cơ sở ---------- */
  const groupCols = (first, upper = false) => [
    { key: 'key', title: first, render: (r) => el('span', { class: upper ? 'mono' : '', text: upper ? String(r.key).toUpperCase() : r.key }) },
    { key: 'n', title: T('Số lệnh', 'Trades'), align: 'right', render: (r) => fmt.n(r.n, 0) },
    { key: 'avg_ret_pct', title: T('TB/lệnh', 'Avg/trade'), align: 'right', render: (r) => el('span', { class: fmt.cls(r.avg_ret_pct), text: fmt.pct(r.avg_ret_pct, 2) }) },
    { key: 'median_ret_pct', title: T('Trung vị', 'Median'), align: 'right', render: (r) => el('span', { class: fmt.cls(r.median_ret_pct), text: fmt.pct(r.median_ret_pct, 1) }) },
    { key: 'win_rate_pct', title: T('Tỷ lệ thắng', 'Win rate'), align: 'right', render: (r) => fmt.pct(r.win_rate_pct, 0, false) },
  ];
  view.appendChild(el('div', { class: 'grid cols-2 section' }, [
    el('div', { class: 'card' }, [
      el('div', { class: 'card-title' }, [el('h3', { text: 'Kết quả theo tổ chức phát hành' })]),
      table({ compact: true, rows: bt.by_issuer || [], columns: groupCols(T('TCPH', 'Issuer'), true) }),
    ]),
    el('div', { class: 'card' }, [
      el('div', { class: 'card-title' }, [el('h3', { text: 'Kết quả theo cổ phiếu cơ sở' })]),
      table({ compact: true, rows: bt.by_underlying || [], columns: groupCols(T('Cơ sở', 'Underlying')) }),
    ]),
  ]));

  /* ---------- 10. Nhật ký lệnh ---------- */
  const trades = (bt.trades || []).slice().reverse();
  view.appendChild(el('div', { class: 'section' }, [
    sectionHead('Nhật ký lệnh', el('span', { class: 'tiny muted', text: T(
      `${fmt.n(bt.n_trades_total, 0)} lệnh · hiển thị ${fmt.n(trades.length, 0)} lệnh gần nhất`,
      `${fmt.n(bt.n_trades_total, 0)} trades · showing the latest ${fmt.n(trades.length, 0)}`) })),
    table({
      compact: true,
      stickyFirst: true,
      rows: trades,
      onRowClick: (r) => navigate(`#/cw/${r.ticker}`),
      columns: [
        { key: 'entry_date', title: T('Vào', 'Entry'), render: (r) => fmt.date(r.entry_date) },
        { key: 'exit_date', title: T('Ra', 'Exit'), render: (r) => fmt.date(r.exit_date) },
        { key: 'ticker', title: T('Mã', 'Ticker'), render: (r) => el('span', { class: 'tbl-ticker', text: r.ticker }) },
        { key: 'underlying', title: T('Cơ sở', 'Underlying') },
        { key: 'score', title: T('Điểm', 'Score'), align: 'right', render: (r) => fmt.n(r.score, 1) },
        { key: 'entry', title: T('Giá vào', 'Entry px'), align: 'right', render: (r) => fmt.px(r.entry) },
        { key: 'exit', title: T('Giá ra', 'Exit px'), align: 'right', render: (r) => fmt.px(r.exit) },
        { key: 'gross_ret_pct', title: T('Gộp', 'Gross'), align: 'right', render: (r) => el('span', { class: fmt.cls(r.gross_ret_pct), text: fmt.pct(r.gross_ret_pct, 1) }) },
        { key: 'ret_pct', title: T('Sau phí', 'Net'), align: 'right', render: (r) => el('span', { class: fmt.cls(r.ret_pct), text: fmt.pct(r.ret_pct, 1) }) },
        { key: 'mfe_pct', title: 'MFE', align: 'right', render: (r) => el('span', { class: 'up', text: fmt.pct(r.mfe_pct, 1) }) },
        { key: 'mae_pct', title: 'MAE', align: 'right', render: (r) => el('span', { class: 'down', text: fmt.pct(r.mae_pct, 1) }) },
        { key: 'holding_sessions', title: T('Phiên', 'Sessions'), align: 'right' },
        {
          key: 'exit_reason', title: T('Thoát', 'Exit'),
          render: (r) => {
            const lab = EXIT_LABEL[r.exit_reason] || [r.exit_reason, r.exit_reason];
            return el('span', { class: 'badge ' + (r.exit_reason === 'stop' ? 'HIGH_RISK' : r.exit_reason === 'take_profit' ? 'BUY' : 'tag'), text: T(...lab) });
          },
        },
      ],
    }),
    el('div', { class: 'tiny muted', style: 'margin-top:6px', text: T(
      'Nhấp vào một dòng để mở trang phân tích của mã đó.',
      'Click a row to open that warrant’s analysis page.') }),
  ]));

  /* ---------- 11. Giả định & giới hạn ---------- */
  view.appendChild(el('div', { class: 'card section' }, [
    el('div', { class: 'card-title' }, [
      el('h3', { text: 'Giả định, giới hạn và chống thiên lệch' }),
      el('span', { class: 'tiny muted', text: T('Đọc trước khi dùng bất kỳ con số nào ở trên',
        'Read before using any figure above') }),
    ]),
    el('ul', { class: 'factor-list warn' }, caveats.map((c, i) => el('li', { text: T(c, caveatsEn[i] || c) }))),
    el('div', { class: 'formula', style: 'margin-top:10px', text:
      `start=${cfg.start} · end=${cfg.end} · rebalance=${cfg.rebalance_sessions || '—'} · `
      + `top_n=${cfg.top_n} · holding=${cfg.holding_sessions} · `
      + `cost=${fmt.n(cfg.cost_per_side_pct, 2)}%/side · r=${cfg.risk_free}` }),
    el('div', { class: 'tiny muted', style: 'margin-top:6px', text: costLine(cfg) }),
  ]));
}

/* ---------- widget ---------- */

/** Tóm tắt các bộ lọc có lợi nhuận trung bình mỗi lệnh dương, kèm cảnh báo cỡ mẫu. */
function positiveFilterNotes(bt) {
  const rows = (bt.filter_sensitivity || []).filter((r) => (r.avg_trade_ret_pct || 0) > 0);
  if (!rows.length) return [];
  return rows.slice(0, 4).map((r) => {
    const small = (r.n_trades || 0) < 50;
    return el('div', { class: 'bt-filter-row' }, [
      el('span', { class: 'bt-filter-name', text: T(r.filter, r.filter_en || r.filter) }),
      el('span', { class: 'mono ' + fmt.cls(r.avg_trade_ret_pct), text: `${fmt.pct(r.avg_trade_ret_pct, 2)}${T('/lệnh', '/trade')}` }),
      el('span', { class: 'mono', text: `${fmt.n(r.n_trades, 0)} ${T('lệnh', 'trades')}` }),
      el('span', { class: 'mono ' + fmt.cls(r.total_return_pct), text: fmt.pct(r.total_return_pct, 1) }),
      small ? el('span', { class: 'badge HOLD', text: T('mẫu nhỏ', 'small sample') }) : null,
    ]);
  });
}

function monthlyHeatmap(monthly) {
  const map = new Map(monthly.map((m) => [m.month, m.score_top_pct]));
  const years = [...new Set(monthly.map((m) => Number(String(m.month).slice(0, 4))))].sort();
  const rows = years.map((y) => {
    const row = { year: String(y) };
    let prod = 1;
    let has = false;
    for (let mo = 1; mo <= 12; mo++) {
      const key = `${y}-${String(mo).padStart(2, '0')}`;
      const v = map.get(key);
      row['m' + mo] = v === undefined || v === null ? null : v;
      if (Number.isFinite(v)) { prod *= 1 + v / 100; has = true; }
    }
    row.total = has ? (prod - 1) * 100 : null;
    return row;
  });
  const cell = (v) => {
    if (!Number.isFinite(v)) return el('span', { class: 'mh-na', text: '·' });
    const lvl = Math.min(4, Math.max(1, Math.ceil(Math.abs(v) / 4)));
    return el('span', { class: `mh-cell ${v >= 0 ? 'mh-pos' : 'mh-neg'}-${lvl}`, text: fmt.pct(v, 1) });
  };
  const columns = [
    { key: 'year', title: T('Năm', 'Year'), render: (r) => el('span', { class: 'mono strong', text: r.year }) },
    ...['01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11', '12']
      .map((mm, i) => ({ key: 'm' + (i + 1), title: mm, align: 'right', render: (r) => cell(r['m' + (i + 1)]) })),
    {
      key: 'total', title: T('Cả năm', 'Year'), align: 'right',
      render: (r) => (Number.isFinite(r.total)
        ? el('span', { class: 'mono strong ' + fmt.cls(r.total), text: fmt.pct(r.total, 1) })
        : el('span', { class: 'mh-na', text: '·' })),
    },
  ];
  return table({ compact: true, rows, columns, empty: T('Chưa có dữ liệu tháng', 'No monthly data yet') });
}

function heatSummary(monthly) {
  const vals = monthly.map((m) => m.score_top_pct).filter((v) => Number.isFinite(v));
  if (!vals.length) return null;
  const pos = vals.filter((v) => v > 0).length;
  const best = monthly.reduce((a, b) => (b.score_top_pct > a.score_top_pct ? b : a), monthly[0]);
  const worst = monthly.reduce((a, b) => (b.score_top_pct < a.score_top_pct ? b : a), monthly[0]);
  return el('span', { class: 'tiny muted', text: T(
    `${vals.length} tháng · ${pos} tháng dương · tốt nhất ${best.label} ${fmt.pct(best.score_top_pct, 1)}`
      + ` · xấu nhất ${worst.label} ${fmt.pct(worst.score_top_pct, 1)}`,
    `${vals.length} months · ${pos} up · best ${best.label} ${fmt.pct(best.score_top_pct, 1)}`
      + ` · worst ${worst.label} ${fmt.pct(worst.score_top_pct, 1)}`) });
}

function explainerCard(bt, cfg) {
  const s = bt.summary || {};
  const net = s.score_top || {};
  const gross = s.score_top_gross || {};
  const ew = s.ew_universe || {};
  const bench = s.underlying_ew || {};
  const up = (bt.regime || {}).up || {};
  const down = (bt.regime || {}).down || {};
  const items = [
    {
      vi: ['1. Cấu trúc của chứng quyền',
        'Premium hoà vốn của vũ trụ ở mức cao: cổ phiếu cơ sở phải tăng hàng chục phần trăm mới hoà vốn, '
        + 'trong khi theta bào mòn mỗi phiên. Phần lớn CW giảm giá bất kể tín hiệu — đây là đặc điểm sản phẩm, '
        + 'không phải lỗi mô hình.'],
      en: ['1. Structure of the product',
        'Break-even premiums across the universe are high: the underlying must rally tens of percent just to '
        + 'break even, while theta erodes value every session. Most warrants fall regardless of the signal — '
        + 'that is the product, not a model error.'],
    },
    {
      vi: ['2. Chi phí giao dịch',
        `${fmt.n(cfg.cost_per_side_pct, 2)}%/chiều (${fmt.n(cfg.round_trip_pct, 1)}%/vòng) × `
        + `${fmt.n(cfg.n_signal_dates, 0)} vòng tái cân bằng: riêng chi phí đã lấy đi ${fmt.pct(bt.cost_drag_pct, 1)}. `
        + 'Nếu chỉ phải trả hoa hồng + trượt giá thực tế (khoảng 0,45%/chiều), kết quả vẫn âm nhưng nhẹ hơn nhiều.'],
      en: ['2. Trading costs',
        `${fmt.n(cfg.cost_per_side_pct, 2)}%/side (${fmt.n(cfg.round_trip_pct, 1)}%/round trip) × `
        + `${fmt.n(cfg.n_signal_dates, 0)} rebalances: costs alone took ${fmt.pct(bt.cost_drag_pct, 1)}. `
        + 'At a realistic commission-plus-slippage level (~0.45%/side) the result stays negative but far milder.'],
    },
    {
      vi: ['3. Tín hiệu chưa đủ mạnh',
        `Trước phí, top-5 đạt ${fmt.pct(gross.total_return_pct, 1)} so với toàn vũ trụ ${fmt.pct(ew.total_return_pct, 1)} `
        + '— thang điểm tách được nhóm tốt hơn, nhưng chưa đủ để bù chi phí và độ biến động.'],
      en: ['3. The signal is not strong enough',
        `Before costs the top-5 returned ${fmt.pct(gross.total_return_pct, 1)} versus ${fmt.pct(ew.total_return_pct, 1)} `
        + 'for the whole universe — the score does separate a better group, but not enough to cover costs and volatility.'],
    },
    {
      vi: ['4. Phụ thuộc xu hướng thị trường',
        `Khi cổ phiếu cơ sở tăng, chiến lược lãi trung bình ${fmt.pct(up.avg_ret_pct, 2)}/kỳ; khi cơ sở giảm, `
        + `lỗ ${fmt.pct(down.avg_ret_pct, 2)}/kỳ. Đó là beta nhiều hơn là alpha: cùng kỳ rổ cơ sở đạt `
        + `${fmt.pct(bench.total_return_pct, 1)}, chiến lược ${fmt.pct(net.total_return_pct, 1)}.`],
      en: ['4. Market-trend dependence',
        `When the underlying rises the strategy makes ${fmt.pct(up.avg_ret_pct, 2)}/period on average; when it falls `
        + `it loses ${fmt.pct(down.avg_ret_pct, 2)}/period. That is beta rather than alpha: the underlying basket `
        + `returned ${fmt.pct(bench.total_return_pct, 1)} versus ${fmt.pct(net.total_return_pct, 1)} for the strategy.`],
    },
  ];
  return el('div', { class: 'card' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: T('Vì sao chiến lược thua lỗ', 'Why the strategy loses money') })]),
    el('div', { class: 'bt-explain' }, items.map((it) => el('div', { class: 'bt-explain-item' }, [
      el('div', { class: 'bt-explain-title', text: T(it.vi[0], it.en[0]) }),
      el('div', { class: 'tiny muted', text: T(it.vi[1], it.en[1]) }),
    ]))),
  ]);
}

function sensitivityCard(title, note, rows, columns) {
  return el('div', { class: 'card' }, [
    el('div', { class: 'card-title' }, [el('h3', { text: title })]),
    table({ compact: true, rows, columns, empty: T('Không có dữ liệu', 'No data') }),
    note ? el('div', { class: 'tiny muted', style: 'margin-top:6px', text: note }) : null,
  ]);
}

function costLine(config) {
  const cb = config?.cost_breakdown;
  if (!cb) return bi('Chi phí: n/a', 'Costs: n/a');
  const total = (config.cost_per_side_bps / 100).toFixed(2);
  return bi(
    `Chi phí mỗi chiều: hoa hồng ${fmt.n(cb.commission_pct, 2)}% + trượt giá ${fmt.n(cb.slippage_pct, 2)}% + nửa spread ${fmt.n(cb.half_spread_pct, 2)}% = ${total}%`,
    `Cost per side: commission ${fmt.n(cb.commission_pct, 2)}% + slippage ${fmt.n(cb.slippage_pct, 2)}% + half-spread ${fmt.n(cb.half_spread_pct, 2)}% = ${total}%`,
  );
}

function exportTrades(bt) {
  downloadCsv(`cw-backtest-trades-${bt.config?.end || ''}.csv`, bt.trades || []);
  toast('Đã xuất CSV trades');
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
