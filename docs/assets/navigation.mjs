const VIEW_LABELS_VI = Object.freeze({
  board: 'Bảng giá',
  scoring: 'Xếp hạng',
  valuation: 'Định giá',
  liquidity: 'Thanh khoản',
  underlyings: 'Theo cơ sở',
  stale: 'Mã không giao dịch',
  intraday: 'Trong phiên',
  band: 'Trần–sàn',
  history: 'Lịch sử',
  glossary: 'Giải thích thuật ngữ',
});

export function slugifyVietnamese(value) {
  return String(value ?? '')
    .trim()
    .toLocaleLowerCase('vi')
    .replace(/đ/g, 'd')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

export const VIEW_SLUGS = Object.freeze(Object.fromEntries(
  Object.entries(VIEW_LABELS_VI).map(([view, label]) => [view, slugifyVietnamese(label)]),
));

const SLUG_VIEWS = new Map(Object.entries(VIEW_SLUGS).map(([view, slug]) => [slug, view]));

export function viewFromSearch(search) {
  const slug = new URLSearchParams(search).get('tab');
  return SLUG_VIEWS.get(slug) ?? 'board';
}

/** Build a same-page URL; never creates nested routes or triggers a document load. */
export function urlForView(href, view) {
  const url = new URL(href);
  const slug = VIEW_SLUGS[view];
  if (!slug || view === 'board') url.searchParams.delete('tab');
  else url.searchParams.set('tab', slug);
  return `${url.pathname}${url.search}${url.hash}`;
}
