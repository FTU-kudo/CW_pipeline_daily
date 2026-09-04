"""
bs_calculator.py
────────────────
Tự tính Black-Scholes cho Chứng quyền (CW) Việt Nam.

Inputs (đều đã có trong pipeline):
  - OHLCV underlying  → sigma (historical volatility, annualized, 252 phiên)
  - OHLCV underlying  → S (giá đóng cửa mới nhất, VND)
  - HNX yield curve   → r (Spot rate % continuous, kỳ hạn 10 năm)  ← lãi suất phi rủi ro chuẩn BS
  - df_vietstock      → K (giá thực hiện), T (ngày đến hạn), n (tỷ lệ chuyển đổi)

Công thức:
  d1  = [ln(S/K) + (r + σ²/2)·T] / (σ·√T)
  d2  = d1 - σ·√T
  C   = S·N(d1) - K·e^(-rT)·N(d2)          # Giá Call trên 1 CP cơ sở
  CW  = C / n                                # Quy về 1 CW (chia tỷ lệ chuyển đổi)
  Δ   = N(d1)                                # Delta
  EG  = (S / (CW_price × n)) × Δ            # Effective Gearing (leverage thực tế)

Lưu ý về r (CẬP NHẬT lần 2):
  Lớp "HNX chính thức (curl_cffi)" trước đây bị bỏ hẳn — sai công cụ cho đúng
  bài toán: curl_cffi chỉ giả lập TLS fingerprint, không chạy được JavaScript,
  trong khi trang duong-cong-loi-suat.html cần Vue.js render xong rồi mới lộ
  bảng (nằm trong 1 iframe lồng). Thay bằng `vnbond` (repo:
  github.com/KhoaSampleTown/vnbond, ghim commit a89cc00) — thư viện đã tự tìm
  ra đúng AJAX endpoint gốc của HNX (POST thuần, không cần trình duyệt) cho dữ
  liệu đấu thầu TPCP sơ cấp.

  Thứ tự ưu tiên nguồn r (multi-layer fallback, giống pattern iv_history.parquet
  đã dùng cho IV Rank):
    Lớp 1 — vnbond: hnx.auctions() — trực tiếp từ HNX, POST thuần, không cần
             trình duyệt, có sẵn retry/rate-limit/cache trong bản thân thư viện
    Lớp 2 — Playwright: Spot rate % (continuous) kỳ hạn 10 năm từ
             duong-cong-loi-suat.html — đường cong THỨ CẤP đã fit sẵn, khớp
             đúng convention lãi kép liên tục e^(-rT) trong công thức BS
    Lớp 3 — Cache cục bộ (hnx_10y_cache.json), dùng nếu Lớp 1+2 lỗi và cache
             chưa quá cũ (< 5 ngày)
    Lớp 4 — VBMA (lãi suất trúng thầu sơ cấp TPCP 10Y, cào độc lập với vnbond
             để phòng khi vnbond đổi cấu trúc) — proxy sơ cấp, không hoàn toàn
             tương đương spot rate thứ cấp của HNX
    Lớp 5 — Hằng số cứng (an toàn cuối cùng, không để pipeline crash)

  Cần cài (requirements.txt):
    git+https://github.com/KhoaSampleTown/vnbond.git@a89cc002206cf2e1c75c672b21adc52deb262589
    playwright, beautifulsoup4, requests, pyarrow

  MỌI kết quả BS đều lưu kèm `r_pct` để biết r hôm đó là bao nhiêu — log in ra
  luôn ghi rõ [nguồn: ...] theo từng lớp — quan trọng để audit lại nếu giá BS
  bất thường.
"""

import math
import json
import re
import unicodedata
from pathlib import Path
from datetime import date, datetime, timedelta
from typing import Optional, Tuple

import numpy as np
import pandas as pd


# ══════════════════════════════════════════════════════════════════
# CẤU HÌNH NGUỒN LÃI SUẤT PHI RỦI RO
# ══════════════════════════════════════════════════════════════════

HNX_URL = "https://www.hnx.vn/en-gb/trai-phieu/duong-cong-loi-suat.html"
HNX_TENOR_LABEL = "10 years"          # dòng cần lấy trong bảng yield curve
HNX_RATE_COLUMN = "Spot rate % (continuous)"  # đúng convention e^(-rT) trong BS

