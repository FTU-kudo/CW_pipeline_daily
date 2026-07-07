"""
CW Pipeline YSVN - Incremental Mode
Lan dau (chua co cache): scrape toan bo Vietstock + tai toan bo OHLCV
Cac lan sau (co cache):  chi scrape ma CW moi + tai them phien GD moi nhat

Cache:
  output/cache/vietstock.parquet
  output/cache/ohlcv.parquet

Output:
  output/cw_master.xlsx  (ghi de moi ngay)
  docs/data.json         (cho GitHub Pages dashboard)
"""

import os, re, time, threading, requests, pandas as pd, json
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date, timedelta
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ══════════════════════════════════════════════════════════════════
# CAU HINH
# ══════════════════════════════════════════════════════════════════
BASE_STOCKS = [
    "CACB","CDGC","CFPT","CHDB","CHPG","CLPB","CMBB","CMSN","CMWG","CSHB",
    "CSSB","CSTB","CTCB","CTPB","CVHM","CVIB","CVIC","CVJC","CVNM","CVPB",
    "CVRE","CPOW","CBVH","CBCM","CBSR",
]
YEARS        = ["23","24","25","26"]
MAX_ISSUANCE = 50
MAX_WORKERS  = 10
TIMEOUT      = 12
DELAY        = 0.1

OHLCV_START_DATE = "2023-01-01"   # YYYY-MM-DD (dung cho API moi)
FILTER_DATE      = date(2024, 1, 2)
MAX_RETRIES      = 5
RETRY_DELAY      = 5.0
REQUEST_DELAY    = 1.5

CACHE_DIR       = "output/cache"
VIETSTOCK_CACHE = f"{CACHE_DIR}/vietstock.parquet"
OHLCV_CACHE     = f"{CACHE_DIR}/ohlcv.parquet"
OUTPUT_FILE     = "output/cw_master.xlsx"

# ══════════════════════════════════════════════════════════════════
# CACHE HELPERS
# ══════════════════════════════════════════════════════════════════
def load_cache(path):
    if os.path.exists(path):
        df = pd.read_parquet(path)
        print(f"   Doc cache: {path}  ({len(df):,} dong)")
        return df
    print(f"   Chua co cache: {path}")
    return None

def save_cache(df, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, index=False)
    print(f"   Luu cache: {path}  ({len(df):,} dong)")

# ══════════════════════════════════════════════════════════════════
# VIETSTOCK SCRAPER
# ══════════════════════════════════════════════════════════════════
BASE_URL = "https://finance.vietstock.vn"
HEADERS  = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9",
    "Referer": f"{BASE_URL}/chung-khoan-phai-sinh/chung-quyen.htm",
}

_ALL_TABLE_LABELS = sorted([
    "To chuc phat hanh CKCS","To chuc phat hanh CW",
    "Ngay giao dich cuoi cung","Ngay giao dich dau tien",
    "Khoi luong Niem yet","Khoi luong luu hanh",
    "Loai chung quyen","Kieu thuc hien",
    "TLCD dieu chinh","Gia TH dieu chinh","Ty le chuyen doi",
    "Ngay phat hanh","Ngay niem yet","Ngay dao han",
    "Gia phat hanh","Gia thuc hien","CK co so","Thoi han","Tai lieu",
    "To chuc phat hanh CKCS","To chuc phat hanh CW",
    "Phuong thuc thuc hien quyen","Ngay giao dich cuoi cung",
    "Ngay giao dich dau tien","Khoi luong Niem yet",
    "Khoi luong luu hanh","Loai chung quyen","Kieu thuc hien",
    "TLCD dieu chinh","Gia TH dieu chinh","Ty le chuyen doi",
    "Ngay phat hanh","Ngay niem yet","Ngay dao han",
    "Gia phat hanh","Gia thuc hien","CK co so","Thoi han","Tai lieu",
    # UTF-8
    "Tổ chức phát hành CKCS","Tổ chức phát hành CW",
    "Phương thức thực hiện quyền","Ngày giao dịch cuối cùng",
    "Ngày giao dịch đầu tiên","Khối lượng Niêm yết",
    "Khối lượng lưu hành","Loại chứng quyền","Kiểu thực hiện",
    "TLCĐ điều chỉnh","Giá TH điều chỉnh","Tỷ lệ chuyển đổi",
    "Ngày phát hành","Ngày niêm yết","Ngày đáo hạn",
    "Giá phát hành","Giá thực hiện","CK cơ sở","Thời hạn","Tài liệu",
], key=len, reverse=True)

