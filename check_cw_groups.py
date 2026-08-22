import pandas as pd
from datetime import datetime, timezone, timedelta

df_vs = pd.read_parquet('output/cache/vietstock.parquet')
df_ohlcv = pd.read_parquet('output/cache/ohlcv.parquet')

today = (datetime.now(timezone.utc) + timedelta(hours=7)).date()
today_ts = pd.Timestamp(today)
ldt_vs = pd.to_datetime(df_vs['ngay_gd_cuoi_cung'], dayfirst=True, errors='coerce')
ldt_start = pd.to_datetime(df_vs.get('ngay_gd_dau_tien', pd.Series(dtype=str)), dayfirst=True, errors='coerce')

aug15 = pd.Timestamp('2026-08-15')
filter_date = pd.Timestamp('2024-01-02')

# OHLCV last dates
df_ohlcv['time'] = df_ohlcv['time'].astype(str)
df_ohlcv['time_dt'] = pd.to_datetime(df_ohlcv['time'], dayfirst=True, errors='coerce')
last_ohlcv = df_ohlcv.groupby('Ticker')['time_dt'].max()

# Group 1: Active
active = df_vs[ldt_vs >= today_ts]
print(f'Active CWs (expired >= today): {len(active)}')

# Group 2: Recently expired (expired 15-19/08) -> still need data update
recently_expired = df_vs[(ldt_vs >= aug15) & (ldt_vs < today_ts)]
print(f'CW het han tu 15-19/08: {len(recently_expired)}')
print(recently_expired[['ma_cw','ngay_gd_cuoi_cung']].to_string())

# Group 3: Expired before 15/08 -> OHLCV data is complete, no update needed
old_expired = df_vs[ldt_vs < aug15]
print(f'\nCW het han truoc 15/08 (OHLCV da day du): {len(old_expired)}')

print(f'\nTong CW trong vietstock cache: {len(df_vs)}')
filter_2024 = (ldt_vs >= filter_date) | (ldt_start >= filter_date)
print(f'CW niem yet tu 2024 tro di: {filter_2024.sum()}')
