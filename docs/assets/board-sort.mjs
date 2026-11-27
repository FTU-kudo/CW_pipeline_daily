const isMissing = value => value === null || value === undefined || value === '' ||
  (typeof value === 'number' && !Number.isFinite(value));

/** Sort a filtered board list, keeping unavailable values at the bottom in either direction. */
export function sortBoardRows(rows, key, direction, getValue = row => row[key]) {
  if (!key) return [...rows];
  const sign = direction === 'asc' ? 1 : -1;
  return rows.map((row, index) => ({row, index, value: getValue(row, key)}))
    .sort((a, b) => {
      const aMissing = isMissing(a.value), bMissing = isMissing(b.value);
      if (aMissing !== bMissing) return aMissing ? 1 : -1;
      if (aMissing) return a.index - b.index;
      let comparison;
      const aNumber = typeof a.value === 'number' ? a.value : Number(a.value);
      const bNumber = typeof b.value === 'number' ? b.value : Number(b.value);
      const aNumeric = Number.isFinite(aNumber), bNumeric = Number.isFinite(bNumber);
      if (aNumeric && bNumeric) {
        comparison = aNumber === bNumber ? 0 : aNumber < bNumber ? -1 : 1;
      } else if (aNumeric !== bNumeric) {
        // Mixed numeric and non-numeric values occur when a feed uses a dash for missing data.
        return aNumeric ? -1 : 1;
      } else {
        comparison = String(a.value).localeCompare(String(b.value), 'vi', {numeric: true, sensitivity: 'base'});
      }
      return comparison === 0 ? a.index - b.index : comparison * sign;
    })
    .map(item => item.row);
}
