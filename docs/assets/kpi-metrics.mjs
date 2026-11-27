export function finiteMetric(value) {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function metricNumber(value, digits = 0) {
  const parsed = finiteMetric(value);
  return parsed === null ? '—' : parsed.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function metricPercent(value, digits = 1) {
  const parsed = finiteMetric(value);
  return parsed === null ? '—' : `${parsed.toFixed(digits)}%`;
}

export function safeRatioPercent(value, denominator) {
  const numerator = finiteMetric(value);
  const total = finiteMetric(denominator);
  if (numerator === null || total === null) return '—';
  if (total <= 0) return '0.0';
  const percentage = (numerator / total) * 100;
  return Number.isFinite(percentage) ? percentage.toFixed(1) : '—';
}

export function safeDivide(numerator, denominator) {
  const value = finiteMetric(numerator);
  const total = finiteMetric(denominator);
  if (value === null || total === null || total <= 0) return null;
  const quotient = value / total;
  return Number.isFinite(quotient) ? quotient : null;
}
