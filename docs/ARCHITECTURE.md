# Kiến trúc hệ thống CW Intelligence

> Phiên bản 1.0.0 · Cập nhật 04/11/2026

## 1. Tổng quan

Hệ thống gồm **hai pipeline độc lập nhưng dùng chung nguồn dữ liệu**:

1. **Pipeline gốc** (`pipeline.py`) — scrape Vietstock, tải OHLCV, xuất Excel và `docs/data.json` cho dashboard cũ (`docs/legacy.html`). Giữ nguyên để bảo đảm tương thích và không phá vỡ quy trình đang chạy.
2. **CW Intelligence** (`cwintel/`) — đọc lại cache parquet do pipeline gốc tạo ra, chuẩn hoá, tính toán định lượng, chấm điểm, backtest và phát hành JSON tĩnh cho SPA mới (`docs/index.html`).

Không có backend, không có database, không có API key trong repo. Mọi thứ là **batch + static hosting**.

```
                        ┌──────────────────────────────────────────┐
 Vietstock ────────────▶│ pipeline.py (Playwright + requests)      │
 vnstock VCI/KBS ──────▶│  • scrape điều khoản CW                  │──▶ output/cw_master.xlsx
 HNX / VBMA ───────────▶│  • tải OHLCV CW & cổ phiếu cơ sở         │──▶ docs/data.json (legacy)
                        │  • cache parquet                          │
                        └──────────────────┬───────────────────────┘
                                           │ output/cache/*.parquet
                                           ▼
                        ┌──────────────────────────────────────────┐
                        │ cwintel/data.py    chuẩn hoá, dedupe     │
                        │ cwintel/dates.py   parse ngày/số VN      │
                        │ cwintel/panels.py  panel đặc trưng       │
                        │ cwintel/bs.py      BS, Greeks, IV        │
                        │ cwintel/indicators.py RSI/MACD/ATR/HV    │
                        │ cwintel/scoring.py CW Score + cổng       │
                        │ cwintel/recommend.py card, kế hoạch      │
                        │ cwintel/backtest.py walk-forward         │
                        │ cwintel/quality.py 15 kiểm tra DQ        │
                        │ cwintel/methodology.py công bố phương pháp│
                        │ cwintel/build.py   xuất artifact         │
                        └──────────────────┬───────────────────────┘
                                           ▼
                            docs/data/*.json  (≈13 MB, tĩnh)
                                           ▼
                            docs/index.html + assets/*.js (SPA)
                                           ▼
                                   GitHub Pages
```

## 2. Luồng dữ liệu chi tiết

### 2.1 Ingestion

- **Điều khoản CW**: `output/cache/vietstock.parquet` (ticker, underlying, issuer, strike, ratio, maturity, first/last trade, adjusted terms, break-even niêm yết).
- **OHLCV CW**: `output/cache/ohlcv.parquet` — từng có **hai định dạng ngày song song** (`dd/mm/yyyy` và ISO+07:00) cho cùng một phiên, gây trùng lặp 31,4% (xem `AUDIT.md`).
- **OHLCV cổ phiếu cơ sở**: `output/cache/underlying.parquet`.
- **Lãi suất phi rủi ro**: `output/cache/hnx_bond_yields.csv`, lấy lợi suất 10Y tại ngày dữ liệu, fallback hằng số trong `config.py`.

`cwintel/data.py::load_market_data()` trả `MarketData` gồm `master`, `ohlcv`, `underlying`, `asof`, `risk_free`, `risk_free_source`, `risk_free_date`, `diagnostics`. **Không đọc lại API** ở bước này — chỉ đọc cache.

### 2.2 Chuẩn hoá (validation)

- `parse_date()` hiểu `YYYY-MM-DD`, `DD/MM/YYYY`, ISO có timezone, quy về ngày giao dịch local.
- Dedupe theo `(ticker, ngày)`, giữ bản ghi có khối lượng lớn hơn; ghi lại số dòng bị loại trong `diagnostics`.
- Giá CW và cổ phiếu cơ sở quy về **VND** (một số nguồn trả nghìn VND).
- Điều khoản: dùng `K_adj` / `ratio_adj` nếu có; đánh dấu `terms_adjusted`.
- Phân loại active/expired **theo ngày dữ liệu** (`asof`), không theo `today` — lỗi cũ khiến CW đã đáo hạn vẫn hiện "active".

### 2.3 Panel đặc trưng

`build_cw_panel()` tạo 1 dòng / (CW, phiên), gồm:

- Giá & thanh khoản: `ret1/5/21`, `value`, `value_med20`, `traded_ratio20`, `volume_accel`, `atr14`, `atr_pct`, `ret_std20`.
- Kỹ thuật CW: `rsi14`, `macd_hist`, `macd_hist_slope`, `ma20/50`, `above_ma20/50`, `breakout20`, `sessions`.
- Điều khoản: `K`, `ratio`, `maturity`, `T`, `days_to_maturity`, `is_active`.
- Đặc trưng cổ phiếu cơ sở ghép **as-of + ffill** (chỉ mang dữ liệu quá khứ): `u_close`, `u_ret21/63`, `u_rsi14`, `u_hv20/60/252`, `u_above_ma50`, `u_dist_high60`…
- Định giá: `bs_fv`, `intrinsic`, `time_value`, `premium_be`, `breakeven`, `gearing`, `eff_gearing`, Greeks theo CW.
- IV: `implied_vol_vector` (bisection) cho từng phiên → `iv`, `iv_quality`, `iv_rank` (lịch sử 1 năm), `iv_vs_hv`.

