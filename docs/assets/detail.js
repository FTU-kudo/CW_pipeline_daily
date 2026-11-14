/* ============================================================
   Chi tiết một chứng quyền
   ------------------------------------------------------------
   Bấm mã ở bảng giá (hoặc ?t=ACB2515) để mở một ngăn kéo hiển thị MỌI thông tin có
   trong dữ liệu đã publish, chia thành các nhóm đọc được:

     giá & thanh khoản · bid/ask · khối ngoại · định giá BS/Greeks · điểm số
     · dải trần–sàn · trong phiên · lịch sử theo phiên · cổ phiếu cơ sở

   Nguyên tắc hiển thị
   -------------------
   * Trường nào nguồn không có thì hiện "—" kèm lý do, KHÔNG hiện 0.
   * Mã không khớp lệnh: giá để trống và nói rõ "không giao dịch trong phiên", không
     dùng RefP thay giá.
   * Khối định giá vắng thì nói lý do engine trả về, không tự suy IV.
   ============================================================ */
import {
  bi, esc, num, money, pct, dash, getLang,
} from './ui.js';

let DETAILS = null;
let INDEX = new Map();
let current = null;

export function initDetail(detailsPayload) {
  DETAILS = detailsPayload && Array.isArray(detailsPayload.rows) ? detailsPayload : null;
  INDEX = new Map((DETAILS?.rows || []).map((row) => [row.ticker, row]));
  buildShell();
  // Lưới an toàn: nếu vì bất kỳ lý do gì backdrop còn hiện sau khi khởi tạo, ẩn nó đi.
  // Backdrop phủ kín trang nên đây là lỗi nhìn thấy được ngay, phải chặn từ gốc.
  const backdrop = document.getElementById('detail-backdrop');
  if (backdrop) backdrop.hidden = true;
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeDetail();
  });
  window.addEventListener('cwintel:lang', () => { if (current) openDetail(current.ticker, { scroll: false }); });
  // Đường dẫn ?t=MÃ cho phép chia sẻ liên kết tới một mã.
  const param = new URLSearchParams(window.location.search).get('t');
  if (param) openDetail(param.toUpperCase());
}

export function getDetailRow(ticker) {
  return INDEX.get(String(ticker || '').toUpperCase()) || null;
}

export function hasDetail(ticker) {
  return INDEX.has(String(ticker || '').toUpperCase());
}

export function openDetail(ticker, opts = {}) {
  const row = getDetailRow(ticker);
  const body = document.getElementById('detail-body');
  if (!body) return;
  const panel = document.getElementById('detail-panel');
  if (!panel) return;
  panel.hidden = false;
  const backdrop = document.getElementById('detail-backdrop');
  if (backdrop) backdrop.hidden = false;
  document.body.classList.add('drawer-open');
  if (!row) {
    body.innerHTML = `<div class="empty">${esc(bi('Không tìm thấy mã', 'Ticker not found'))}
      <strong>${esc(ticker)}</strong>. ${esc(bi('Dữ liệu chi tiết chỉ có cho các mã trong snapshot.',
        'Detail data only covers tickers in the snapshot.'))}</div>`;
    return;
  }
  current = row;
  document.getElementById('detail-title').textContent = row.ticker;
  const underline = row.underlying || '—';
  document.getElementById('detail-sub').innerHTML =
    `${esc(bi('Cổ phiếu cơ sở', 'Underlying'))}: <strong>${esc(underline)}</strong>`
    + ` · ${esc(bi('Phiên', 'Session'))} ${esc(DETAILS?.session || '—')}`;
  body.innerHTML = renderBody(row);
  if (opts.scroll !== false) body.scrollTop = 0;
  const url = new URL(window.location.href);
  url.searchParams.set('t', row.ticker);
  window.history.replaceState({}, '', url);
  document.getElementById('detail-close')?.focus();
}

export function closeDetail() {
  const panel = document.getElementById('detail-panel');
  if (!panel) return;
  panel.hidden = true;
  const backdrop = document.getElementById('detail-backdrop');
  if (backdrop) backdrop.hidden = true;
  document.body.classList.remove('drawer-open');
  current = null;
  const url = new URL(window.location.href);
  url.searchParams.delete('t');
  window.history.replaceState({}, '', url);
}

/* ---------------------------------------------------------------
   Dựng khung ngăn kéo một lần
   --------------------------------------------------------------- */