_LABEL_SPLIT_RE = re.compile(
    r'('+  '|'.join(re.escape(l) for l in _ALL_TABLE_LABELS) + r')\s*:',
    re.UNICODE
)
_thread_local = threading.local()

def get_session():
    if not hasattr(_thread_local,"session"):
        s = requests.Session(); s.headers.update(HEADERS)
        _thread_local.session = s
    return _thread_local.session

def clean_cell(raw):
    if not raw: return raw
    raw = raw.strip()
    m = _LABEL_SPLIT_RE.search(raw)
    return raw[:m.start()].strip() if m and m.start()>0 else raw

def parse_number(text):
    if not text or str(text).strip() in ("-",""): return None
    token = str(text).strip().split()[0].replace(",","")
    try: return int(token)
    except ValueError:
        try: return float(token)
        except: return None

def parse_basic_table(soup):
    data={}; table=soup.select_one(".short-doc table")
    if not table: return data
    basic_map = {
        "CK cơ sở":"ck_co_so","Tổ chức phát hành CKCS":"to_chuc_ph_ckcs",
        "Tổ chức phát hành CW":"to_chuc_ph_cw","Loại chứng quyền":"loai_cw",
        "Kiểu thực hiện":"kieu_thuc_hien","Phương thức thực hiện quyền":"phuong_thuc",
        "Thời hạn":"thoi_han","Ngày phát hành":"ngay_phat_hanh",
        "Ngày niêm yết":"ngay_niem_yet","Ngày giao dịch đầu tiên":"ngay_gd_dau_tien",
        "Ngày giao dịch cuối cùng":"ngay_gd_cuoi_cung","Ngày đáo hạn":"ngay_dao_han",
        "Tỷ lệ chuyển đổi":"ty_le_chuyen_doi","TLCĐ điều chỉnh":"tlcd_dieu_chinh",
        "Giá phát hành":"gia_phat_hanh","Giá thực hiện":"gia_thuc_hien",
        "Giá TH điều chỉnh":"gia_th_dieu_chinh","Khối lượng Niêm yết":"kl_niem_yet",
        "Khối lượng lưu hành":"kl_luu_hanh",
    }
    for tr in table.find_all("tr"):
        tds=tr.find_all("td",limit=2)
        if len(tds)<2: continue
        b=tds[0].find("b")
        label=(b.get_text(strip=True) if b else tds[0].get_text(strip=True)).replace(":","").strip()
        val=clean_cell(tds[1].get_text(" ",strip=True))
        for key,col in basic_map.items():
            if key in label: data[col]=val; break
    return data

def get_cw_detail(code):
    url=f"{BASE_URL}/chung-khoan-phai-sinh/{code}/cw-tong-quan.htm"
    res={"ma_cw":code,"status":"unknown"}
    try: resp=get_session().get(url,timeout=TIMEOUT,allow_redirects=True)
    except requests.RequestException as e:
        res["status"]="error"; res["loi"]=str(e)[:120]; return res
    if resp.status_code==404: res["status"]="not_found"; return res
    if resp.status_code!=200: res["status"]=f"http_{resp.status_code}"; return res
    soup=BeautifulSoup(resp.text,"html.parser")
    if not soup.select_one("h1.h1-title"): res["status"]="not_found"; return res
    res["status"]="found"
    pe=soup.select_one("#stockprice .price")
    res["gia_hien_tai"]=parse_number(pe.get_text(strip=True)) if pe else None
    for sel,key,is_num in [
        ("#basestock","gia_ck_co_so",True),("#moneyness","s_x",True),
        ("#breakeven","hoa_von",True),("#moneyness-status","trang_thai_cw",False)
    ]:
        el=soup.select_one(sel)
        if el:
            v=el.get_text(strip=True)
            res[key]=parse_number(v) if is_num else v
    res.update(parse_basic_table(soup))
    return res