### 2.4 Snapshot & scoring

`build_snapshot(asof, tolerance_days=14)`:

1. Lấy dòng cuối cùng ≤ `asof` cho mỗi CW (dung sai 14 ngày để không rơi nửa vũ trụ).
2. Ghép metadata TCPH, tỷ trọng giá trị giao dịch của TCPH.
3. `add_peer_metrics()` — fit **smile IV** theo `ln(K/S)/√T` cho từng cổ phiếu cơ sở (tuyến tính nếu R² ≥ 0,15, kernel Gaussian nếu không), tính `iv_resid`, premium trung vị nhóm, `fv_smile`.
4. `score_universe()` — 6 thành phần, mỗi thành phần trả `(score, confidence, detail)`; tổng hợp có trọng số × confidence.
5. `classify_frame()` — áp ngưỡng **tăng dần** rồi các cổng chất lượng; trả `(recommendation, rec_reason)`.

### 2.5 Phát hành (build)

`build_all()` ghi:

| Tệp | Nội dung | Kích thước điển hình |
|---|---|---|
| `meta.json` | phiên bản, as-of, nguồn, lãi suất, danh sách series, kích thước tệp, thời gian build | ~10 KB |
| `market.json` | KPI, phân bố TCPH/cơ sở, top lists, breadth 250 phiên | ~100 KB |
| `screener.json` | 348 CW active + CW đã đáo hạn, 40+ trường | ~730 KB |
| `recommendations.json` | card đầy đủ cho mọi CW active | ~1,1 MB |
| `underlyings.json` | tổng hợp 22 cổ phiếu cơ sở | ~6 KB |
| `backtest.json` | summary, curve, trades, buckets, độ nhạy, caveats | ~100 KB |
| `quality.json` | 15 kiểm tra + headline | ~5 KB |
| `methodology.json` | công thức, trọng số, cổng, giới hạn | ~9 KB |
| `series/cw/<ticker>.json` | ~759 tệp, chỉ CW active hoặc giao dịch trong 365 ngày | ~11 MB |
| `series/und/<sym>.json` | 22 tệp, 500 phiên gần nhất | ~2 MB |

**Quy ước làm tròn**: giá 1 chữ số thập phân, % 1–2, điểm 1, confidence 3. `NaN` → `null` để JSON hợp lệ.

## 3. Frontend

- **Không phụ thuộc thư viện ngoài**: chart vẽ bằng canvas (`core.js`), CSS thuần, ES modules.
- **Định tuyến hash**: `#/overview`, `#/heatmap`, `#/screener`, `#/cw/<ticker>`, `#/recommendations`, `#/backtest`, `#/watchlist`, `#/portfolio`, `#/alerts`, `#/data`, `#/method`.
- **Dữ liệu tải lười**: chỉ fetch JSON khi vào trang; series chỉ tải khi mở chi tiết; cache trong bộ nhớ.
- **Trạng thái người dùng** (watchlist, danh mục mô phỏng, bộ lọc, cảnh báo) lưu `localStorage`, không gửi ra ngoài.
- **Suy giảm hợp lý**: nếu thiếu tệp (CW đáo hạn, chưa build series), hiển thị thông báo thay vì lỗi.
- **Cảnh báo dữ liệu cũ**: `meta.dataAgeDays > 3` → banner trên toàn bộ trang.

## 4. Hiệu năng

Đo trên máy 4 vCPU với cache sẵn:

| Bước | Thời gian |
|---|---|
| Nạp + chuẩn hoá 273k dòng OHLCV | ~8 s |
| Panel 158k dòng, 148k quan sát IV | ~30 s |
| Snapshot + scoring 348 CW | ~5 s |
| Backtest walk-forward 43 kỳ, 215 lệnh | ~90 s |
| Xuất 780 tệp JSON | ~25 s |
| **Tổng** | **~250 s** |

RAM đỉnh ~1,5 GB. Toàn bộ chạy trong GitHub Actions runner 7 GB.

## 5. Quyết định thiết kế quan trọng

1. **Không dùng BS@HV làm tín hiệu mua.** Trên thị trường VN gần như mọi CW giao dịch cao hơn giá trị BS theo HV; dùng nó sẽ "mua" toàn bộ thị trường. Thay vào đó dùng **định giá tương đối** (premium, IV residual so đường cong cùng cơ sở).
2. **Percentile trong cùng cơ sở** cho premium/IV, tránh so CW FPT với CW HPG.
3. **Momentum percentile trên các underlying duy nhất**, tránh underlying có 30 CW làm méo phân bố.
4. **Confidence-weighted score**: CW thiếu dữ liệu bị giảm trọng số thay vì bị điểm 0 oan.
5. **Cổng chất lượng tách khỏi điểm**: điểm cao vẫn có thể bị hạ hạng; lý do được ghi vào `rec_reason`.
6. **Backtest tách khỏi build demo**: báo cáo cả chiến lược thua lỗ, kèm độ nhạy và caveats.
7. **Artifact tĩnh**: đơn giản, miễn phí, không cần server; đổi lại không có realtime và không có order routing.

## 6. Bảo mật & vận hành

- Không có secret trong repo. `VNSTOCK_API` (nếu dùng) lấy từ GitHub Secrets.
- Dashboard chỉ đọc tệp tĩnh cùng origin; không có CORS, không có endpoint ghi.
- Dữ liệu cá nhân (watchlist/danh mục) không rời khỏi trình duyệt.
- Log build in ra stdout, có `buildSeconds`, `warnings`, số bản ghi từng bước.