function buildShell() {
  if (document.getElementById('detail-panel')) return;
  const panel = document.createElement('aside');
  panel.id = 'detail-panel';
  panel.className = 'drawer';
  panel.hidden = true;
  panel.setAttribute('role', 'dialog');
  panel.setAttribute('aria-modal', 'true');
  panel.setAttribute('aria-labelledby', 'detail-title');
  panel.innerHTML = `
    <header class="drawer-head">
      <div>
        <h2 id="detail-title">—</h2>
        <div class="drawer-sub" id="detail-sub"></div>
      </div>
      <button type="button" id="detail-close" class="close" aria-label="${esc(bi('Đóng', 'Close'))}">✕</button>
    </header>
    <div class="drawer-body" id="detail-body"></div>`;
  document.body.appendChild(panel);
  const backdrop = document.createElement('div');
  backdrop.className = 'drawer-backdrop';
  backdrop.id = 'detail-backdrop';
  // BẮT BUỘC: backdrop có position:fixed + inset:0, nên nếu không ẩn ngay thì nó phủ tối
  // toàn trang từ lúc tải. Đây là lỗi "một lớp mờ khi truy cập web".
  backdrop.hidden = true;
  document.body.appendChild(backdrop);
  panel.querySelector('#detail-close').addEventListener('click', closeDetail);
  backdrop.addEventListener('click', closeDetail);
}

/* ---------------------------------------------------------------
   Các khối nội dung
   --------------------------------------------------------------- */
function section(title, inner, hint) {
  if (!inner) return '';
  return `<section class="dsec"><h3>${esc(title)}</h3>`
    + (hint ? `<p class="dhint">${hint}</p>` : '')
    + inner + '</section>';
}

/** Lưới nhãn–giá trị. `items` là [nhãn, giá trị đã format, lý do khi thiếu]. */
function grid(items) {
  const rows = items.map(([label, value, reason]) => {
    const shown = value === null || value === undefined || value === '' ? dash(reason) : value;
    return `<div class="dkv"><span class="dk">${esc(label)}</span>`
      + `<span class="dv">${shown}</span></div>`;
  }).join('');
  return `<div class="dgrid">${rows}</div>`;
}

function priceGrid(row) {
  const market = row.market || {};
  const raw = row.raw || {};
  const traded = market.traded === true;
  const idle = bi('Không giao dịch trong phiên', 'Not traded this session');
  return grid([
    [bi('Giá khớp cuối', 'Last price'), traded ? num(market.lastPrice) : null,
      traded ? null : idle],
    [bi('Giá tham chiếu (đóng cửa phiên trước)', 'Reference (previous close)'), num(raw.RefP)],
    [bi('Thay đổi trong ngày', 'Change'),
      market.priceChangePct === null || market.priceChangePct === undefined
        ? null : `<span class="${market.priceChangePct > 0 ? 'positive' : market.priceChangePct < 0 ? 'negative' : ''}">${pct(market.priceChangePct)}</span>`,
      idle],
    [bi('Giá mở cửa', 'Open'), traded ? num(raw.OpenP) : null, idle],
    [bi('Cao nhất', 'Highest'), traded ? num(raw.HighestP) : null, idle],
    [bi('Thấp nhất', 'Lowest'), traded ? num(raw.LowestP) : null, idle],
    [bi('Giá bình quân', 'Average price'), traded ? num(raw.AvgP, 2) : null, idle],
    [bi('Trần', 'Ceiling'), num(raw.CeilingP)],
    [bi('Sàn', 'Floor'), num(raw.FloorP)],
    [bi('Khối lượng khớp', 'Matched volume'), num(raw.TotalVol)],
    [bi('Giá trị khớp', 'Matched value'), money(raw.TotalVal)],
    [bi('Spread (bước giá)', 'Spread (ticks)'), num(market.spreadTicks, 1)],
  ]);
}

function bookGrid(row) {
  const raw = row.raw || {};
  const sides = [
    ['B1', raw.B1P, raw.B1V], ['B2', raw.B2P, raw.B2V], ['B3', raw.B3P, raw.B3V],
    ['S1', raw.S1P, raw.S1V], ['S2', raw.S2P, raw.S2V], ['S3', raw.S3P, raw.S3V],
  ];
  const cells = sides.map(([label, price, volume]) => (
    `<div class="book-row ${label.startsWith('S') ? 'ask' : 'bid'}">`
    + `<span class="bl">${label}</span>`
    + `<span class="bp">${price === null || price === undefined ? '—' : num(price)}</span>`
    + `<span class="bv">${volume === null || volume === undefined ? '—' : num(volume)}</span>`
    + '</div>'
  )).join('');
  return `<div class="book"><div class="book-head"><span></span>`
    + `<span>${esc(bi('Giá', 'Price'))}</span><span>${esc(bi('Khối lượng', 'Volume'))}</span></div>`
    + cells + '</div>';
}