CACHE_FILE = Path("hnx_10y_cache.json")
CACHE_MAX_AGE_DAYS = 5                 # cache quá 5 ngày coi như "cũ", không tin nữa

VBMA_LIST_URL = "https://vbma.org.vn/vi/activities"
VBMA_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

VNBOND_AUCTION_LOOKBACK_DAYS = 45      # đủ rộng để bắt được phiên gọi kỳ hạn 10 năm gần nhất

_FALLBACK_RATE_10Y = 4.53   # % — an toàn cuối cùng nếu MỌI nguồn đều fail


# ══════════════════════════════════════════════════════════════════
# 1. LÃI SUẤT PHI RỦI RO — HNX 10Y
# ══════════════════════════════════════════════════════════════════

# ── Lớp 1: vnbond (HNX auctions — trực tiếp, không cần trình duyệt) ─────────

def _ascii(s) -> str:
    """Bỏ dấu tiếng Việt + hạ chữ thường trước khi so khớp tên cột.
    Dùng lại đúng kỹ thuật mà chính vnbond áp dụng nội bộ (vbma._ascii) — bẫy
    đã biết: 'ngay' in 'ngày'.lower() là False nếu không bỏ dấu trước."""
    s = unicodedata.normalize("NFKD", str(s))
    return "".join(ch for ch in s if not unicodedata.combining(ch)).lower()


def _find_col(columns, *keywords) -> Optional[str]:
    """Tìm tên cột thật khớp với TẤT CẢ từ khoá (đã chuẩn hoá bỏ dấu).
    Không hard-code tên cột chính xác vì schema thật của vnbond.hnx.auctions()
    chưa được tự kiểm chứng bằng gọi mạng sống — dò theo tên là cách an toàn."""
    for c in columns:
        norm = _ascii(c)
        if all(_ascii(k) in norm for k in keywords):
            return c
    return None


def _parse_tenor_to_years(raw) -> Optional[float]:
    """'10' hoặc '10 Năm' hoặc '10 năm' → 10.0."""
    try:
        return float(str(raw).strip().replace(",", "."))
    except ValueError:
        pass
    try:
        from vnbond.sources.hnx import _tenor_years
        return _tenor_years(raw)
    except Exception:
        return None


