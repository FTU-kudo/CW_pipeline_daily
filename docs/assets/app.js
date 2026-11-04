/* CW Intelligence — khởi động ứng dụng, định tuyến, trạng thái toàn cục */
import {
  $, el, fmt, data, initTheme, initSearch, registerRoute, startRouter, render, store, toast,
} from './core.js';
import overview from './pages/overview.js';
import heatmap from './pages/heatmap.js';
import screener from './pages/screener.js';
import detail from './pages/detail.js';
import { recommendationsPage, backtestPage } from './pages/advice.js';
import { watchlistPage, portfolioPage, alertsPage } from './pages/tools.js';
import { dataPage, methodPage } from './pages/system.js';
import liquidityPage from './pages/liquidity.js';
import { initI18n, getLang, bi } from './i18n.js';
import { clockParts, hasClosedToday, startClock } from './clock.js';

function setBoot(pct, msg) {
  const bar = $('#boot-bar');
  const label = $('#boot-msg');
  if (bar) bar.style.width = Math.round(pct * 100) + '%';
  if (label && msg) label.textContent = msg;
}

const BOOT_MSG = {
  meta: 'Đang đọc metadata phiên bản…',
  market: 'Đang tải tổng quan thị trường…',
  screener: 'Đang tải dữ liệu screener…',
  recommendations: 'Đang tải khuyến nghị…',
  underlyings: 'Đang tải dữ liệu cổ phiếu cơ sở…',
  quality: 'Đang chạy kiểm tra chất lượng dữ liệu…',
  methodology: 'Đang tải phương pháp luận…',
  liquidity: 'Đang tải dữ liệu thanh khoản…',
  lifecycle: 'Đang đối chiếu vòng đời CW (niêm yết / đáo hạn)…',
  done: 'Sẵn sàng.',
};

// Chuỗi sinh bằng JS: 'both' ghép VI · EN, các chế độ khác lấy một ngôn ngữ.
// Gắn data-no-i18n để bộ dịch DOM không dịch chồng lên chuỗi đã ghép sẵn.
function tx(vi, en) {
  return getLang() === 'both' ? `${vi} · ${en}` : bi(vi, en);
}

function setNodeText(node, text) {
  if (!node) return;
  node.setAttribute('data-no-i18n', '');
  node.textContent = text;
}

