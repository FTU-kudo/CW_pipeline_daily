"""
CW Pipeline – YSVN
Bước 1: Scrape thông tin CW từ Vietstock (2301 → nay)
Bước 2: Tải OHLCV từ vnstock (KBS)
Bước 3: Lọc CW có ngày GD cuối cùng >= 02/01/2024
Bước 4: Xuất Excel 3 sheet vào /output
"""

import os
import re
import time
import threading
import requests
import pandas as pd
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ══════════════════════════════════════════════════════════════════
# CẤU HÌNH
# ══════════════════════════════════════════════════════════════════
BASE_STOCKS = [
    "CACB", "CDGC", "CFPT", "CHDB", "CHPG",
    "CLPB", "CMBB", "CMSN", "CMWG", "CSHB",
    "CSSB", "CSTB", "CTCB", "CTPB", "CVHM",
    "CVIB", "CVIC", "CVJC", "CVNM", "CVPB",
    "CVRE", "CPOW", "CBVH", "CBCM", "CBSR",
]
YEARS        = ["23", "24", "25", "26"]
MAX_ISSUANCE = 50
MAX_WORKERS  = 10
TIMEOUT      = 12
DELAY        = 0.1

OHLCV_START_DATE = "01/01/2023"
FILTER_DATE      = date(2024, 1, 2)

MAX_RETRIES   = 5
RETRY_DELAY   = 5.0
REQUEST_DELAY = 1.5

today_str   = date.today().strftime("%Y%m%d")
OUTPUT_FILE = f"output/CW_Pipeline_{today_str}.xlsx"

# ══════════════════════════════════════════════════════════════════
# BƯỚC 1 – SCRAPE VIETSTOCK
# ══════════════════════════════════════════════════════════════════
BASE_URL = "https://finance.vietstock.vn"
HEADERS  = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9",
    "Referer": f"{BASE_URL}/chung-khoan-phai-sinh/chung-quyen.htm",
}

_ALL_TABLE_LABELS = sorted([
    "Tổ chức phát hành CKCS", "Tổ chức phát hành CW",
    "Phương thức thực hiện quyền", "Ngày giao dịch cuối cùng",
    "Ngày giao dịch đầu tiên", "Khối lượng Niêm yết",
    "Khối lượng lưu hành", "Loại chứng quyền", "Kiểu thực hiện",
    "TLCĐ điều chỉnh", "Giá TH điều chỉnh", "Tỷ lệ chuyển đổi",
    "Ngày phát hành", "Ngày niêm yết", "Ngày đáo hạn",
    "Giá phát hành", "Giá thực hiện", "CK cơ sở", "Thời hạn", "Tài liệu",
], key=len, reverse=True)

_LABEL_SPLIT_RE = re.compile(
    r'(' + '|'.join(re.escape(l) for l in _ALL_TABLE_LABELS) + r')\s*:',
    re.UNICODE
)

_thread_local = threading.local()

def get_session():
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        s.headers.update(HEADERS)
        _thread_local.session = s
    return _thread_local.session

def clean_cell(raw):
    if not raw:
        return raw
    raw = raw.strip()
    m = _LABEL_SPLIT_RE.search(raw)
    if m and m.start() > 0:
        return raw[:m.start()].strip()
    return raw

def parse_number(text):
    if not text or str(text).strip() in ("-", ""):
        return None
    token = str(text).strip().split()[0].replace(",", "")
    try:
        return int(token)
    except ValueError:
        try:
            return float(token)
        except ValueError:
            return None