def _scrape_hnx_10y_via_vnbond(lookback_days: int = VNBOND_AUCTION_LOOKBACK_DAYS) -> Tuple[Optional[float], Optional[str]]:
    """
    Lớp 1: lấy kết quả đấu thầu TPCP trực tiếp từ HNX qua vnbond.hnx.auctions()
    (POST thẳng vào endpoint AJAX thật mà HNX expose — không cần trình duyệt).

    Trả về (lãi suất %, ngày đấu thầu) của kỳ hạn gần 10 năm nhất, hoặc
    (None, None) nếu không có — KHÔNG raise, để get_risk_free_rate() tự
    quyết định lớp fallback tiếp theo.
    """
    try:
        import vnbond as vm
    except ImportError:
        print("   [vnbond] Chưa cài — chạy: pip install \"git+https://github.com/"
              "KhoaSampleTown/vnbond.git@a89cc002206cf2e1c75c672b21adc52deb262589\"")
        return None, None

    try:
        start = (date.today() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        end = date.today().strftime("%Y-%m-%d")
        df = vm.hnx.auctions(start=start, end=end, verbose=False)
    except Exception as e:
        print(f"   [vnbond] Lỗi khi gọi hnx.auctions(): {e}")
        return None, None

    if df is None or df.empty:
        print("   [vnbond] Không có phiên đấu thầu nào trong khoảng lookback.")
        return None, None

    col_date = _find_col(df.columns, "ngay", "dau thau") or _find_col(df.columns, "ngay")
    col_tenor = _find_col(df.columns, "ky han") or _find_col(df.columns, "ki han")
    col_rate = _find_col(df.columns, "lai suat", "trung thau") or _find_col(df.columns, "lai suat")

    if not all([col_date, col_tenor, col_rate]):
        print(f"   [vnbond] Không dò được đủ 3 cột cần thiết. "
              f"Cột thật trả về: {list(df.columns)} — cần bạn xác nhận tay.")
        return None, None

    df = df.copy()
    df["_tenor_yrs"] = df[col_tenor].map(_parse_tenor_to_years)
    df["_rate"] = df[col_rate].apply(
        lambda x: float(str(x).replace(",", ".")) if str(x).strip() not in ("", "-", "nan") else None
    )
    df["_date_parsed"] = pd.to_datetime(df[col_date], dayfirst=True, errors="coerce")

    df = df.dropna(subset=["_tenor_yrs", "_rate", "_date_parsed"])
    df = df[(df["_tenor_yrs"] - 10).abs() <= 0.5]   # chấp nhận đúng kỳ hạn "10"
    if df.empty:
        print("   [vnbond] Không có phiên nào gọi thầu kỳ hạn 10 năm trong lookback.")
        return None, None

    df = df.sort_values("_date_parsed", ascending=False)
    best = df.iloc[0]
    return float(best["_rate"]), best["_date_parsed"].strftime("%Y-%m-%d")


# ── Lớp 2: Playwright (đường cong thứ cấp đã fit sẵn của HNX) ───────────────

def _scrape_hnx_yield_curve(timeout_ms: int = 60_000, wait_after_load_ms: int = 5_000):
    """
    Scrape bảng đường cong lợi suất HNX bằng Playwright (Sync API).
    Bảng nằm trong 1 iframe lồng (class 'html-preview-frame'), không lộ qua
    HTML tĩnh hay request JSON nào — phải duyệt qua page.frames để tìm.

    Trả về (DataFrame[Tenor, Spot rate % (continuous), Par yield (%), Spot rate % (annual)], ref_date)
    hoặc (None, None) nếu lỗi — KHÔNG raise exception ra ngoài, để lớp gọi tự quyết định fallback.
    """
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],  # cần thiết trên runner GitHub Actions
            )
            page = browser.new_page()
            try:
                page.goto(HNX_URL, wait_until="networkidle", timeout=timeout_ms)
                page.wait_for_timeout(wait_after_load_ms)

                target_frame = next(
                    (f for f in page.frames if f.query_selector("#_tableDatas")), None
                )
                if target_frame is None:
                    print("   [HNX scrape] Không tìm thấy iframe chứa bảng — cấu trúc trang có thể đã đổi.")
                    return None, None

                rows = target_frame.query_selector_all("#_tableDatas tbody tr")
                data = []
                for r in rows:
                    cols = r.query_selector_all("td")
                    data.append([c.inner_text().strip() for c in cols])

                date_input = page.query_selector("#txtDateYC")
                ref_date = date_input.get_attribute("value") if date_input else None

                if not data:
                    print("   [HNX scrape] Bảng rỗng.")
                    return None, None

                df = pd.DataFrame(
                    data,
                    columns=["Tenor", "Spot rate % (continuous)", "Par yield (%)", "Spot rate % (annual)"],
                )
                return df, ref_date
            finally:
                browser.close()

    except Exception as e:
        print(f"   [HNX scrape] Lỗi Playwright: {e}")
        return None, None


def _extract_tenor_rate(df: pd.DataFrame, tenor_label: str, column: str) -> Optional[float]:
    """Lấy giá trị (%) tại đúng kỳ hạn từ bảng đã scrape. Trả về None nếu không khớp/không parse được."""
    if df is None or df.empty:
        return None
    match = df[df["Tenor"].str.strip().str.lower() == tenor_label.lower()]
    if match.empty:
        print(f"   [HNX scrape] Không thấy kỳ hạn '{tenor_label}' trong bảng.")
        return None
    raw = str(match.iloc[0][column]).replace(",", ".").strip()
    try:
        return float(raw)
    except ValueError:
        print(f"   [HNX scrape] Không parse được giá trị '{raw}' ở cột '{column}'.")
        return None


# ── Lớp 3: cache cục bộ ──────────────────────────────────────────────────────

