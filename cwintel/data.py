"""Nạp & chuẩn hoá dữ liệu thị trường từ cache parquet.

Nguyên tắc:
  * Không gọi mạng.
  * Không sửa cache tại đây (chỉ đọc) — pipeline là nơi duy nhất ghi cache.
  * Dedupe theo `(ticker, ngày)` đã chuẩn hoá, không theo chuỗi thô.
  * Giữ cột nguồn `src_fmt` để audit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config
from .dates import parse_date, parse_dates, parse_numbers, to_number


# ──────────────────────────────────────────────────────────────────
# ISSUER CHUẨN HOÁ
# ──────────────────────────────────────────────────────────────────
# Bảng ánh xạ theo thứ tự ưu tiên (so khớp substring, không phân biệt hoa thường).
ISSUER_MAP = [
    ("shinhan", ("Shinhan", "Shinhan Việt Nam")),
    ("kis", ("KIS", "Korea Investment")),
    ("ssi", ("Chứng khoán SSI", "SSI")),
    ("hsc", ("Hồ Chí Minh", "HSC")),
    ("acbs", ("Chứng khoán ACB", "ACBS")),
    ("vndirect", ("VNDIRECT",)),
    ("vietcap", ("Vietcap", "Bản Việt")),
    ("vpbank", ("VPBank", "VP Bank")),
    ("mbs", ("Chứng khoán MB", "MBS", "MB ")),
    ("kafi", ("KAFI",)),
    ("lpbs", ("LPBank", "Lien Viet", "LPB")),
    ("phs", ("Phú Hưng", "PHS")),
    ("lps", ("LPS",)),
    ("tcbs", ("Kỹ Thương", "Techcom", "TCBS")),
    ("maybank", ("Maybank",)),
    ("bvsc", ("BIDV", "BVSC")),
    ("pinetree", ("Pinetree",)),
    ("kbsv", ("KB Việt Nam", "KB Securities", "KBSV")),
]

ISSUER_FULL = {
    "shinhan": "Shinhan Securities Việt Nam",
    "kis": "KIS Việt Nam",
    "ssi": "SSI Securities",
    "hsc": "HSC (Chứng khoán TP.HCM)",
    "acbs": "ACBS (Chứng khoán ACB)",
    "vndirect": "VNDIRECT",
    "vietcap": "Vietcap",
    "vpbank": "VPBank Securities",
    "mbs": "MBS (Chứng khoán MB)",
    "kafi": "KAFI (Chứng khoán KAFI)",
    "lpbs": "LPBank Securities",
    "phs": "PHS (Chứng khoán Phú Hưng)",
    "lps": "LPBank Securities (LPS)",
    "tcbs": "TCBS (Chứng khoán Kỹ Thương)",
    "maybank": "Maybank Securities",
    "bvsc": "BIDV Securities",
    "pinetree": "Pinetree Securities",
    "kbsv": "KB Securities Việt Nam",
}


def canonical_issuer(raw: str | None) -> str:
    if raw is None:
        return "khac"
    s = str(raw).lower()
    for key, needles in ISSUER_MAP:
        if any(n.lower() in s for n in needles):
            return key
    return "khac"


def issuer_name(key: str) -> str:
    return ISSUER_FULL.get(key, key.upper())


# ──────────────────────────────────────────────────────────────────
# KẾT QUẢ NẠP
# ──────────────────────────────────────────────────────────────────
@dataclass
class MarketData:
    asof: pd.Timestamp
    ohlcv: pd.DataFrame                       # ticker, date, o/h/l/c (VND), volume
    underlying: pd.DataFrame                  # ticker(=symbol), date, o/h/l/c (VND), volume
    master: pd.DataFrame                      # metadata 1 dòng / CW
    risk_free: float
    risk_free_source: str
    risk_free_date: pd.Timestamp | None
    diagnostics: dict = field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────
def _price_to_vnd(series: pd.Series) -> pd.Series:
    """Cache lưu nghìn VND (vd 0.78 = 780 VND). Nếu nguồn đã là VND thì giữ nguyên."""
    s = pd.to_numeric(series, errors="coerce")
    med = s[s > 0].median()
    if pd.notna(med) and med > 1000:
        return s
    return s * 1000.0


def _canonical_ohlcv(df: pd.DataFrame, name: str) -> tuple[pd.DataFrame, dict]:
    diag = {"rows_in": int(len(df)), "duplicates_removed": 0, "unparsed_dates": 0,
            "src_fmt_counts": {}}
    if df is None or df.empty:
        return pd.DataFrame(), diag

    out = pd.DataFrame({
        "ticker": df["Ticker"].astype(str).str.strip(),
        "raw_date": df["time"].astype(str),
        "date": parse_dates(df["time"]),
    })
    raw_len = out["raw_date"].str.len()
    # Nguồn dd/mm/yyyy (10 ký tự) là định dạng chuẩn của pipeline; còn lại là ISO +07:00
    out["src_fmt"] = np.where(raw_len <= 10, "dmy", "iso")
    diag["src_fmt_counts"] = out["src_fmt"].value_counts().to_dict()
    diag["unparsed_dates"] = int(out["date"].isna().sum())

    for col in ("open", "high", "low", "close"):
        if col in df.columns:
            out[col] = _price_to_vnd(df[col])
    if "volume" in df.columns:
        out["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)

    out = out.dropna(subset=["date"]).copy()
    out = out[out["ticker"].str.len() > 0]

    # Dedupe theo (ticker, ngày). Ưu tiên bản ghi có volume lớn hơn (phiên đầy đủ),
    # hoà thì ưu tiên định dạng chuẩn dd/mm/yyyy.
    out["_vol"] = out.get("volume", pd.Series(0.0, index=out.index)).fillna(0.0)
    out["_pref"] = (out["src_fmt"] == "dmy").astype(int)
    out = out.sort_values(["ticker", "date", "_vol", "_pref"])
    before = len(out)
    out = out.drop_duplicates(subset=["ticker", "date"], keep="last")
    diag["duplicates_removed"] = int(before - len(out))
    out = out.drop(columns=["_vol", "_pref"]).reset_index(drop=True)

    # Sắp xếp và loại các phiên không hợp lệ
    out = out.sort_values(["ticker", "date"]).reset_index(drop=True)
    for col in ("close", "open", "high", "low"):
        if col in out.columns:
            out.loc[out[col] <= 0, col] = np.nan

    diag["rows_out"] = int(len(out))
    diag["tickers"] = int(out["ticker"].nunique())
    diag["date_min"] = out["date"].min().strftime("%Y-%m-%d") if len(out) else None
    diag["date_max"] = out["date"].max().strftime("%Y-%m-%d") if len(out) else None
    diag["name"] = name
    return out, diag


# ──────────────────────────────────────────────────────────────────
# MASTER (điều khoản CW)
# ──────────────────────────────────────────────────────────────────
def build_master(vs: pd.DataFrame, asof: pd.Timestamp) -> pd.DataFrame:
    """Chuẩn hoá metadata Vietstock thành bảng điều khoản CW.

    Quy tắc chọn strike/ratio: dùng bản **đã điều chỉnh** khi có (điều khoản thực tế
    tại thời điểm hiện tại), nếu không có thì dùng bản gốc. Ghi rõ bằng cột
    `terms_adjusted`.
    """
    df = pd.DataFrame(index=vs.index)
    df["ticker"] = vs["ma_cw"].astype(str).str.strip()
    df["underlying"] = vs["ck_co_so"].astype(str).str.strip().str.upper()
    df["issuer_raw"] = vs["to_chuc_ph_cw"].astype(str).str.strip()
    df["issuer"] = df["issuer_raw"].map(canonical_issuer)
    df["issuer_name"] = df["issuer"].map(issuer_name)

    df["issue_date"] = parse_dates(vs["ngay_phat_hanh"])
    df["listing_date"] = parse_dates(vs["ngay_niem_yet"])
    df["first_trade"] = parse_dates(vs["ngay_gd_dau_tien"])
    df["last_trade"] = parse_dates(vs["ngay_gd_cuoi_cung"])
    df["maturity"] = parse_dates(vs["ngay_dao_han"])

    df["K_raw"] = parse_numbers(vs["gia_thuc_hien"])
    df["K_adj"] = parse_numbers(vs["gia_th_dieu_chinh"])
    df["ratio_raw"] = parse_numbers(vs["ty_le_chuyen_doi"])
    df["ratio_adj"] = parse_numbers(vs["tlcd_dieu_chinh"])
    df["terms_adjusted"] = df["K_adj"].notna() & df["ratio_adj"].notna()
    df["K"] = df["K_adj"].fillna(df["K_raw"])
    df["ratio"] = df["ratio_adj"].fillna(df["ratio_raw"])
    # Chỉnh lại nếu ratio/ K bị lệch do Vietstock trả về dạng nghìn đồng
    df.loc[(df["K"] > 0) & (df["K"] < 1000), "K"] = np.nan

    df["listed_volume"] = parse_numbers(vs["kl_niem_yet"])
    df["outstanding_volume"] = parse_numbers(vs["kl_luu_hanh"])
    df["term_label"] = vs.get("thoi_han", "").astype(str)
    df["price_vs"] = parse_numbers(vs["gia_hien_tai"])
    df["be_vs"] = parse_numbers(vs["hoa_von"])
    df["moneyness_vs"] = vs.get("trang_thai_cw", "").astype(str)
    df["underlying_vs"] = parse_numbers(vs["gia_ck_co_so"])

    # Trạng thái theo điều khoản hợp đồng, KHÔNG so với "hôm nay" (xem AUDIT §4).
    matured = df["maturity"].notna() & (df["maturity"] < asof)
    stopped = df["last_trade"].notna() & (df["last_trade"] < asof - pd.Timedelta(days=7))
    df["is_active"] = ~(matured | stopped)
    # CW đã ngừng giao dịch nhưng chưa tới ngày đáo hạn (huỷ niêm yết)
    df["delisted_early"] = (~matured) & stopped
    df["status"] = np.where(df["is_active"], "active", "expired")

    df["days_to_maturity"] = (df["maturity"] - asof).dt.days
    df["T"] = df["days_to_maturity"] / config.DAYS_PER_YEAR

    # Lỗi điều khoản
    bad_terms = df["K"].isna() | df["ratio"].isna() | (df["K"] <= 0) | (df["ratio"] <= 0)
    df.loc[bad_terms, "K"] = df.loc[bad_terms, "K"].fillna(np.nan)
    df["terms_valid"] = ~bad_terms
    df = df[df["ticker"].str.len() > 0].drop_duplicates(subset="ticker", keep="last")
    return df.reset_index(drop=True)


def load_market_data(asof: pd.Timestamp | None = None) -> MarketData:
    """Nạp toàn bộ dữ liệu cần cho tầng phân tích."""
    diag: dict = {}

    # ── OHLCV CW
    if config.OHLCV_CACHE.exists():
        oh, d1 = _canonical_ohlcv(pd.read_parquet(config.OHLCV_CACHE), "ohlcv_cw")
    else:
        oh, d1 = pd.DataFrame(), {"name": "ohlcv_cw", "rows_in": 0}
    diag["ohlcv"] = d1

    # ── Underlying
    if config.UNDERLYING_CACHE.exists():
        und, d2 = _canonical_ohlcv(pd.read_parquet(config.UNDERLYING_CACHE), "underlying")
    else:
        und, d2 = pd.DataFrame(), {"name": "underlying", "rows_in": 0}
    und = und.rename(columns={"ticker": "ticker"})
    diag["underlying"] = d2

    if asof is None:
        cands = [d for d in (oh["date"].max() if len(oh) else None,
                             und["date"].max() if len(und) else None) if d is not None]
        asof = max(cands) if cands else pd.Timestamp.utcnow().normalize()
    asof = pd.Timestamp(asof).normalize()

    vs = pd.read_parquet(config.VIETSTOCK_CACHE) if config.VIETSTOCK_CACHE.exists() else pd.DataFrame()
    master = build_master(vs, asof) if not vs.empty else pd.DataFrame()
    diag["master"] = {
        "rows": int(len(master)),
        "active": int(master["is_active"].sum()) if len(master) else 0,
        "expired": int((~master["is_active"]).sum()) if len(master) else 0,
        "issuers": int(master["issuer"].nunique()) if len(master) else 0,
        "underlyings": int(master["underlying"].nunique()) if len(master) else 0,
        "missing_terms": int((~master["terms_valid"]).sum()) if len(master) else 0,
        "adjusted_terms": int(master["terms_adjusted"].sum()) if len(master) else 0,
    }

    r, src, rdate = load_risk_free()
    return MarketData(asof=asof, ohlcv=oh, underlying=und, master=master,
                      risk_free=r, risk_free_source=src, risk_free_date=rdate,
                      diagnostics=diag)


def load_risk_free() -> tuple[float, str, pd.Timestamp | None]:
    """Lãi suất phi rủi ro 10Y (continuous, thập phân) từ cache HNX; fallback có ghi nguồn."""
    if config.BOND_CACHE.exists():
        try:
            df = pd.read_csv(config.BOND_CACHE)
            df["date"] = parse_dates(df["date"])
            df = df.dropna(subset=["date"]).sort_values("date")
            if "10Y" in df.columns and df["10Y"].notna().any():
                last = df.dropna(subset=["10Y"]).iloc[-1]
                return float(last["10Y"]) / 100.0, "hnx_yield_curve_cache", last["date"]
        except Exception:  # pragma: no cover - cache hỏng
            pass
    return config.DEFAULT_RISK_FREE, "default_constant", None


def price_series_for(ohlcv: pd.DataFrame, ticker: str) -> pd.DataFrame:
    return ohlcv[ohlcv["ticker"] == ticker].sort_values("date").reset_index(drop=True)


def last_price_map(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Giá đóng cửa mới nhất + ngày mới nhất cho từng ticker."""
    if ohlcv.empty:
        return pd.DataFrame(columns=["ticker", "date", "close"])
    idx = ohlcv.groupby("ticker")["date"].idxmax()
    return ohlcv.loc[idx, ["ticker", "date", "close"]].reset_index(drop=True)