def scrape_codes(codes, label=""):
    total=len(codes); raw={}; lock=threading.Lock(); t0=time.time()
    def crawl(code):
        time.sleep(DELAY); return code,get_cw_detail(code)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs={ex.submit(crawl,c):c for c in codes}
        for f in as_completed(futs):
            code,result=f.result(); raw[code]=result; done=len(raw)
            if result.get("status")=="found":
                el=time.time()-t0; sp=done/el if el else 0; eta=(total-done)/sp if sp else 0
                with lock:
                    print(f"  [{done:>4}/{total}] OK {code}  HH:{result.get('ngay_dao_han',''):12}  {sp:.1f}/s ETA:{eta:.0f}s")
            elif done%100==0:
                el=time.time()-t0; sp=done/el if el else 0; eta=(total-done)/sp if sp else 0
                with lock: print(f"  [{done:>4}/{total}] ... {label}  {sp:.1f}/s ETA:{eta:.0f}s")
    records=[raw[c] for c in codes if raw.get(c,{}).get("status")=="found"]
    df=pd.DataFrame(records) if records else pd.DataFrame()
    if not df.empty:
        df.drop(columns=[c for c in ["status","loi"] if c in df.columns],inplace=True)
    return df

# ══════════════════════════════════════════════════════════════════
# BUOC 1 - VIETSTOCK (INCREMENTAL)
# ══════════════════════════════════════════════════════════════════
def step1_vietstock():
    print("\n"+"="*60)
    print("BUOC 1 - Vietstock (incremental)")
    print("="*60)
    all_codes=[
        f"{s}{yy}{n:02d}"
        for s in BASE_STOCKS for yy in YEARS for n in range(1,MAX_ISSUANCE+1)
    ]
    df_cache=load_cache(VIETSTOCK_CACHE)
    if df_cache is None:
        print(f"   Full load - {len(all_codes):,} ma")
        df=scrape_codes(all_codes,"full")
        save_cache(df,VIETSTOCK_CACHE); return df
    known=set(df_cache["ma_cw"].tolist())
    new_codes=[c for c in all_codes if c not in known]
    print(f"   Cache co: {len(known)} ma  |  Can kiem tra them: {len(new_codes)}")
    if new_codes:
        df_new=scrape_codes(new_codes,"incremental")
        if not df_new.empty:
            df_merged=pd.concat([df_cache,df_new],ignore_index=True)
            df_merged.drop_duplicates(subset="ma_cw",keep="last",inplace=True)
            print(f"   Them {len(df_new)} ma moi")
            save_cache(df_merged,VIETSTOCK_CACHE); return df_merged
    return df_cache

# ══════════════════════════════════════════════════════════════════
# BUOC 2 - OHLCV (INCREMENTAL) - dung vnstock API moi
# ══════════════════════════════════════════════════════════════════
def _to_ymd(s):
    """Chuyen DD/MM/YYYY hoac YYYY-MM-DD sang YYYY-MM-DD"""
    s = str(s).strip()
    if re.match(r'\d{2}/\d{2}/\d{4}', s):
        d,m,y = s.split("/"); return f"{y}-{m}-{d}"
    return s  # da la YYYY-MM-DD

def _normalise_ohlcv(df, symbol):
    """Chuan hoa DataFrame OHLCV ve dung schema: time(DD/MM/YYYY), open, high, low, close, volume, Ticker"""
    df = df.copy()
    df.columns = [c.lower() for c in df.columns]
    # Doi ten cot time
    for alt in ["date","trading_date","datetime","time"]:
        if alt in df.columns:
            df.rename(columns={alt:"time"}, inplace=True); break
    # Doi ten cot volume
    for alt in ["volume","vol","klgd"]:
        if alt in df.columns and alt != "volume":
            df.rename(columns={alt:"volume"}, inplace=True); break
    # Doi ten cot gia
    for src,dst in [("open","open"),("high","high"),("low","low"),("close","close")]:
        if src not in df.columns:
            for alt in [f"{src}_price",f"gia_{src}"]:
                if alt in df.columns: df.rename(columns={alt:dst},inplace=True); break
    # Chuan hoa cot time sang DD/MM/YYYY
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], errors="coerce").dt.strftime("%d/%m/%Y")
    df["Ticker"] = symbol
    # Chi giu cac cot can thiet
    keep = [c for c in ["time","open","high","low","close","volume","Ticker"] if c in df.columns]
    return df[keep].dropna(subset=["time"])

