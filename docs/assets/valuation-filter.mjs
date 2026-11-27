export const valuationRangeFilters = [
  ['iv', 'IV'],
  ['ivGroupMedian', 'IV nhóm'],
  ['ivResidualPct', 'Chênh lệch IV'],
  ['ivMinusHv', 'IV − HV'],
  ['delta', 'Delta'],
  ['strike', 'Strike'],
  ['underlyingPrice', 'Giá cơ sở (S)'],
  ['cwPrice', 'Giá CW'],
  ['daysToMaturity', 'Đáo hạn (ngày)'],
  ['premiumPct', 'Premium'],
];

export function activeValuationAdvancedCount(filters = {}) {
  return valuationRangeFilters.reduce((count, [key]) => count + Number(
    (filters[key]?.min !== '' && filters[key]?.min != null) ||
    (filters[key]?.max !== '' && filters[key]?.max != null),
  ), 0);
}

export function activeValuationFilterCount(filters = {}) {
  return Number(Boolean(filters.underlying)) + Number(Boolean(filters.moneyness)) + activeValuationAdvancedCount(filters);
}

export function filterValuationRows(rows, query = '', filters = {}) {
  const needle = String(query).trim().toLocaleLowerCase();
  return (rows || []).filter(row => {
    if (needle && !Object.values(row).some(value => String(value ?? '').toLocaleLowerCase().includes(needle))) return false;
    if (filters.underlying && String(row.underlying ?? '') !== filters.underlying) return false;
    if (filters.moneyness && String(row.moneyness ?? '—') !== filters.moneyness) return false;
    for (const [key] of valuationRangeFilters) {
      const range = filters[key] || {};
      const min = range.min === '' || range.min == null ? null : Number(range.min);
      const max = range.max === '' || range.max == null ? null : Number(range.max);
      if (min === null && max === null) continue;
      if (row[key] === null || row[key] === undefined || row[key] === '') return false;
      const value = Number(row[key]);
      if (!Number.isFinite(value) || (min !== null && value < min) || (max !== null && value > max)) return false;
    }
    return true;
  });
}