def parse_basic_table(soup):
    data = {}
    table = soup.select_one(".short-doc table")
    if not table:
        return data
    basic_map = {
        "CK cơ sở":                    "ck_co_so",
        "Tổ chức phát hành CKCS":      "to_chuc_ph_ckcs",
        "Tổ chức phát hành CW":        "to_chuc_ph_cw",
        "Loại chứng quyền":            "loai_cw",
        "Kiểu thực hiện":              "kieu_thuc_hien",
        "Phương thức thực hiện quyền": "phuong_thuc",
        "Thời hạn":                    "thoi_han",
        "Ngày phát hành":              "ngay_phat_hanh",
        "Ngày niêm yết":               "ngay_niem_yet",
        "Ngày giao dịch đầu tiên":     "ngay_gd_dau_tien",
        "Ngày giao dịch cuối cùng":    "ngay_gd_cuoi_cung",
        "Ngày đáo hạn":                "ngay_dao_han",
        "Tỷ lệ chuyển đổi":           "ty_le_chuyen_doi",
        "TLCĐ điều chỉnh":            "tlcd_dieu_chinh",
        "Giá phát hành":               "gia_phat_hanh",
        "Giá thực hiện":               "gia_thuc_hien",
        "Giá TH điều chỉnh":          "gia_th_dieu_chinh",
        "Khối lượng Niêm yết":         "kl_niem_yet",
        "Khối lượng lưu hành":         "kl_luu_hanh",
    }
    for tr in table.find_all("tr"):
        tds = tr.find_all("td", limit=2)
        if len(tds) < 2:
            continue
        b_tag = tds[0].find("b")
        label = (b_tag.get_text(strip=True) if b_tag
                 else tds[0].get_text(strip=True)).replace(":", "").strip()
        raw_val   = tds[1].get_text(" ", strip=True)
        clean_val = clean_cell(raw_val)
        for key, col_name in basic_map.items():
            if key in label:
                data[col_name] = clean_val
                break
    return data

def get_cw_detail(code):
    url    = f"{BASE_URL}/chung-khoan-phai-sinh/{code}/cw-tong-quan.htm"
    result = {"ma_cw": code, "status": "unknown"}
    try:
        resp = get_session().get(url, timeout=TIMEOUT, allow_redirects=True)
    except requests.RequestException as e:
        result["status"] = "error"
        result["loi"]    = str(e)[:120]
        return result
    if resp.status_code == 404:
        result["status"] = "not_found"
        return result
    if resp.status_code != 200:
        result["status"] = f"http_{resp.status_code}"
        return result
    soup = BeautifulSoup(resp.text, "html.parser")
    if not soup.select_one("h1.h1-title"):
        result["status"] = "not_found"
        return result
    result["status"] = "found"
    price_el = soup.select_one("#stockprice .price")
    result["gia_hien_tai"] = parse_number(price_el.get_text(strip=True)) if price_el else None
    for sel, key, is_num in [
        ("#basestock",        "gia_ck_co_so", True),
        ("#moneyness",        "s_x",          True),
        ("#breakeven",        "hoa_von",       True),
        ("#moneyness-status", "trang_thai_cw", False),
    ]:
        el = soup.select_one(sel)
        if el:
            val = el.get_text(strip=True)
            result[key] = parse_number(val) if is_num else val
    result.update(parse_basic_table(soup))
    return result

def step1_scrape_vietstock():
    print("\n" + "=" * 60)
    print("🕷️  BƯỚC 1 – Scrape Vietstock")
    print("=" * 60)

    codes = [
        f"{stock}{yy}{n:02d}"
        for stock in BASE_STOCKS
        for yy in YEARS
        for n in range(1, MAX_ISSUANCE + 1)
    ]
    total      = len(codes)
    print(f"📋 Tổng mã cần kiểm tra: {total:,}")

    raw_results = {}
    print_lock  = threading.Lock()
    start_time  = time.time()

    def crawl_one(code):
        time.sleep(DELAY)
        return code, get_cw_detail(code)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(crawl_one, c): c for c in codes}
        for future in as_completed(futures):
            code, result = future.result()
            raw_results[code] = result
            done = len(raw_results)
            if result.get("status") == "found":
                elapsed = time.time() - start_time
                speed   = done / elapsed if elapsed else 0
                eta     = (total - done) / speed if speed else 0
                with print_lock:
                    print(
                        f"  [{done:>4}/{total}] ✅ {code}"
                        f"  HH: {result.get('ngay_dao_han', ''):12}"
                        f"  ⚡{speed:.1f}/s  ETA:{eta:.0f}s"
                    )
            elif done % 100 == 0:
                elapsed = time.time() - start_time
                speed   = done / elapsed if elapsed else 0
                eta     = (total - done) / speed if speed else 0
                with print_lock:
                    print(f"  [{done:>4}/{total}] ... quét tiếp  ⚡{speed:.1f}/s  ETA:{eta:.0f}s")

    records = [
        raw_results[c] for c in codes
        if raw_results.get(c, {}).get("status") == "found"
    ]
    df = pd.DataFrame(records)
    df.drop(columns=[c for c in ["status", "loi"] if c in df.columns], inplace=True)

    elapsed = time.time() - start_time
    print(f"\n⏱  Bước 1 xong: {elapsed:.0f}s | Tìm thấy: {len(df):,} mã")
    return df