def fetch_one(symbol, start_str, end_str):
    """
    Tai OHLCV 1 ma CW voi retry.
    start_str/end_str: YYYY-MM-DD hoac DD/MM/YYYY deu duoc.
    Tra ve DataFrame da chuan hoa, DataFrame rong, hoac None (that bai hoan toan).
    """
    start = _to_ymd(start_str)
    end   = _to_ymd(end_str)

    for attempt in range(1, MAX_RETRIES+1):
        try:
            from vnstock.api.quote import Quote
            q  = Quote(symbol=symbol, source="VCI")
            df = q.history(start=start, end=end, interval="1D")

            if df is None or df.empty:
                return pd.DataFrame()

            return _normalise_ohlcv(df, symbol)

        except Exception as e:
            msg = str(e)
            is_rl = any(k in msg.lower() for k in
                        ["rate limit","429","too many","quota","throttle"])
            is_403 = "403" in msg or "forbidden" in msg.lower()
            wait = RETRY_DELAY * attempt if is_rl else RETRY_DELAY

            if is_403 and attempt == 1:
                # Thu fallback sang KBS neu VCI bi 403
                try:
                    from vnstock.api.quote import Quote as Q2
                    q2 = Q2(symbol=symbol, source="KBS")
                    df2 = q2.history(start=start, end=end, interval="1D")
                    if df2 is not None and not df2.empty:
                        return _normalise_ohlcv(df2, symbol)
                except Exception:
                    pass

            tag = "RL" if is_rl else "403" if is_403 else "ERR"
            print(f"      {tag} {symbol} #{attempt} wait {wait:.0f}s | {msg[:60]}")
            if attempt < MAX_RETRIES:
                time.sleep(wait)

    return None  # that bai hoan toan sau MAX_RETRIES

def step2_ohlcv(df_vs):
    print("\n"+"="*60)
    print("BUOC 2 - OHLCV (incremental)")
    print("="*60)

    api_key = os.environ.get("VNSTOCK_API","")
    if api_key:
        try:
            import vnai; vnai.setup_api_key(api_key)
            print("   OK Vnstock API key registered.")
        except Exception as e:
            print(f"   WARN: setup_api_key failed: {e}")
    else:
        print("   WARN: no VNSTOCK_API env var.")

    today     = date.today().strftime("%Y-%m-%d")
    tickers   = df_vs["ma_cw"].dropna().unique().tolist()
    df_cache  = load_cache(OHLCV_CACHE)

        if df_cache is None:
        # ── Full load ────────────────────────────────────────────
        print(f"   Full load - {len(tickers)} ma tu {OHLCV_START_DATE}")
        rows=[]; failed=[]; skipped=[]
        for i,sym in enumerate(tickers,1):
            df_r = fetch_one(sym, OHLCV_START_DATE, today)
            if df_r is None:
                failed.append(sym)
                print(f"  [{i:>4}/{len(tickers)}] FAIL {sym}")
            elif df_r.empty:
                skipped.append(sym)
                print(f"  [{i:>4}/{len(tickers)}] EMPTY {sym}")
            else:
                rows.append(df_r)
                print(f"  [{i:>4}/{len(tickers)}] OK {sym} ({len(df_r)} phien)")
            time.sleep(REQUEST_DELAY)
        df_out = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
        print(f"   OK:{len(rows)}  Empty:{len(skipped)}  Fail:{len(failed)}")
        if failed: print(f"   Failed: {failed}")
        save_cache(df_out, OHLCV_CACHE)
        return df_out
    
    # ── Ensure time is string before incremental processing ──────────────────────
    df_cache["time"] = df_cache["time"].astype(str)
    
    # ── Incremental ──────────────────────────────────────────────
    # Cache co the luu time theo DD/MM/YYYY — chuan hoa sang datetime de tinh last_dt
    df_cache["time_dt"] = pd.to_datetime(df_cache["time"], dayfirst=True, errors="coerce")
  
    last_dt  = df_cache.groupby("Ticker")["time_dt"].max()
    cached   = set(last_dt.index)
    total    = len(tickers)
    new_rows = []; failed = []; skipped = []

    for i,sym in enumerate(tickers,1):
        if sym in cached:
            next_dt  = last_dt[sym] + timedelta(days=1)
            if next_dt.date() > date.today():
                print(f"  [{i:>4}/{total}] SKIP {sym} (cap nhat den {last_dt[sym].strftime('%d/%m/%Y')})")
                continue
            start_str = next_dt.strftime("%Y-%m-%d")
            lbl = f"+tu {next_dt.strftime('%d/%m/%Y')}"
        else:
            start_str = OHLCV_START_DATE
            lbl = "new full"

        df_r = fetch_one(sym, start_str, today)
        if df_r is None:
            failed.append(sym)
            print(f"  [{i:>4}/{total}] FAIL {sym}")
        elif df_r.empty:
            skipped.append(sym)
            print(f"  [{i:>4}/{total}] NO_NEW {sym} ({lbl})")
        else:
            new_rows.append(df_r)
            print(f"  [{i:>4}/{total}] OK {sym} +{len(df_r)} phien ({lbl})")
        time.sleep(REQUEST_DELAY)

    df_cache.drop(columns=["time_dt"], inplace=True)
    if new_rows:
        df_add    = pd.concat(new_rows, ignore_index=True)
        df_merged = pd.concat([df_cache, df_add], ignore_index=True)
        df_merged.drop_duplicates(subset=["time","Ticker"], keep="last", inplace=True)
        print(f"   Them {len(df_add):,} dong moi")
        save_cache(df_merged, OHLCV_CACHE)
        return df_merged
    else:
        print("   Khong co du lieu moi.")
        if failed: print(f"   Failed: {failed}")
        save_cache(df_cache, OHLCV_CACHE)
        return df_cache