function applyMeta() {
  const meta = data.meta || {};
  const sbAsof = $('#sb-asof');
  const sbUpd = $('#sb-updated');
  if (sbAsof) sbAsof.textContent = meta.asofLabel || '—';
  if (sbUpd) sbUpd.textContent = (meta.generatedAt || '—').split(' ').slice(0, 2).join(' ');
  // Độ mới của dữ liệu tính bằng PHIÊN (không phải ngày lịch): meta.session do
  // cwintel/sessions.py sinh ra, so asof với phiên đã đóng gần nhất theo giờ ICT.
  const ses = meta.session || null;
  const lag = ses ? (ses.lagSessions ?? 0) : (meta.dataAgeDays ?? 0);
  const expectedLabel = meta.expectedAsOfLabel || ses?.expectedLabel || '';
  const gapRow = $('#sb-gap-row');
  const gapVal = $('#sb-gap');
  if (gapRow && gapVal) {
    if (lag > 0) {
      gapRow.classList.remove('hidden');
      setNodeText(gapVal, tx(`${lag} phiên`, `${lag} session${lag > 1 ? 's' : ''}`));
      gapVal.className = lag >= 2 ? 'down' : 'warn-text';
    } else {
      gapRow.classList.add('hidden');
    }
  }

  const age = $('#data-age-pill');
  if (age) {
    // Tính theo giờ xem, không dùng session.todayClosed (đó là trạng thái lúc build).
    // Cuối tuần/ngày lễ không có phiên hôm nay → nêu rõ phiên dữ liệu gần nhất.
    const todayClosed = hasClosedToday(clockParts(Date.now(), data.meta?.marketHolidays || []));
    age.textContent = lag > 0
      ? tx(`Thiếu ${lag} phiên`, `${lag} session${lag > 1 ? 's' : ''} behind`)
      : todayClosed
        ? tx('Dữ liệu phiên hôm nay', 'Updated this session')
        : tx(`Dữ liệu phiên ${meta.asofLabel}`, `Session ${meta.asofLabel}`);
    age.className = 'pill ' + (lag > 0 ? 'warn' : 'ok');
    age.title = lag > 0 && expectedLabel
      ? tx(`Dữ liệu dừng ở phiên ${meta.asofLabel}. Phiên đã đóng gần nhất: ${expectedLabel}.`,
        `Data stops at session ${meta.asofLabel}. Latest closed session: ${expectedLabel}.`)
      : tx(`Snapshot cuối phiên ${meta.asofLabel}. Không phải dữ liệu realtime.`,
        `End-of-session snapshot for ${meta.asofLabel}. Not realtime data.`);
  }
  const uni = $('#universe-pill');
  if (uni) uni.textContent = `${fmt.n(meta.universe?.active, 0)} CW · ${fmt.n(meta.universe?.underlyings, 0)} cơ sở`;
  const ver = $('#footer-version');
  if (ver) ver.textContent = `v${meta.version || ''} · methodology ${meta.methodologyVersion || ''}`;

  const stale = $('#stale-banner');
  if (stale) {
    stale.setAttribute('data-no-i18n', '');
    if (lag > 0) {
      // Lệch 1 phiên: pipeline nguồn có thể chưa xong (hoặc hôm đó nghỉ lễ).
      // Lệch từ 2 phiên: coi như sự cố, đổi sang banner đỏ.
      const days = meta.dataAgeDays ?? 0;
      stale.classList.remove('hidden');
      stale.classList.toggle('banner-danger', lag >= 2);
      stale.classList.toggle('banner-warn', lag === 1);
      // Một câu duy nhất cho mỗi ngôn ngữ để bản VI · EN không bị xen kẽ giữa câu.
      const msg = lag >= 2
        ? tx(`<b>Dữ liệu đang trễ nhiều phiên:</b> phiên dữ liệu cuối là ${meta.asofLabel}, `
          + `thiếu ${lag} phiên so với ${expectedLabel} (${days} ngày). Các khuyến nghị, mức giá và `
          + 'điểm số bên dưới được tính trên dữ liệu cũ — không dùng như giá realtime. '
          + 'Kiểm tra workflow "CW Pipeline Daily" trước khi ra quyết định.',
        `<b>Data is several sessions behind:</b> last data session is ${meta.asofLabel}, `
          + `${lag} sessions behind ${expectedLabel} (${days} days). Scores and prices below are `
          + 'computed on older data — do not use as realtime. Check the "CW Pipeline Daily" '
          + 'workflow before making decisions.')
        : tx(`<b>Dữ liệu chưa có phiên mới nhất:</b> dữ liệu dừng ở phiên ${meta.asofLabel}, `
          + `còn thiếu phiên ${expectedLabel}. Bảng giá, điểm và khuyến nghị bên dưới tính trên `
          + 'phiên gần nhất đã có; số liệu sẽ tự cập nhật sau khi pipeline nguồn chạy xong '
          + '(khoảng 16:00–17:30 giờ Việt Nam).',
        `<b>Latest session not in yet:</b> data stops at session ${meta.asofLabel}; session `
          + `${expectedLabel} is missing. Prices, scores and recommendations below use the latest `
          + 'available session and will update once the source pipeline finishes '
          + '(around 16:00–17:30 ICT).');
      stale.innerHTML = msg;
    } else if ((meta.dataAgeDays ?? 0) > 3) {
      stale.classList.remove('hidden');
      stale.classList.remove('banner-danger', 'banner-warn');
      stale.innerHTML = `<b>${tx('Cảnh báo dữ liệu cũ:', 'Stale data warning:')}</b> `
        + tx(`phiên gần nhất là ${meta.asofLabel} (${meta.dataAgeDays} ngày trước). `
          + 'Các khuyến nghị và mức giá bên dưới có thể không còn hiệu lực — không sử dụng như giá realtime.',
        `latest session is ${meta.asofLabel} (${meta.dataAgeDays} days ago). `
          + 'Recommendations and prices below may no longer be valid — do not use as realtime prices.');
    } else {
      stale.classList.add('hidden');
      stale.classList.remove('banner-danger', 'banner-warn');
    }
  }
}