# ══════════════════════════════════════════════════════════════════
# BƯỚC 2 – TẢI OHLCV TỪ VNSTOCK
# ══════════════════════════════════════════════════════════════════
def step2_fetch_ohlcv(df_vietstock):
    from vnstock import Quote, register_user

    api_key = os.environ.get("VNSTOCK_API", "")
    if api_key:
        register_user(api_key)
        print("✅ Đã đăng ký Vnstock API key.")
    else:
        print("⚠️  Không tìm thấy VNSTOCK_API – chạy không có key.")

    print("\n" + "=" * 60)
    print("📈 BƯỚC 2 – Tải OHLCV từ vnstock (KBS)")
    print("=" * 60)

    tickers       = df_vietstock["ma_cw"].dropna().unique().tolist()
    total_tickers = len(tickers)
    today_api     = date.today().strftime("%d/%m/%Y")
    print(f"   Số mã: {total_tickers}  |  Từ: {OHLCV_START_DATE}  |  Đến: {today_api}")

    all_ohlcv    = []
    failed_list  = []
    skipped_list = []

    for i, symbol in enumerate(tickers, start=1):
        success = False
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                quote  = Quote(symbol=symbol, source="KBS")
                df_raw = quote.history(
                    start=OHLCV_START_DATE,
                    end=today_api,
                    interval="d"
                )
                if df_raw is None or df_raw.empty:
                    skipped_list.append(symbol)
                    print(f"  [{i:>4}/{total_tickers}] ⚠️  {symbol}  – không có dữ liệu")
                    success = True
                    break
                df_raw["Ticker"] = symbol
                all_ohlcv.append(df_raw)
                print(f"  [{i:>4}/{total_tickers}] ✅ {symbol}  ({len(df_raw)} phiên)")
                success = True
                break
            except Exception as e:
                err_msg       = str(e)
                is_rate_limit = any(kw in err_msg.lower() for kw in [
                    "rate limit", "429", "too many requests", "quota", "throttle"
                ])
                wait = RETRY_DELAY * attempt if is_rate_limit else RETRY_DELAY
                tag  = "🚦 rate limit" if is_rate_limit else "❌ lỗi"
                print(
                    f"  [{i:>4}/{total_tickers}] {tag} {symbol} "
                    f"(lần {attempt}/{MAX_RETRIES}) → chờ {wait:.0f}s | {err_msg[:60]}"
                )
                if attempt < MAX_RETRIES:
                    time.sleep(wait)

        if not success:
            failed_list.append(symbol)
            print(f"  [{i:>4}/{total_tickers}] 💀 {symbol}  – bỏ qua sau {MAX_RETRIES} lần")

        time.sleep(REQUEST_DELAY)

    print(f"\n   Thành công: {len(all_ohlcv)}  |  Rỗng: {len(skipped_list)}  |  Thất bại: {len(failed_list)}")
    if failed_list:
        print(f"   Mã thất bại: {failed_list}")

    if not all_ohlcv:
        raise RuntimeError("❌ Không lấy được dữ liệu OHLCV nào.")

    return pd.concat(all_ohlcv, ignore_index=True)