# ══════════════════════════════════════════════════════════════════
# BUOC 3 - LOC + SORT
# ══════════════════════════════════════════════════════════════════
def step3_filter(df_full):
    print("\n"+"="*60)
    print("BUOC 3 - Loc & sort")
    print("="*60)
    df_full["time_dt"] = pd.to_datetime(df_full["time"], dayfirst=True, errors="coerce")
    ltd  = df_full.groupby("Ticker")["time_dt"].max().reset_index().rename(columns={"time_dt":"ltd"})
    ts   = pd.Timestamp(FILTER_DATE)
    valid   = ltd.loc[ltd["ltd"]>=ts,"Ticker"].tolist()
    removed = ltd.loc[ltd["ltd"]<ts,"Ticker"].tolist()
    print(f"   Tong ma: {len(ltd)}  |  Hop le: {len(valid)}  |  Loai: {len(removed)}")
    df = df_full[df_full["Ticker"].isin(valid) & (df_full["time_dt"]>=ts)].copy()
    df.sort_values(["time_dt","Ticker"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    df["time"] = df["time_dt"].dt.strftime("%d/%m/%Y")
    df.drop(columns=["time_dt"], inplace=True)
    cols = [c for c in ["time","open","high","low","close","volume","Ticker"] if c in df.columns]
    print(f"   Phien GD: {len(df):,}  |  Ngay: {df['time'].nunique()}  |  CW: {df['Ticker'].nunique()}")
    return df[cols], valid

# ══════════════════════════════════════════════════════════════════
# BUOC 4 - XUAT EXCEL
# ══════════════════════════════════════════════════════════════════
COL_RENAME={
    "ma_cw":"Ticker","ck_co_so":"Underlying Asset","to_chuc_ph_cw":"Issuer",
    "loai_cw":"Type","kieu_thuc_hien":"Exercise Style","thoi_han":"Term",
    "ngay_phat_hanh":"Issuance Date","ngay_niem_yet":"Listing Date",
    "ngay_gd_dau_tien":"First Trading Date","ngay_gd_cuoi_cung":"Last Trading Date",
    "ngay_dao_han":"Maturity Date","ty_le_chuyen_doi":"Conversion Ratio",
    "tlcd_dieu_chinh":"Adj. Conversion Ratio","gia_thuc_hien":"Exercise Price",
    "gia_th_dieu_chinh":"Adj. Exercise Price","gia_phat_hanh":"Issuance Price",
    "kl_niem_yet":"Listed Volume","kl_luu_hanh":"Outstanding Volume",
    "gia_hien_tai":"Current Price","trang_thai_cw":"Moneyness","s_x":"S/X","hoa_von":"Break-even",
}
PRIORITY=["ma_cw","ck_co_so","to_chuc_ph_cw","ngay_gd_dau_tien","ngay_gd_cuoi_cung",
          "ngay_dao_han","ty_le_chuyen_doi","tlcd_dieu_chinh","gia_thuc_hien",
          "gia_th_dieu_chinh","kl_niem_yet","kl_luu_hanh","loai_cw","kieu_thuc_hien",
          "thoi_han","ngay_phat_hanh","ngay_niem_yet","gia_phat_hanh","gia_hien_tai","trang_thai_cw"]

def fmt_sheet(ws, color):
    fill=PatternFill("solid",fgColor=color); font=Font(bold=True,color="FFFFFF",size=10)
    aln=Alignment(horizontal="center",vertical="center")
    brd=Border(left=Side(style="thin"),right=Side(style="thin"),
               top=Side(style="thin"),bottom=Side(style="thin"))
    for c in ws[1]: c.fill=fill; c.font=font; c.alignment=aln; c.border=brd
    ws.freeze_panes="A2"
    for col in ws.columns:
        w=max((len(str(c.value)) if c.value else 0) for c in col)
        ws.column_dimensions[get_column_letter(col[0].column)].width=min(w+2,30)

def step4_excel(df_ohlcv, df_vs, valid_tickers):
    print("\n"+"="*60)
    print("BUOC 4 - Xuat Excel")
    print("="*60)
    df=df_vs[df_vs["ma_cw"].isin(valid_tickers)].copy()
    p=[c for c in PRIORITY if c in df.columns]
    df=df[p+[c for c in df.columns if c not in p]]
    today_ts=pd.Timestamp(date.today())
    df["_ldt"]=pd.to_datetime(df["ngay_gd_cuoi_cung"],dayfirst=True,errors="coerce")
    df.rename(columns=COL_RENAME,inplace=True)
    act=df[df["_ldt"]>=today_ts].drop(columns=["_ldt"]).sort_values("Ticker")
    exp=df[df["_ldt"]< today_ts].drop(columns=["_ldt"]).sort_values("Ticker")
    os.makedirs("output",exist_ok=True)
    with pd.ExcelWriter(OUTPUT_FILE,engine="openpyxl") as w:
        df_ohlcv.to_excel(w,sheet_name="OHLCV",index=False)
        act.to_excel(w,sheet_name="CW_Info_Active",index=False)
        exp.to_excel(w,sheet_name="CW_Info_Expired",index=False)
        wb=w.book
        fmt_sheet(wb["OHLCV"],"1F4E79")
        fmt_sheet(wb["CW_Info_Active"],"375623")
        fmt_sheet(wb["CW_Info_Expired"],"843C0C")
    print(f"OK Saved: {OUTPUT_FILE}")
    print(f"   Updated: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"   OHLCV: {len(df_ohlcv):,} rows | Active: {len(act)} | Expired: {len(exp)}")

# ══════════════════════════════════════════════════════════════════
# BUOC 5 - XUAT data.json CHO GITHUB PAGES DASHBOARD
# ══════════════════════════════════════════════════════════════════
def _parse_ratio(raw):
    try: return float(str(raw).split(":")[0].replace(",","."))
    except: return 1.0

def _parse_exercise(raw):
    try:
        s = re.sub(r"[^\d]","", str(raw))
        return int(s) if s else 0
    except: return 0

def step5_export_json(df_ohlcv_filtered, df_vietstock, valid_tickers):
    print("\n"+"="*60)
    print("BUOC 5 - Xuat data.json cho GitHub Pages")
    print("="*60)

    today_ts = pd.Timestamp(date.today())
    df_info  = df_vietstock[df_vietstock["ma_cw"].isin(valid_tickers)].copy()
    df_info["_last_gd_dt"] = pd.to_datetime(
        df_info["ngay_gd_cuoi_cung"], dayfirst=True, errors="coerce"
    )

    # Index OHLCV theo Ticker de tra cuu nhanh
    ohlcv_idx = {t: grp for t,grp in df_ohlcv_filtered.groupby("Ticker")}

    def calc_metrics(row):
        ticker   = row["ma_cw"]
        ratio    = _parse_ratio(row.get("ty_le_chuyen_doi", 1))
        exercise = _parse_exercise(row.get("gia_thuc_hien", 0))
        sub      = ohlcv_idx.get(ticker, pd.DataFrame())
        price_cw = float(sub["close"].iloc[-1]) if not sub.empty else 0.0

        # Uoc tinh gia underlying (S) tu gia CW va ty le CD
        # S ~ price_CW * ratio * 1000 * markup (vi CW thuong giao dich discount)
        # Day la xap xi; de chinh xac hon can nguon gia co phieu rieng
        S = price_cw * ratio * 1000 * 1.15 if price_cw > 0 else 0

        intrinsic   = max(S - exercise, 0)
        premium     = ((price_cw*1000*ratio - intrinsic) / S * 100) if S > 0 else 0
        gross_lev   = (S / (price_cw*1000*ratio)) if price_cw > 0 and ratio > 0 else 0
        delta       = 0.65 if intrinsic > 0 else 0.35
        eff_lev     = gross_lev * delta
        breakeven   = (exercise + price_cw*1000*ratio) / 1000
        moneyness   = "ITM" if S > exercise*1.02 else "OTM" if S < exercise*0.98 else "ATM"
        return {
            "price":    round(price_cw, 3),
            "exercise": exercise,
            "ratio":    ratio,
            "premium":  round(premium, 1),
            "eff_lev":  round(eff_lev, 2),
            "breakeven":round(breakeven, 1),
            "moneyness":moneyness,
        }

    cw_list = []
    for _, row in df_info.iterrows():
        status = "active" if pd.notna(row["_last_gd_dt"]) and row["_last_gd_dt"] >= today_ts else "expired"
        issuer = str(row.get("to_chuc_ph_cw","")).replace("CTCP Chứng khoán ","").split("(")[0].strip()
        cw_list.append({
            "ticker":     str(row.get("ma_cw","")),
            "underlying": str(row.get("ck_co_so","")),
            "issuer":     issuer,
            "maturity":   str(row.get("ngay_dao_han","")),
            "status":     status,
            **calc_metrics(row),
        })

    # OHLCV drill-down: 120 phien gan nhat moi ma
    df_ohlcv_filtered = df_ohlcv_filtered.copy()
    df_ohlcv_filtered["time_dt"] = pd.to_datetime(
        df_ohlcv_filtered["time"], dayfirst=True, errors="coerce"
    )
    ohlcv_out = {}
    ratio_map = {c["ticker"]: c["ratio"] for c in cw_list}

    for ticker in valid_tickers:
        sub = (df_ohlcv_filtered[df_ohlcv_filtered["Ticker"]==ticker]
               .sort_values("time_dt").tail(120))
        if sub.empty: continue
        ratio = ratio_map.get(ticker, 1)
        ohlcv_out[ticker] = {
            "dates":            sub["time_dt"].dt.strftime("%d/%m").tolist(),
            "close":            [round(float(v),3) for v in sub["close"]],
            "underlying_close": [round(float(v)*ratio*1000*1.15, 0) for v in sub["close"]],
        }

    out = {
        "updated_at": datetime.now().strftime("%d/%m/%Y %H:%M ICT"),
        "cw_list":    cw_list,
        "ohlcv":      ohlcv_out,
    }
    os.makedirs("docs", exist_ok=True)
    with open("docs/data.json","w",encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",",":"))

    size_kb = os.path.getsize("docs/data.json") / 1024
    print(f"OK docs/data.json  ({len(cw_list)} CW, {len(ohlcv_out)} OHLCV, {size_kb:.0f} KB)")

# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════
if __name__=="__main__":
    t0 = time.time()
    df_vs              = step1_vietstock()
    df_ohlcv_full      = step2_ohlcv(df_vs)
    df_filtered, valid = step3_filter(df_ohlcv_full)
    step4_excel(df_filtered, df_vs, valid)
    step5_export_json(df_filtered, df_vs, valid)
    print(f"\nDone in {(time.time()-t0)/60:.1f} min")