def _load_cache() -> Optional[dict]:
    if not CACHE_FILE.exists():
        return None
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_cache(rate_pct: float, ref_date: Optional[str], tenor_label: str, column: str) -> None:
    CACHE_FILE.write_text(
        json.dumps(
            {
                "rate_pct": rate_pct,
                "ref_date": ref_date,
                "tenor": tenor_label,
                "column": column,
                "fetched_at": datetime.now().isoformat(timespec="seconds"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _cache_is_fresh(cache: dict) -> bool:
    try:
        fetched_at = datetime.fromisoformat(cache["fetched_at"])
    except Exception:
        return False
    return (datetime.now() - fetched_at) <= timedelta(days=CACHE_MAX_AGE_DAYS)


# ── Lớp 4: VBMA (fallback độc lập, phòng khi vnbond đổi cấu trúc) ───────────

def _scrape_vbma_10y_auction(limit_articles: int = 6) -> Optional[float]:
    """
    Lãi suất trúng thầu SƠ CẤP TPCP kỳ hạn 10 năm, công bố bởi VBMA.
    LƯU Ý: đây khác bản chất với spot rate THỨ CẤP của HNX — chỉ dùng khi
    Lớp 1+2+3 đều fail. Cào độc lập (requests+BeautifulSoup) với vnbond để
    không cùng lúc sập nếu vnbond đổi cấu trúc.
    """
    import requests
    from bs4 import BeautifulSoup

    try:
        r = requests.get(VBMA_LIST_URL, headers=VBMA_HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        urls = []
        for a in soup.find_all("a", href=True):
            if "ket-qua-dau-thau-trai-phieu-chinh-phu" in a["href"]:
                full = a["href"] if a["href"].startswith("http") else "https://vbma.org.vn" + a["href"]
                if full not in urls:
                    urls.append(full)
            if len(urls) >= limit_articles:
                break

        for url in urls:
            rr = requests.get(url, headers=VBMA_HEADERS, timeout=15)
            rr.raise_for_status()
            s2 = BeautifulSoup(rr.text, "html.parser")
            for table in s2.find_all("table"):
                rows = table.find_all("tr")
                if not rows:
                    continue
                headers_ = [c.get_text(strip=True).lower() for c in rows[0].find_all(["th", "td"])]
                idx_tenor = next((i for i, h in enumerate(headers_) if "kỳ hạn" in h or "kì hạn" in h), None)
                idx_rate = next((i for i, h in enumerate(headers_) if "lãi suất trúng thầu" in h), None)
                if idx_tenor is None or idx_rate is None:
                    continue
                for row in rows[1:]:
                    cols = [c.get_text(strip=True) for c in row.find_all("td")]
                    if len(cols) <= max(idx_tenor, idx_rate):
                        continue
                    if cols[idx_tenor].strip() == "10":
                        rate_str = cols[idx_rate].replace(",", ".").strip()
                        if rate_str and rate_str != "-":
                            print(f"   [VBMA fallback] Lãi suất trúng thầu 10Y ({url}): {rate_str}%")
                            return float(rate_str)
        return None
    except Exception as e:
        print(f"   [VBMA fallback] Lỗi: {e}")
        return None


# ── Điều phối 5 lớp ───────────────────────────────────────────────────────

def get_risk_free_rate(as_of_date: Optional[str] = None) -> float:
    """
    Lấy lãi suất phi rủi ro cho BS. Multi-layer fallback — KHÔNG bao giờ raise,
    luôn trả về 1 float dùng được.

      Lớp 1 — vnbond: hnx.auctions() (trực tiếp HNX, không cần trình duyệt)
      Lớp 2 — Playwright: Spot rate % (continuous) 10Y (đường cong đã fit sẵn)
      Lớp 3 — Cache cục bộ (< 5 ngày)
      Lớp 4 — VBMA auction scraper (độc lập code path)
      Lớp 5 — Hằng số cứng

    Returns:
        float: lãi suất dạng thập phân (vd: 0.043671 cho 4.3671%)
    """
    # ── Lớp 1: vnbond ─────────────────────────────────────────────
    rate_pct, auction_date = _scrape_hnx_10y_via_vnbond()
    if rate_pct is not None:
        _save_cache(rate_pct, auction_date, "10Y (auction)", "vnbond.hnx.auctions")
        print(f"   r (HNX 10Y trúng thầu, phiên {auction_date}): {rate_pct:.4f}%  [nguồn: vnbond]")
        return rate_pct / 100

    # ── Lớp 2: Playwright — đường cong thứ cấp đã fit sẵn ───────────
    df, ref_date = _scrape_hnx_yield_curve()
    rate_pct = _extract_tenor_rate(df, HNX_TENOR_LABEL, HNX_RATE_COLUMN)
    if rate_pct is not None:
        _save_cache(rate_pct, ref_date, HNX_TENOR_LABEL, HNX_RATE_COLUMN)
        print(f"   r (HNX 10Y continuous, ngày {ref_date}): {rate_pct:.4f}%  [nguồn: HNX Playwright]")
        return rate_pct / 100

    # ── Lớp 3: cache gần nhất còn "tươi" ─────────────────────────
    cache = _load_cache()
    if cache and _cache_is_fresh(cache):
        print(f"   r (cache, lấy lúc {cache['fetched_at']}): {cache['rate_pct']:.4f}%  [nguồn: cache]")
        return cache["rate_pct"] / 100

    # ── Lớp 4: VBMA auction 10Y (proxy sơ cấp, độc lập vnbond) ──────
    vbma_rate = _scrape_vbma_10y_auction()
    if vbma_rate is not None:
        print(f"   r (VBMA auction 10Y): {vbma_rate:.4f}%  [nguồn: VBMA — CHÚ Ý: sơ cấp, không phải spot HNX]")
        return vbma_rate / 100

    # ── Lớp 5: cache cũ còn hơn không, hoặc hằng số cứng ─────────
    if cache:
        print(f"   r (cache ĐÃ CŨ, {cache['fetched_at']}): {cache['rate_pct']:.4f}%  [nguồn: cache cũ]")
        return cache["rate_pct"] / 100

    print(f"   r (fallback hardcoded): {_FALLBACK_RATE_10Y:.3f}%  [nguồn: hằng số cứng]")
    return _FALLBACK_RATE_10Y / 100


# ══════════════════════════════════════════════════════════════════
# 2. SIGMA — HISTORICAL VOLATILITY TỪ OHLCV UNDERLYING
# ══════════════════════════════════════════════════════════════════

def calc_sigma(ohlcv_underlying: pd.DataFrame,
               window: int = 252,
               as_of_date: Optional[str] = None) -> float:
    """
    Tính Annualized Sigma (σ) từ log-return giá đóng cửa của CK cơ sở.
    Dùng đúng 252 phiên giao dịch gần nhất (chuẩn Vietstock/Bloomberg).
    """
    df = ohlcv_underlying.copy()

    if not isinstance(df.index, pd.DatetimeIndex):
        time_col = next((c for c in ["time", "date", "Date"] if c in df.columns), None)
        if time_col:
            df[time_col] = pd.to_datetime(df[time_col], dayfirst=True, errors="coerce")
            df = df.set_index(time_col)
        else:
            raise ValueError("ohlcv_underlying cần có index datetime hoặc cột 'time'/'date'")

    df = df.sort_index()

    close = df["close"].dropna().copy()
    if close.median() < 1000:
        close = close * 1000

    if as_of_date:
        close = close[close.index <= pd.to_datetime(as_of_date)]

    if len(close) < 20:
        raise ValueError(f"Không đủ dữ liệu để tính sigma (chỉ có {len(close)} phiên)")

    close = close.iloc[-window:]
    log_returns = np.log(close / close.shift(1)).dropna()
    sigma = float(log_returns.std() * math.sqrt(252))

    print(f"   σ ({len(log_returns)} phiên): {sigma:.4f} ({sigma*100:.2f}%/năm)")
    return round(sigma, 4)


def calc_sigma_series(ohlcv_underlying: pd.DataFrame,
                      window: int = 252) -> pd.Series:
    """Chuỗi sigma rolling theo ngày — dùng cho backtesting / chart lịch sử."""
    df = ohlcv_underlying.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        time_col = next((c for c in ["time", "date"] if c in df.columns), None)
        if time_col:
            df = df.set_index(pd.to_datetime(df[time_col], dayfirst=True, errors="coerce"))
    df = df.sort_index()

    close = df["close"].dropna()
    if close.median() < 1000:
        close = close * 1000

    log_ret = np.log(close / close.shift(1))
    sigma_series = log_ret.rolling(window=window, min_periods=20).std() * math.sqrt(252)
    return sigma_series.round(4)


# ══════════════════════════════════════════════════════════════════
# 3. BLACK-SCHOLES CORE
# ══════════════════════════════════════════════════════════════════

def _norm_cdf(x: float) -> float:
    """CDF phân phối chuẩn N(0,1) — dùng math.erf để tránh phụ thuộc scipy."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_call(S: float, K: float, T: float, r: float, sigma: float) -> dict:
    """Tính giá Call theo Black-Scholes và các Greeks cơ bản."""
    if T <= 0:
        intrinsic = max(S - K, 0.0)
        return {
            "price": round(intrinsic, 2),
            "delta": 1.0 if S > K else 0.0,
            "gamma": 0.0, "theta": 0.0, "vega": 0.0,
            "d1": float("inf"), "d2": float("inf"),
        }

    if sigma <= 0 or S <= 0 or K <= 0:
        return {"price": 0.0, "delta": 0.0, "gamma": 0.0,
                "theta": 0.0, "vega": 0.0, "d1": 0.0, "d2": 0.0}

    sqrt_T = math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    Nd1  = _norm_cdf(d1)
    Nd2  = _norm_cdf(d2)
    nd1  = math.exp(-0.5 * d1 ** 2) / math.sqrt(2 * math.pi)
    disc = math.exp(-r * T)

    price = S * Nd1 - K * disc * Nd2

    delta = Nd1
    gamma = nd1 / (S * sigma * sqrt_T)
    theta = (-(S * nd1 * sigma) / (2 * sqrt_T) - r * K * disc * Nd2) / 365
    vega  = S * nd1 * sqrt_T / 100

    return {
        "price": round(price, 2),
        "delta": round(delta, 4),
        "gamma": round(gamma, 6),
        "theta": round(theta, 2),
        "vega" : round(vega, 2),
        "d1"   : round(d1, 4),
        "d2"   : round(d2, 4),
    }


# ══════════════════════════════════════════════════════════════════
# 4. HÀM TỔNG HỢP — TÍNH BS CHO 1 CW
# ══════════════════════════════════════════════════════════════════

def calc_bs_for_cw(
    cw_info:            dict,
    ohlcv_underlying:   pd.DataFrame,
    risk_free_rate:     Optional[float] = None,
    as_of_date:         Optional[str]   = None,
) -> dict:
    """Tính đầy đủ Black-Scholes cho 1 CW."""
    today_str = as_of_date or date.today().strftime("%Y-%m-%d")
    today_dt  = pd.to_datetime(today_str)

    K_raw = str(cw_info.get("gia_thuc_hien", "0"))
    K = float(re.sub(r"[^\d.]", "", K_raw) or 0)
    if K <= 0:
        return {"error": "Giá thực hiện không hợp lệ"}

    ratio_raw = str(cw_info.get("ty_le_chuyen_doi", "1"))
    try:
        n = float(ratio_raw.split(":")[0].replace(",", "."))
    except Exception:
        n = 1.0
    if n <= 0:
        n = 1.0

    maturity_raw = str(cw_info.get("ngay_dao_han", ""))
    try:
        maturity_dt = pd.to_datetime(maturity_raw, dayfirst=True, errors="raise")
    except Exception:
        return {"error": f"Ngày đáo hạn không hợp lệ: {maturity_raw}"}

    T_days = (maturity_dt - today_dt).days
    T = max(T_days, 0) / 365.0

    df_u = ohlcv_underlying.copy()
    if not isinstance(df_u.index, pd.DatetimeIndex):
        tcol = next((c for c in ["time", "date"] if c in df_u.columns), None)
        if tcol:
            df_u = df_u.set_index(pd.to_datetime(df_u[tcol], dayfirst=True, errors="coerce"))
    df_u = df_u.sort_index()
    df_u_filtered = df_u[df_u.index <= today_dt]
    if df_u_filtered.empty:
        return {"error": "Không có dữ liệu giá CK cơ sở"}
    S = float(df_u_filtered["close"].iloc[-1])
    if S < 1000:
        S *= 1000

    if risk_free_rate is None:
        r = get_risk_free_rate(today_str)
    else:
        r = risk_free_rate

    try:
        sigma = calc_sigma(ohlcv_underlying, window=252, as_of_date=today_str)
    except ValueError as e:
        sigma = 0.35
        print(f"   WARN sigma fallback 0.35: {e}")

    bs = bs_call(S=S, K=K, T=T, r=r, sigma=sigma)
    cw_bs_price = bs["price"] / n

    if   S > K * 1.02: moneyness = "ITM"
    elif S < K * 0.98: moneyness = "OTM"
    else:              moneyness = "ATM"

    eff_gearing = round((S / (cw_bs_price * n)) * bs["delta"], 2) if cw_bs_price > 0 else 0

    return {
        "S":           round(S, 0),
        "K":           round(K, 0),
        "T_days":      T_days,
        "T_years":     round(T, 4),
        "r_pct":       round(r * 100, 3),
        "sigma":       sigma,
        "sigma_pct":   round(sigma * 100, 2),
        "n":           n,
        "moneyness":   moneyness,
        "bs_price_call":  round(cw_bs_price, 2),
        "delta":          bs["delta"],
        "gamma":          bs["gamma"],
        "theta":          bs["theta"],
        "vega":           bs["vega"],
        "eff_gearing":    eff_gearing,
    }


# ══════════════════════════════════════════════════════════════════
# 5. BATCH: TÍNH BS CHO TOÀN BỘ CW ACTIVE TRONG PIPELINE
# ══════════════════════════════════════════════════════════════════

def step_bs_selfcalc(
    df_vietstock:       pd.DataFrame,
    valid_tickers:      list,
    underlying_ohlcv:   dict,
    as_of_date:         Optional[str] = None,
) -> dict:
    """Tính Black-Scholes cho tất cả CW active. r được fetch 1 lần duy nhất cho cả batch."""
    print("\n" + "=" * 60)
    print("BUOC BS (tự tính) — Black-Scholes từ OHLCV + HNX 10Y (vnbond → Playwright → cache → VBMA → fallback)")
    print("=" * 60)

    today_str = as_of_date or date.today().strftime("%Y-%m-%d")

    r = get_risk_free_rate(today_str)
    print(f"   r (dùng cho toàn bộ batch) = {r*100:.4f}%")

    df_active = df_vietstock[df_vietstock["ma_cw"].isin(valid_tickers)].copy()
    today_ts  = pd.Timestamp(today_str)
    if "ngay_gd_cuoi_cung" in df_active.columns:
        ldt = pd.to_datetime(df_active["ngay_gd_cuoi_cung"], dayfirst=True, errors="coerce")
        df_active = df_active[ldt >= today_ts]

    results = {}
    ok = fail = skip = 0
    total = len(df_active)

    for _, row in df_active.iterrows():
        ticker    = str(row.get("ma_cw", ""))
        und_sym   = str(row.get("ck_co_so", "")).strip()
        ohlcv_und = underlying_ohlcv.get(und_sym)

        if ohlcv_und is None or (hasattr(ohlcv_und, "empty") and ohlcv_und.empty):
            skip += 1
            continue

        try:
            res = calc_bs_for_cw(
                cw_info           = row.to_dict(),
                ohlcv_underlying  = ohlcv_und,
                risk_free_rate    = r,
                as_of_date        = today_str,
            )
            if "error" in res:
                fail += 1
                if fail <= 5:
                    print(f"   FAIL {ticker}: {res['error']}")
            else:
                results[ticker] = res
                ok += 1
                if ok <= 5 or ok % 50 == 0:
                    print(f"   [{ok:>4}/{total}] {ticker:12} "
                          f"S={res['S']:>8,.0f}  K={res['K']:>8,.0f}  "
                          f"T={res['T_days']}d  σ={res['sigma_pct']:.1f}%  "
                          f"BS={res['bs_price_call']:>7.2f}  Δ={res['delta']:.3f}  "
                          f"{res['moneyness']}")
        except Exception as e:
            fail += 1
            if fail <= 5:
                print(f"   FAIL {ticker}: {e}")

    print(f"\n   OK={ok}  FAIL={fail}  SKIP(no underlying)={skip}")
    return results


# ══════════════════════════════════════════════════════════════════
# 6. BACKTESTING: CHUỖI BS THEO NGÀY (cho drill-down chart)
# ══════════════════════════════════════════════════════════════════

def calc_bs_history(
    cw_info:            dict,
    ohlcv_underlying:   pd.DataFrame,
    ohlcv_cw:           pd.DataFrame,
    risk_free_rate_series: Optional[pd.Series] = None,
) -> list:
    """Tính chuỗi giá BS theo từng ngày giao dịch — dùng cho biểu đồ Backtesting."""
    K_raw = str(cw_info.get("gia_thuc_hien", "0"))
    K     = float(re.sub(r"[^\d.]", "", K_raw) or 0)
    n_raw = str(cw_info.get("ty_le_chuyen_doi", "1"))
    n     = float(n_raw.split(":")[0].replace(",", ".")) if n_raw else 1.0
    mat_raw = str(cw_info.get("ngay_dao_han", ""))
    try:
        maturity_dt = pd.to_datetime(mat_raw, dayfirst=True)
    except Exception:
        return []

    df_u = ohlcv_underlying.copy()
    if not isinstance(df_u.index, pd.DatetimeIndex):
        tcol = next((c for c in ["time", "date"] if c in df_u.columns), None)
        if tcol:
            df_u = df_u.set_index(pd.to_datetime(df_u[tcol], dayfirst=True, errors="coerce"))
    df_u = df_u.sort_index()
    close_u = df_u["close"].dropna()
    if close_u.median() < 1000:
        close_u = close_u * 1000

    log_ret      = np.log(close_u / close_u.shift(1))
    sigma_series = log_ret.rolling(252, min_periods=20).std() * math.sqrt(252)

    r_default = 0.0453  # fallback nếu không truyền risk_free_rate_series

    history = []
    for dt, S in close_u.items():
        if pd.isna(S) or S <= 0:
            continue

        T_days = (maturity_dt - dt).days
        if T_days < 0:
            continue
        T = T_days / 365.0

        sigma = float(sigma_series.get(dt, np.nan))
        if np.isnan(sigma) or sigma <= 0:
            continue

        if risk_free_rate_series is not None and dt in risk_free_rate_series.index:
            r = float(risk_free_rate_series[dt]) / 100
        else:
            r = r_default

        bs = bs_call(S=S, K=K, T=T, r=r, sigma=sigma)
        cw_bs = bs["price"] / n

        history.append({
            "date":     dt.strftime("%d/%m/%Y"),
            "S":        round(S, 0),
            "sigma":    round(sigma, 4),
            "T_days":   T_days,
            "r_pct":    round(r * 100, 3),
            "bs_call":  round(cw_bs, 2),
            "delta":    bs["delta"],
        })

    return sorted(history, key=lambda x: x["date"])


# ══════════════════════════════════════════════════════════════════
# 7. QUICK TEST
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("=== Test lấy r (vnbond → Playwright → cache → VBMA → fallback) ===\n")
    r_today = get_risk_free_rate()
    print(f"\nr sử dụng hôm nay: {r_today*100:.4f}%\n")

    print("=== Test BS với CSTB2604 (15/07/2026) ===\n")
    bs = bs_call(S=69800, K=60000, T=103/365, r=r_today, sigma=0.3954)
    cw_price = bs["price"] / 5

    print(f"Giá CK cơ sở (S)  : 69,800 VND")
    print(f"Giá thực hiện (K)  : 60,000 VND")
    print(f"Thời gian (T)      : 103 ngày = {103/365:.4f} năm")
    print(f"Lãi suất (r)       : {r_today*100:.4f}% (10Y — xem log phía trên để biết nguồn)")
    print(f"Volatility (σ)     : 39.54%")
    print(f"Tỷ lệ chuyển đổi  : 5:1")
    print()
    print(f"─── Kết quả BS ───")
    print(f"Giá CW lý thuyết   : {cw_price:,.2f} VND")
    print(f"Delta (Δ)          : {bs['delta']:.4f}")
    print(f"Gamma (Γ)          : {bs['gamma']:.6f}")
    print(f"Theta (Θ)          : {bs['theta']:.2f} VND/ngày")
    print(f"Vega               : {bs['vega']:.2f} VND per 1% vol")
    print(f"d1                 : {bs['d1']:.4f}")
    print(f"d2                 : {bs['d2']:.4f}")