# ══════════════════════════════════════════════════════════════════
# BƯỚC 3 – LỌC + SORT THEO NGÀY
# ══════════════════════════════════════════════════════════════════
def step3_filter_and_sort(df_ohlcv_full):
    print("\n" + "=" * 60)
    print("🔍 BƯỚC 3 – Lọc & sort theo ngày")
    print("=" * 60)

    df_ohlcv_full["time_dt"] = pd.to_datetime(
        df_ohlcv_full["time"], dayfirst=True, errors="coerce"
    )

    last_trading_day = (
        df_ohlcv_full.groupby("Ticker")["time_dt"]
        .max()
        .reset_index()
        .rename(columns={"time_dt": "last_trading_date"})
    )

    filter_ts       = pd.Timestamp(FILTER_DATE)
    valid_tickers   = last_trading_day.loc[
        last_trading_day["last_trading_date"] >= filter_ts, "Ticker"
    ].tolist()
    removed_tickers = last_trading_day.loc[
        last_trading_day["last_trading_date"] < filter_ts, "Ticker"
    ].tolist()

    print(f"   Tổng mã có OHLCV  : {len(last_trading_day)}")
    print(f"   ✅ Mã đạt tiêu chí : {len(valid_tickers)}")
    print(f"   ❌ Mã bị loại      : {len(removed_tickers)}")

    # Lọc + chỉ lấy phiên từ 02/01/2024
    df_filtered = df_ohlcv_full[
        (df_ohlcv_full["Ticker"].isin(valid_tickers)) &
        (df_ohlcv_full["time_dt"] >= filter_ts)
    ].copy()

    # Sort: ngày tăng dần → Ticker A→Z
    df_filtered.sort_values(["time_dt", "Ticker"], ascending=[True, True], inplace=True)
    df_filtered.reset_index(drop=True, inplace=True)

    df_filtered["time"] = df_filtered["time_dt"].dt.strftime("%d/%m/%Y")
    df_filtered.drop(columns=["time_dt"], inplace=True)

    col_order = ["time", "open", "high", "low", "close", "volume", "Ticker"]
    col_order = [c for c in col_order if c in df_filtered.columns]
    df_filtered = df_filtered[col_order]

    print(f"   Tổng phiên GD giữ lại : {len(df_filtered):,}")
    print(f"   Số ngày giao dịch     : {df_filtered['time'].nunique()}")
    print(f"   Số CW hợp lệ          : {df_filtered['Ticker'].nunique()}")

    return df_filtered, valid_tickers, last_trading_day


# ══════════════════════════════════════════════════════════════════
# BƯỚC 4 – XUẤT EXCEL
# ══════════════════════════════════════════════════════════════════
def format_sheet(ws, header_color="1F4E79"):
    header_fill  = PatternFill("solid", fgColor=header_color)
    header_font  = Font(bold=True, color="FFFFFF", size=10)
    center_align = Alignment(horizontal="center", vertical="center")
    thin_border  = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"),  bottom=Side(style="thin")
    )
    for cell in ws[1]:
        cell.fill      = header_fill
        cell.font      = header_font
        cell.alignment = center_align
        cell.border    = thin_border
    ws.freeze_panes = "A2"
    for col_cells in ws.columns:
        max_len = max(
            (len(str(c.value)) if c.value is not None else 0)
            for c in col_cells
        )
        ws.column_dimensions[get_column_letter(col_cells[0].column)].width = min(max_len + 2, 30)