function foreignGrid(row) {
  const raw = row.raw || {};
  const none = bi('Nguồn không trả trường này', 'Source does not provide this field');
  return grid([
    [bi('Khối ngoại mua', 'Foreign buy volume'), num(raw.FTBuyVol), none],
    [bi('Khối ngoại bán', 'Foreign sell volume'), num(raw.FTSellVol), none],
    [bi('Room ngoại còn lại', 'Remaining foreign room'), num(raw.FRoom), none],
  ]);
}

function valuationSection(row) {
  const val = row.valuation;
  if (!val) {
    const reason = row.valuationBlockedBy
      || bi('Mã này không nằm trong danh sách được định giá của phiên.',
        'This ticker is not in the valued list for the session.');
    return section(bi('Định giá Black–Scholes', 'Black–Scholes valuation'),
      `<div class="dnote">${esc(bi('Không có khối định giá cho mã này', 'No valuation block for this ticker'))}.</div>`
      + `<p class="dhint">${esc(reason)}</p>`);
  }
  const iv = val.iv;
  const deltaCls = '';
  return section(bi('Định giá Black–Scholes', 'Black–Scholes valuation'), grid([
    [bi('Strike', 'Strike'), num(val.strike)],
    [bi('Tỷ lệ chuyển đổi', 'Conversion ratio'), num(val.ratio, 3)],
    [bi('Ngày đáo hạn', 'Maturity date'), esc(val.maturity)],
    [bi('Số ngày còn lại', 'Days to maturity'), num(val.daysToMaturity)],
    [bi('Giá cổ phiếu cơ sở', 'Underlying price'), num(val.underlyingPrice)],
    [bi('Nguồn giá cơ sở', 'Underlying price source'), esc(val.underlyingSource)],
    [bi('IV (biến động ẩn)', 'IV (implied volatility)'),
      iv === null || iv === undefined ? null : `${num(iv, 2)}%`],
    [bi('HV 21 phiên', 'HV 21 sessions'),
      val.hvShort === null || val.hvShort === undefined ? null : `${num(val.hvShort, 2)}%`,
      bi('Cần lịch sử cổ phiếu cơ sở', 'Needs underlying price history')],
    [bi('HV 63 phiên', 'HV 63 sessions'),
      val.hvLong === null || val.hvLong === undefined ? null : `${num(val.hvLong, 2)}%`],
    [bi('IV − HV', 'IV − HV'),
      val.ivMinusHv === null || val.ivMinusHv === undefined ? null
        : `${val.ivMinusHv > 0 ? '+' : ''}${num(val.ivMinusHv, 2)}`,
      bi('Cần lịch sử cổ phiếu cơ sở', 'Needs underlying price history')],
    [bi('Premium hoà vốn', 'Break-even premium'),
      val.premiumPct === null || val.premiumPct === undefined ? null : `${num(val.premiumPct, 2)}%`],
    [bi('Đòn bẩy', 'Leverage'), num(val.leverage, 2)],
    [bi('Giá trị nội tại', 'Intrinsic value'), num(val.intrinsic, 2)],
    [bi('Giá trị thời gian', 'Time value'), num(val.timeValue, 2)],
    [bi('ITM/ATM/OTM', 'ITM/ATM/OTM'), esc(val.moneyness)],
    [`${bi('Delta', 'Delta')} <span class="dgreek">∂C/∂S</span>`, num(val.delta, 4)],
    ['Gamma', num(val.gamma, 6)],
    ['Theta', num(val.theta, 4)],
    ['Vega', num(val.vega, 4)],
    ['Rho', num(val.rho, 4)],
    [bi('Delta quy đổi', 'Delta (converted)'), num(val.deltaOption, 4)],
    [bi('IV nhóm cùng cơ sở', 'IV of the same-underlying group'),
      val.ivGroupMedian === null || val.ivGroupMedian === undefined ? null
        : `${num(val.ivGroupMedian, 2)}% (${num(val.ivGroupSize)} ${bi('mã', 'tickers')})`,
      bi('Nhóm dưới 5 mã thì không so', 'Groups under 5 tickers are not compared')],
    [bi('Chênh lệch IV', 'IV vs group'),
      val.ivResidualPct === null || val.ivResidualPct === undefined ? null
        : `<span class="${val.ivResidualPct < 0 ? 'positive' : 'negative'}">${val.ivResidualPct > 0 ? '+' : ''}${num(val.ivResidualPct, 2)}%</span>`],
  ]), esc(bi(
    'IV suy ngược từ giá thị trường, không phải dự báo. Mô hình quyền chọn châu Âu, không cổ tức (q=0) — dùng để so sánh tương đối, không phải giá mục tiêu.',
    'IV is inverted from the market price, not a forecast. European, no-dividend (q=0) model — for relative comparison, not a target price.')));
}

