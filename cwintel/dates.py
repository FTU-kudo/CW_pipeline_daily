"""Chuẩn hoá ngày & số — nguồn duy nhất cho toàn bộ pipeline.

Bối cảnh (xem docs/AUDIT.md §2): cache OHLCV chứa 2 định dạng ngày
(`14/03/2023` và `2023-03-14 07:00:00`) cho cùng một phiên. Parse bằng
`pd.to_datetime(..., dayfirst=True)` trả NaT cho toàn bộ nhóm ISO, làm mất
49% số dòng. Module này parse tường minh theo từng định dạng và không bao giờ
để pandas tự đoán.
"""

from __future__ import annotations

import re
from typing import Iterable

import numpy as np
import pandas as pd

_DMY_RE = re.compile(r"^\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})")
_YMD_RE = re.compile(r"^\s*(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})")
_NUM_CLEAN_RE = re.compile(r"[^0-9.\-]")


def parse_date(value) -> pd.Timestamp | None:
    """Parse một giá trị ngày bất kỳ về `pd.Timestamp` (naive, chỉ phần ngày).

    Hỗ trợ: dd/mm/yyyy, yyyy-mm-dd, ISO8601 có giờ (bỏ phần giờ + offset),
    datetime/date/Timestamp của Python. Trả None nếu không đọc được.
    """
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        ts = value
    elif hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        try:
            ts = pd.Timestamp(value)
        except (ValueError, TypeError):
            return None
    else:
        s = str(value).strip()
        if not s or s.lower() in {"nan", "nat", "none", "null", "-"}:
            return None
        m = _YMD_RE.match(s)
        if m:
            y, mo, d = (int(x) for x in m.groups())
            ts = pd.Timestamp(year=y, month=mo, day=d)
        else:
            m = _DMY_RE.match(s)
            if not m:
                return None
            d, mo, y = (int(x) for x in m.groups())
            ts = pd.Timestamp(year=y, month=mo, day=d)
    if pd.isna(ts):
        return None
    return ts.normalize()


def parse_dates(series: Iterable) -> pd.Series:
    """Vector hoá `parse_date` cho một Series bất kỳ (kể cả object/string)."""
    s = pd.Series(series)
    if pd.api.types.is_datetime64_any_dtype(s):
        return s.dt.normalize()
    if len(s) == 0:
        return pd.Series([], dtype="datetime64[ns]")
    # Fast path: toàn bộ là ISO hoặc toàn bộ là dd/mm
    vals = s.astype(str).str.strip()
    head = vals.iloc[0]
    if _YMD_RE.match(head) and vals.str.match(_YMD_RE.pattern).all():
        return pd.to_datetime(vals.str.slice(0, 10), format="%Y-%m-%d", errors="coerce").dt.normalize()
    if _DMY_RE.match(head) and vals.str.match(_DMY_RE.pattern).all():
        return pd.to_datetime(vals, format="%d/%m/%Y", errors="coerce").dt.normalize()
    out = pd.Series(pd.NaT, index=s.index, dtype="datetime64[ns]")
    for idx, v in s.items():
        ts = parse_date(v)
        if ts is not None:
            out.at[idx] = ts
    return out


def to_number(value, default=np.nan) -> float:
    """Chuyển '27,700' / '4.31' / '1.234,5' / '2 : 1' → float."""
    if value is None:
        return default
    if isinstance(value, (int, float, np.integer, np.floating)):
        return default if (isinstance(value, float) and np.isnan(value)) else float(value)
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null", "-", "n/a"}:
        return default
    s = s.split(":")[0] if ":" in s else s
    s = s.replace(" ", "").replace("%", "")
    # Định dạng Việt Nam: '.' phân tách nghìn, ',' phân tách thập phân
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        head, _, tail = s.partition(",")
        # '1,300' → 1300 ; '4,31' → 4.31
        s = s.replace(",", ".") if len(tail) <= 2 else s.replace(",", "")
    s = _NUM_CLEAN_RE.sub("", s)
    try:
        return float(s)
    except ValueError:
        return default


def parse_numbers(series: Iterable) -> pd.Series:
    s = pd.Series(series)
    if len(s) == 0:
        return pd.Series([], dtype="float64")
    if pd.api.types.is_numeric_dtype(s):
        return s.astype("float64")
    uniq = pd.unique(s.astype(object))
    if len(uniq) < 5000:
        mapping = {v: to_number(v) for v in uniq}
        return s.map(mapping).astype("float64")
    return s.map(to_number).astype("float64")


def latest_session(dates: pd.Series) -> pd.Timestamp | None:
    d = parse_dates(dates).dropna()
    return d.max() if len(d) else None


def days_between(start, end) -> float:
    a, b = parse_date(start), parse_date(end)
    if a is None or b is None:
        return float("nan")
    return (b - a).days