async function boot() {
  initI18n();
  initTheme();
  try {
    await data.init((pct, key) => setBoot(pct * 0.95, BOOT_MSG[key] || 'Đang tải…'));
  } catch (err) {
    console.error(err);
    setBoot(1, '');
    $('#boot-msg').innerHTML = `<div style="color:var(--down);font-weight:600">Không tải được dữ liệu</div>`
      + `<div style="margin-top:6px">${escapeHtml(err.message)}</div>`
      + '<div style="margin-top:10px;color:var(--text-3)">Kiểm tra rằng thư mục <code>docs/data/</code> tồn tại và đã chạy pipeline '
      + '(<code>python -m cwintel.build</code>). Nếu mở tệp trực tiếp bằng file://, hãy chạy một web server tĩnh.</div>';
    return;
  }

  applyMeta();
  $('#boot').classList.add('hidden');
  $('#app').classList.remove('hidden');
  initSearch();
  // Đồng hồ thời gian thực (giờ VN): chạy suốt phiên làm việc của tab
  // Nghỉ lễ lấy từ meta.marketHolidays (sinh từ cwintel/config.py) để đồng hồ
  // không báo "đang khớp lệnh" vào ngày thị trường đóng cửa.
  startClock(document, { lang: getLang, holidays: () => data.meta?.marketHolidays || [] });

  registerRoute('overview', overview);
  registerRoute('heatmap', heatmap);
  registerRoute('screener', screener);
  registerRoute('cw', detail);
  registerRoute('recommendations', (view) => recommendationsPage(view));
  registerRoute('backtest', (view) => backtestPage(view));
  registerRoute('liquidity', liquidityPage);
  registerRoute('watchlist', watchlistPage);
  registerRoute('portfolio', portfolioPage);
  registerRoute('alerts', alertsPage);
  registerRoute('data', dataPage);
  registerRoute('method', methodPage);

  // mobile menu
  $('#btn-menu')?.addEventListener('click', () => $('#sidebar')?.classList.toggle('open'));
  document.addEventListener('click', (e) => {
    if (window.innerWidth <= 900 && !e.target.closest('#sidebar') && !e.target.closest('#btn-menu')) {
      $('#sidebar')?.classList.remove('open');
    }
  });

  // watchlist badge trong nav
  const navCount = $('#nav-screener-count');
  if (navCount) navCount.textContent = fmt.n((data.screener?.active || []).length, 0);

  // deep link vào detail từ URL query (?t=) — hữu dụng khi chia sẻ
  if (!location.hash) {
    const p = new URLSearchParams(location.search);
    if (p.get('t')) location.hash = `#/cw/${p.get('t')}`;
  }

  startRouter();

  // Đổi ngôn ngữ: dựng lại trang để số liệu, ngày tháng và chart dùng đúng locale
  window.addEventListener('cwintel:lang', () => {
    applyMeta();
    render();
    const navCountEl = $('#nav-screener-count');
    if (navCountEl) navCountEl.textContent = fmt.n((data.screener?.active || []).length, 0);
  });

  // cảnh báo định kỳ nhẹ: nếu watchlist có mã đáo hạn < 7 ngày, nhắc một lần / phiên
  const wl = store.get('watchlist', []);
  const soon = wl.map((t) => data.row(t)).filter((r) => r && (r.dte ?? 999) < 7);
  if (soon.length) {
    const key = `notified:${data.meta?.asof}`;
    if (!store.get(key, false)) {
      setTimeout(() => {
        const label = getLang() === 'en'
        ? `${soon.length} watchlist warrants expire soon (<7 days): ${soon.map((r) => r.t).join(', ')}`
        : `${soon.length} CW trong watchlist sắp đáo hạn (<7 ngày): ${soon.map((r) => r.t).join(', ')}`;
      toast(label, 6000);
        store.set(key, true);
      }, 1200);
    }
  }
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

boot();