function scoringSection(row) {
  const score = row.scoring;
  if (!score) {
    return section(bi('Điểm số', 'Score'),
      `<div class="dnote">${esc(bi('Mã không được chấm điểm', 'Ticker not scored'))}.</div>`
      + `<p class="dhint">${esc(bi('Chỉ mã có khớp lệnh mới được chấm — không có giá thì không có gì để chấm.',
        'Only traded tickers are scored — without a price there is nothing to score.'))}</p>`);
  }
  const parts = score.parts || {};
  const bars = [
    [bi('Thanh khoản', 'Liquidity'), parts.liquidity],
    [bi('Chi phí', 'Cost'), parts.cost],
    [bi('Định giá', 'Valuation'), parts.valuation],
    [bi('Chất lượng giá', 'Price quality'), parts.priceQuality],
    [bi('Độ ổn định', 'Consistency'), parts.consistency],
  ].map(([label, value]) => `<div class="dbar"><span class="dl">${esc(label)}</span>`
    + `<span class="dtrack"><span class="dfill" style="width:${Math.max(0, Math.min(100, value || 0))}%"></span></span>`
    + `<span class="dv">${value === null || value === undefined ? '—' : num(value, 0)}</span></div>`).join('');
  return section(bi('Điểm số', 'Score'),
    `<div class="dscore"><span class="big">${num(score.score, 1)}</span>`
    + `<span class="of">/100 · ${esc(bi('hạng', 'rank'))} ${num(score.rank)}</span>`
    + `<span class="tier">${esc(score.tier || '')}</span></div>`
    + `<div class="dbars">${bars}</div>`,
    esc(bi('Điểm tương đối trong rổ CW hiện tại, không phải xác suất sinh lời hay khuyến nghị.',
      'Relative score within the current warrant universe, not a probability of profit or a recommendation.')));
}

function bandSection(row) {
  const band = row.priceBand;
  if (!band) return '';
  return section(bi('Dải trần–sàn', 'Price band'), grid([
    [bi('Trần', 'Ceiling'), num(band.ceiling)],
    [bi('Sàn', 'Floor'), num(band.floor)],
    [bi('Giá đóng cửa', 'Close'), num(band.close)],
    [bi('Tỷ lệ giá trên trần', 'Distance to ceiling'),
      band.toCeilingPct === null ? null : `${num(band.toCeilingPct, 2)}%`],
    [bi('Tỷ lệ giá trên sàn', 'Distance to floor'),
      band.toFloorPct === null ? null : `${num(band.toFloorPct, 2)}%`],
    [bi('Trạng thái', 'Status'),
      band.atCeiling ? esc(bi('Đang ở trần', 'At ceiling'))
        : band.atFloor ? esc(bi('Đang ở sàn', 'At floor')) : esc(bi('Trong dải', 'Inside band'))],
  ]));
}

function intradaySection(row) {
  const day = row.intraday;
  if (!day) return '';
  return section(bi('Trong phiên hôm nay', 'Today intraday'), grid([
    [bi('Mở', 'Open'), num(day.open)],
    [bi('Cao', 'High'), num(day.high)],
    [bi('Thấp', 'Low'), num(day.low)],
    [bi('Đóng', 'Close'), num(day.close)],
    [`${bi('Biên độ', 'Range')}`, `${num(day.rangeVND)} (${num(day.rangePct, 1)}%)`],
    [bi('Vị trí giá trong biên', 'Close location'),
      day.closeLocation === null ? null : num(day.closeLocation, 2)],
  ]), esc(bi('Mô tả phiên đã xảy ra, không phải tín hiệu.',
    'Describes a session that already happened; not a signal.')));
}

