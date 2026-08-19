"""
Script patch OHLCV cache: fetch missing data from 15/08 -> 19/08 for all stuck CWs
"""
import os, time, pandas as pd
from datetime import datetime, timezone, timedelta

OHLCV_CACHE = 'output/cache/ohlcv.parquet'
VIETSTOCK_CACHE = 'output/cache/vietstock.parquet'
START_DATE = '2026-08-15'
END_DATE = '2026-08-20'

def normalise(df, symbol):
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    time_col = None
    for c in df.columns:
        if 'time' in c.lower() or 'date' in c.lower():
            time_col = c
            break
    if time_col is None:
        time_col = df.columns[0]
    df = df.rename(columns={time_col: 'time'})
    df['time'] = df['time'].astype(str).str.strip()
    df['time'] = df['time'].str.replace(r'\s+\d{2}:\d{2}.*$', '', regex=True)
    parsed = pd.to_datetime(df['time'], errors='coerce')
    df['time'] = parsed.dt.strftime('%d/%m/%Y')
    df['Ticker'] = symbol
    keep = [c for c in ['time','open','high','low','close','volume','Ticker'] if c in df.columns]
    return df[keep].dropna(subset=['time'])

print('Loading caches...')
df_cache = pd.read_parquet(OHLCV_CACHE)
df_vs = pd.read_parquet(VIETSTOCK_CACHE)

# Xác định CW đang hoạt động (ngay_gd_cuoi_cung >= hôm nay)
from datetime import date
today = (datetime.now(timezone.utc) + timedelta(hours=7)).date()
today_ts = pd.Timestamp(today)
ldt_vs = pd.to_datetime(df_vs['ngay_gd_cuoi_cung'], dayfirst=True, errors='coerce')
active_cws = set(df_vs.loc[ldt_vs >= today_ts, 'ma_cw'].tolist())
print(f'Active CWs today: {len(active_cws)}')

df_cache['time'] = df_cache['time'].astype(str)
df_cache['time_dt'] = pd.to_datetime(df_cache['time'], dayfirst=True, errors='coerce')
last_dt = df_cache.groupby('Ticker')['time_dt'].max()

cutoff = pd.Timestamp('2026-08-14').date()

# Nhóm 1: CW active nhưng CHƯA có OHLCV nào → fetch từ ngay_gd_dau_tien
no_ohlcv = active_cws - set(last_dt.index)
# Nhóm 2: CW active nhưng data bị stuck tại 14/08 trở về trước
stuck_14 = [sym for sym in active_cws if sym in last_dt.index and last_dt[sym].date() <= cutoff]

# Lookup ngay_gd_dau_tien từ vietstock cache để fetch đúng điểm bắt đầu
first_date_map = {}
if 'ngay_gd_dau_tien' in df_vs.columns:
    for _, row in df_vs[['ma_cw','ngay_gd_dau_tien']].dropna().iterrows():
        try:
            dt = pd.to_datetime(str(row['ngay_gd_dau_tien']).strip(), dayfirst=True, errors='coerce')
            if pd.notna(dt):
                first_date_map[row['ma_cw']] = (dt - timedelta(days=1)).strftime('%Y-%m-%d')
        except Exception:
            pass

print(f'CW chua co OHLCV nao: {len(no_ohlcv)} -> {sorted(no_ohlcv)}')
print(f'CW bi stuck tai <=14/08: {len(stuck_14)}')

# Gộp lại: (ticker, start_str)
need_update = []
for sym in sorted(no_ohlcv):
    start = first_date_map.get(sym, START_DATE)
    need_update.append((sym, start))
for sym in sorted(stuck_14):
    last = last_dt[sym]
    start = (last + timedelta(days=1)).strftime('%Y-%m-%d') if pd.notna(last) else START_DATE
    need_update.append((sym, start))

print(f'Tong can fetch: {len(need_update)} tickers')


from vnstock.api.quote import Quote
import re

DELAY = 1.2   # 1.2s/request = 50 req/min, an toàn dưới ngưỡng 60 req/min của Community

new_rows = []
failed = []
n_ok = 0

def fetch_with_retry(sym, start_str, end_str, max_retries=3):
    """Fetch OHLCV với xử lý rate limit tự động."""
    for attempt in range(1, max_retries + 1):
        for source in ['VCI', 'KBS']:
            try:
                q = Quote(symbol=sym, source=source)
                df_r = q.history(start=start_str, end=end_str, interval='1D')
                if df_r is not None and not df_r.empty:
                    return df_r
            except Exception as e:
                msg = str(e).lower()
                # Phát hiện rate limit
                if any(k in msg for k in ['rate limit', '429', 'gioi han', 'exceeded', 'wait']):
                    # Tìm thời gian chờ trong thông báo lỗi
                    wait_match = re.search(r'ch[oờ]\s+(\d+)\s+gi[âa]y', str(e), re.IGNORECASE)
                    wait_sec = int(wait_match.group(1)) + 2 if wait_match else 62
                    print(f'    [RL] {sym} → chờ {wait_sec}s...')
                    time.sleep(wait_sec)
                    break  # thử lại với cùng source
                # Lỗi khác → thử source tiếp theo
                break
    return None

for i, (sym, start_str) in enumerate(need_update, 1):
    df_r = fetch_with_retry(sym, start_str, END_DATE)
    if df_r is not None:
        df_norm = normalise(df_r, sym)
        if not df_norm.empty:
            new_rows.append(df_norm)
            n_ok += 1
            if i <= 6 or i % 50 == 0:
                print(f'  [{i:>4}/{len(need_update)}] OK {sym} (from {start_str}) +{len(df_norm)} rows')
    else:
        failed.append(sym)
        if len(failed) <= 5:
            print(f'  [{i:>4}/{len(need_update)}] SKIP {sym} (no data)')

    time.sleep(DELAY)

print(f'\nDone: OK={n_ok} | FAIL={len(failed)} | new_rows_chunks={len(new_rows)}')
if failed:
    print(f'Failed: {failed[:10]}')

if new_rows:
    df_add = pd.concat(new_rows, ignore_index=True)
    # Merge
    df_cache.drop(columns=['time_dt'], inplace=True)
    df_merged = pd.concat([df_cache, df_add], ignore_index=True)
    df_merged['time'] = df_merged['time'].astype(str).str.strip()
    df_merged = df_merged[~df_merged['time'].isin(['NaT','nan',''])]
    df_merged['_sort_dt'] = pd.to_datetime(df_merged['time'], dayfirst=True, errors='coerce')
    df_merged.sort_values(['Ticker','_sort_dt'], inplace=True)
    df_merged.drop_duplicates(subset=['time','Ticker'], keep='last', inplace=True)
    df_merged.drop(columns=['_sort_dt'], inplace=True)
    df_merged.reset_index(drop=True, inplace=True)
    df_merged.to_parquet(OHLCV_CACHE, index=False)
    print(f'Saved: {len(df_merged):,} rows to {OHLCV_CACHE}')
    
    # Verify
    df_check = pd.read_parquet(OHLCV_CACHE)
    df_check['time'] = df_check['time'].astype(str)
    df_check['time_dt'] = pd.to_datetime(df_check['time'], dayfirst=True, errors='coerce')
    last2 = df_check.groupby('Ticker')['time_dt'].max()
    print(f'CSTB2604 last date now: {last2.get("CSTB2604")}')
    print(f'CSTB2609 last date now: {last2.get("CSTB2609")}')
    still_stuck = (last2.dt.date <= cutoff).sum()
    print(f'Still stuck at 14/08: {still_stuck} tickers')
else:
    print('No new data fetched - check your network or API')