def step4_export_excel(df_ohlcv_filtered, df_vietstock, valid_tickers, last_trading_day):
    print("\n" + "=" * 60)
    print("💾 BƯỚC 4 – Xuất Excel")
    print("=" * 60)

    column_rename = {
        "ma_cw":             "Ticker",
        "ck_co_so":          "Underlying Asset",
        "to_chuc_ph_cw":     "Issuer",
        "loai_cw":           "Type",
        "kieu_thuc_hien":    "Exercise Style",
        "thoi_han":          "Term",
        "ngay_phat_hanh":    "Issuance Date",
        "ngay_niem_yet":     "Listing Date",
        "ngay_gd_dau_tien":  "First Trading Date",
        "ngay_gd_cuoi_cung": "Last Trading Date",
        "ngay_dao_han":      "Maturity Date",
        "ty_le_chuyen_doi":  "Conversion Ratio",
        "tlcd_dieu_chinh":   "Adj. Conversion Ratio",
        "gia_thuc_hien":     "Exercise Price",
        "gia_th_dieu_chinh": "Adj. Exercise Price",
        "gia_phat_hanh":     "Issuance Price",
        "kl_niem_yet":       "Listed Volume",
        "kl_luu_hanh":       "Outstanding Volume",
        "gia_hien_tai":      "Current Price",
        "trang_thai_cw":     "Moneyness",
        "s_x":               "S/X",
        "hoa_von":           "Break-even",
    }

    priority_cols = [
        "ma_cw", "ck_co_so", "to_chuc_ph_cw",
        "ngay_gd_dau_tien", "ngay_gd_cuoi_cung", "ngay_dao_han",
        "ty_le_chuyen_doi", "tlcd_dieu_chinh",
        "gia_thuc_hien", "gia_th_dieu_chinh",
        "kl_niem_yet", "kl_luu_hanh",
        "loai_cw", "kieu_thuc_hien", "thoi_han",
        "ngay_phat_hanh", "ngay_niem_yet",
        "gia_phat_hanh", "gia_hien_tai", "trang_thai_cw",
    ]

    df_info = df_vietstock[df_vietstock["ma_cw"].isin(valid_tickers)].copy()
    p_cols  = [c for c in priority_cols if c in df_info.columns]
    rest    = [c for c in df_info.columns if c not in p_cols]
    df_info = df_info[p_cols + rest]
    df_info.rename(columns=column_rename, inplace=True)
    df_info = df_info.merge(
        last_trading_day.rename(columns={"Ticker": "Ticker"}),
        left_on="Ticker", right_on="Ticker", how="left"
    )
    today_ts = pd.Timestamp(date.today())
    df_info_active  = df_info[df_info["last_trading_date"] >= today_ts].drop(columns=["last_trading_date"])
    df_info_expired = df_info[df_info["last_trading_date"] <  today_ts].drop(columns=["last_trading_date"])
    df_info_active.sort_values("Ticker",  inplace=True)
    df_info_expired.sort_values("Ticker", inplace=True)

    os.makedirs("output", exist_ok=True)
    with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
        df_ohlcv_filtered.to_excel(writer, sheet_name="OHLCV",           index=False)
        df_info_active.to_excel(   writer, sheet_name="CW_Info_Active",  index=False)
        df_info_expired.to_excel(  writer, sheet_name="CW_Info_Expired", index=False)
        wb = writer.book
        format_sheet(wb["OHLCV"],           header_color="1F4E79")
        format_sheet(wb["CW_Info_Active"],  header_color="375623")
        format_sheet(wb["CW_Info_Expired"], header_color="843C0C")

    print(f"✅ Đã lưu: {OUTPUT_FILE}")
    print(f"   Sheet OHLCV           : {len(df_ohlcv_filtered):,} dòng")
    print(f"   Sheet CW_Info_Active  : {len(df_info_active)} mã")
    print(f"   Sheet CW_Info_Expired : {len(df_info_expired)} mã")


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    start_all = time.time()

    df_vietstock                              = step1_scrape_vietstock()
    df_ohlcv_full                             = step2_fetch_ohlcv(df_vietstock)
    df_ohlcv_filtered, valid_tickers, ltd     = step3_filter_and_sort(df_ohlcv_full)
    step4_export_excel(df_ohlcv_filtered, df_vietstock, valid_tickers, ltd)

    total_time = time.time() - start_all
    print(f"\n🏁 Pipeline hoàn tất: {total_time/60:.1f} phút")
    print(f"   File: {OUTPUT_FILE}")