function historySection(row) {
  const bars = row.history || [];
  if (!bars.length) {
    return section(bi('Lịch sử theo phiên', 'Session history'),
      `<div class="dnote">${esc(bi('Chưa tích luỹ đủ lịch sử', 'Not enough history accumulated'))}.</div>`
      + `<p class="dhint">${esc(bi('Kho OHLCV dày lên sau mỗi lần workflow chạy sau giờ đóng cửa. Endpoint không có dữ liệu quá khứ nên không thể backfill.',
        'The OHLCV store grows after each post-close workflow run. The endpoint has no history, so it cannot be backfilled.'))}</p>`);
  }
  const head = `<div class="table-wrap"><table class="dtable"><thead><tr>`
    + `<th>${esc(bi('Phiên', 'Session'))}</th><th>${esc(bi('Mở', 'Open'))}</th>`
    + `<th>${esc(bi('Cao', 'High'))}</th><th>${esc(bi('Thấp', 'Low'))}</th>`
    + `<th>${esc(bi('Đóng', 'Close'))}</th><th>${esc(bi('Khối lượng', 'Volume'))}</th>`
    + `<th>${esc(bi('Giá trị', 'Value'))}</th></tr></thead><tbody>`;
  const body = bars.slice().reverse().map((bar) => `<tr><td>${esc(bar.session)}</td>`
    + `<td class="num">${bar.open === null ? dash() : num(bar.open)}</td>`
    + `<td class="num">${bar.high === null ? dash() : num(bar.high)}</td>`
    + `<td class="num">${bar.low === null ? dash() : num(bar.low)}</td>`
    + `<td class="num">${bar.close === null ? dash(bi('Không khớp lệnh', 'No trade')) : num(bar.close)}</td>`
    + `<td class="num">${bar.volume === null ? dash() : num(bar.volume)}</td>`
    + `<td class="num">${bar.value === null ? dash() : money(bar.value)}</td></tr>`).join('');
  return section(bi('Lịch sử theo phiên', 'Session history'), head + body + '</tbody></table></div>',
    esc(bi('Ô "—" là phiên không khớp lệnh: để trống thay vì điền giá tham chiếu.',
      '"—" marks a session with no trade: left empty rather than filled with the reference price.')));
}

function underlyingSection(row) {
  const stats = row.underlyingStats;
  if (!stats) return '';
  return section(bi('Cổ phiếu cơ sở (tham chiếu)', 'Underlying (reference)'), grid([
    [bi('Cổ phiếu cơ sở', 'Underlying'), esc(stats.underlying)],
    [bi('Số CW cùng cơ sở', 'Warrants on this underlying'), num(stats.warrants)],
    [bi('Số mã có giao dịch', 'Traded tickers'), num(stats.traded)],
    [bi('Giá trị giao dịch nhóm', 'Group traded value'), money(stats.valueVND)],
    [bi('Tỷ trọng giá trị', 'Value share'), `${num(stats.valueSharePct, 2)}%`],
    [bi('Spread trung vị nhóm', 'Group median spread'), `${num(stats.medianSpreadPct, 2)}%`],
    [bi('Giá trung vị nhóm', 'Group median price'), num(stats.medianPriceVND)],
    [`${bi('Biến động tốt nhất', 'Best change')}`,
      stats.bestChangePct === null ? null : `${num(stats.bestChangePct, 2)}%`],
    [`${bi('Biến động xấu nhất', 'Worst change')}`,
      stats.worstChangePct === null ? null : `${num(stats.worstChangePct, 2)}%`],
  ]));
}

function rawSection(row) {
  const raw = row.raw || {};
  const entries = Object.entries(raw).filter(([, v]) => v !== null && v !== undefined);
  const rows = entries.map(([k, v]) => `<div class="dkv"><span class="dk">${esc(k)}</span>`
    + `<span class="dv">${esc(v)}</span></div>`).join('');
  const missing = Object.entries(raw).filter(([, v]) => v === null || v === undefined)
    .map(([k]) => k);
  return section(bi('Trường gốc từ API', 'Raw API fields'),
    `<div class="dgrid">${rows}</div>`,
    missing.length
      ? esc(bi('Trường nguồn không trả (để trống, không điền 0): ', 'Fields the source did not return (left empty, not zero): '))
        + esc(missing.join(', '))
      : null);
}

function renderBody(row) {
  const parts = [
    section(bi('Giá & thanh khoản', 'Price & liquidity'), priceGrid(row)),
    section(bi('Bid / Ask', 'Bid / Ask'), bookGrid(row)),
    section(bi('Khối ngoại & room', 'Foreign flow & room'), foreignGrid(row)),
    valuationSection(row),
    scoringSection(row),
    bandSection(row),
    intradaySection(row),
    historySection(row),
    underlyingSection(row),
    rawSection(row),
  ];
  return parts.filter(Boolean).join('');
}
