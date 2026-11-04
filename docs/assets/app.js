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
  done: 'Sẵn sàng.',
};

function applyMeta() {
  const meta = data.meta || {};
  const sbAsof = $('#sb-asof');
  const sbUpd = $('#sb-updated');
  if (sbAsof) sbAsof.textContent = meta.asofLabel || '—';
  if (sbUpd) sbUpd.textContent = (meta.generatedAt || '—').split(' ').slice(0, 2).join(' ');
  const age = $('#data-age-pill');
  if (age) {
    const days = meta.dataAgeDays ?? 0;
    age.textContent = days <= 0 ? 'Dữ liệu phiên hôm nay' : `Dữ liệu cách ${days} phiên`;
    age.className = 'pill ' + (days > 3 ? 'warn' : 'ok');
    age.title = `Snapshot cuối phiên ${meta.asofLabel}. Không phải dữ liệu realtime.`;
  }
  const uni = $('#universe-pill');
  if (uni) uni.textContent = `${fmt.n(meta.universe?.active, 0)} CW · ${fmt.n(meta.universe?.underlyings, 0)} cơ sở`;
  const ver = $('#footer-version');
  if (ver) ver.textContent = `v${meta.version || ''} · methodology ${meta.methodologyVersion || ''}`;

  const stale = $('#stale-banner');
  if (stale) {
    const days = meta.dataAgeDays ?? 0;
    if (days > 3) {
      stale.classList.remove('hidden');
      stale.innerHTML = `<b>Cảnh báo dữ liệu cũ:</b> phiên gần nhất là ${meta.asofLabel} (${days} ngày trước). `
        + 'Các khuyến nghị và mức giá bên dưới có thể không còn hiệu lực — không sử dụng như giá realtime.';
    } else {
      stale.classList.add('hidden');
    }
  }
}

async function boot() {
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

  registerRoute('overview', overview);
  registerRoute('heatmap', heatmap);
  registerRoute('screener', screener);
  registerRoute('cw', detail);
  registerRoute('recommendations', (view) => recommendationsPage(view));
  registerRoute('backtest', (view) => backtestPage(view));
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

  // cảnh báo định kỳ nhẹ: nếu watchlist có mã đáo hạn < 7 ngày, nhắc một lần / phiên
  const wl = store.get('watchlist', []);
  const soon = wl.map((t) => data.row(t)).filter((r) => r && (r.dte ?? 999) < 7);
  if (soon.length) {
    const key = `notified:${data.meta?.asof}`;
    if (!store.get(key, false)) {
      setTimeout(() => {
        toast(`${soon.length} CW trong watchlist sắp đáo hạn (<7 ngày): ${soon.map((r) => r.t).join(', ')}`, 6000);
        store.set(key, true);
      }, 1200);
    }
  }
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

boot();
