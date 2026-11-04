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
                        │ cwintel/liquidity.py ADV/Amihud/DTL    │
                        │ cwintel/bs.py      BS, Greeks, IV        │
                        │ cwintel/indicators.py RSI/MACD/ATR/HV    │
                        │ cwintel/scoring.py CW Score + cổng       │
                        │ cwintel/recommend.py card, kế hoạch      │
                        │ cwintel/backtest.py walk-forward         │
                        │ cwintel/quality.py 21 kiểm tra DQ        │
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

0. **Lọc theo vòng đời** (xem §2.6): chỉ giữ CW còn hiệu lực tại `asof`
   (`maturity > asof`, đã bắt đầu giao dịch). CW đã đáo hạn / chờ niêm yết
   không bao giờ vào snapshot nên không bị chấm điểm hay khuyến nghị.
1. Lấy dòng cuối cùng ≤ `asof` cho mỗi CW (dung sai 14 ngày để không rơi nửa vũ trụ).
2. Ghép metadata TCPH, tỷ trọng giá trị giao dịch của TCPH.
3. `add_peer_metrics()` — fit **smile IV** theo `ln(K/S)/√T` cho từng cổ phiếu cơ sở (tuyến tính nếu R² ≥ 0,15, kernel Gaussian nếu không), tính `iv_resid`, premium trung vị nhóm, `fv_smile`.
4. **DTE/T tính lại tại `asof`** (`maturity − asof`), không kế thừa DTE của phiên
   khớp lệnh cuối — nhờ vậy DTE không thể âm dù giá đã cũ.
5. `score_universe()` — 6 thành phần, mỗi thành phần trả `(score, confidence, detail)`; tổng hợp có trọng số × confidence.
6. `classify_frame()` — áp ngưỡng **tăng dần** rồi các cổng chất lượng; trả `(recommendation, rec_reason)`.

### 2.5 Phát hành (build)

`build_all()` ghi:

| Tệp | Nội dung | Kích thước điển hình |
|---|---|---|
| `meta.json` | phiên bản, as-of, **`session`** (phiên đã đóng gần nhất, số phiên bị thiếu), **`marketHolidays`** cho đồng hồ, nguồn, lãi suất, danh sách series, kích thước tệp, thời gian build | ~11 KB |
| `market.json` | KPI, phân bố TCPH/cơ sở, top lists, breadth 250 phiên | ~100 KB |
| `screener.json` | CW còn hiệu lực + CW đã đáo hạn/ngừng giao dịch, 40+ trường | ~730 KB |
| `recommendations.json` | card đầy đủ cho mọi CW còn hiệu lực | ~1,1 MB |
| `lifecycle.json` | trạng thái vòng đời, sự kiện niêm yết/đáo hạn, lịch 12+12 tháng | ~24 KB |
| `underlyings.json` | tổng hợp 22 cổ phiếu cơ sở | ~6 KB |
| `backtest.json` | summary, curve theo phiên, trades, buckets, regime, độ nhạy, caveats VI/EN | ~212 KB |
| `quality.json` | 21 kiểm tra + headline | ~6 KB |
| `methodology.json` | công thức, trọng số, cổng, giới hạn | ~9 KB |
| `series/cw/<ticker>.json` | ~759 tệp, chỉ CW active hoặc giao dịch trong 365 ngày | ~11 MB |
| `series/und/<sym>.json` | 22 tệp, 500 phiên gần nhất | ~2 MB |

**Quy ước làm tròn**: giá 1 chữ số thập phân, % 1–2, điểm 1, confidence 3. `NaN` → `null` để JSON hợp lệ.


### 2.6 Vòng đời CW: niêm yết liên tục, đáo hạn liên tục

### 2.7 Độ mới dữ liệu: phiên đã đóng gần nhất (`cwintel/sessions.py`)

`asof` chỉ nói dữ liệu *dừng ở đâu*, không nói dữ liệu *có nên dừng ở đó không*. Ngày 03/11/2026
build đã chạy "thành công" trên cache chưa có phiên 04/11 và phát hành nguyên trạng: dashboard
ghi "Phiên dữ liệu 03/11" trong khi phiên 04/11 đã đóng cửa, và ngưỡng cũ (`dataAgeDays > 4`,
đếm **ngày lịch**) không hề kêu. Từ bản này build luôn đối chiếu thêm một mốc thứ hai:

- **Phiên đã đóng gần nhất** (`last_closed_session`) tính theo giờ Việt Nam: Thứ Hai–Thứ Sáu,
  trừ `config.MARKET_HOLIDAYS`, và chỉ tính phiên hôm nay sau **15:10 ICT** (`CLOSE_READY`) để
  chờ dữ liệu ATC về.
- `session_status(asof)` trả `lagSessions` (số **phiên** thiếu, không phải ngày), `missing[]`,
  `expected/expectedLabel`, `checkedAt` và `status` = `ok` (0) · `warn` (1) · `stale` (≥ 2).
- Kết quả được ghi vào `meta.session`, `meta.dataAgeSessions`, `meta.expectedAsOf*`; `meta.stale`
  bật khi lệch ≥ 2 phiên **hoặc** cũ hơn `STALE_DATA_DAYS_WARNING` ngày.
- `quality.json` có thêm cổng `session_lag` (tổng 21 cổng) để build không thể im lặng.
- UI đọc `meta.session`: sidebar đổi nhãn thành **"Phiên dữ liệu cuối"** kèm dòng "Trễ N phiên";
  pill đầu trang đếm phiên thật ("Thiếu 1 phiên" thay cho "cách 3 ngày"); lệch 1 phiên hiện banner
  vàng, lệch ≥ 2 phiên hiện banner đỏ.

Lễ âm lịch (Tết, Giỗ Tổ) được liệt kê tường minh trong `MARKET_HOLIDAYS`, không tự suy ra bằng
thư viện lịch âm. Bảng hiện có **12 phiên nghỉ năm 2025** và **13 phiên năm 2026** theo lịch
HOSE/HNX đã công bố; **11 phiên năm 2027 là dự kiến** theo lịch nghỉ Chính phủ và phải đối chiếu
lại khi Sở công bố. Các ngày nghỉ bù rơi vào ngày trong tuần cũng được liệt kê; ngày làm bù vào
thứ Bảy vẫn không là phiên giao dịch.

Không tự suy lịch giao dịch từ mọi ngày nghỉ lao động: ngày **24/11/2026 (Ngày Văn hóa Việt Nam)**
chưa được đưa vào vì đến 04/11/2026 chưa thấy HOSE/HNX xác nhận nghỉ giao dịch. Đây là lựa chọn
an toàn cho giám sát — nếu Sở nghỉ mà bảng chưa cập nhật, hệ thống có thể cảnh báo sớm; ngược lại,
khai báo nhầm một ngày vẫn mở cửa là ngày lễ sẽ **che mất cảnh báo chậm dữ liệu**.


CW không phải vũ trụ tĩnh: mỗi tuần có mã mới niêm yết, mỗi tháng có mã đáo hạn.
Vì vậy mọi mặt cắt phải phân loại lại **mỗi lần build** — `cwintel/lifecycle.py`
là nguồn duy nhất cho việc này.

**Năm trạng thái** (mỗi CW thuộc đúng một trạng thái):

| Trạng thái | Điều kiện | Xử lý |
|---|---|---|
| `listed` | `maturity > asof` và đã bắt đầu giao dịch | vào snapshot, được chấm điểm/khuyến nghị |
| `matured` | `maturity <= asof` | sang `screener.expired`, không chấm điểm |
| `delisted_early` | còn hạn nhưng im lặng > `LIFECYCLE_EARLY_STOP_DAYS` (45 ngày) | như trên, kèm cờ ngừng sớm |
| `pending` | `first_trade > asof` | chưa vào snapshot |
| `unknown` | thiếu `maturity` | loại khỏi snapshot, bị quality cảnh báo |

**Bất biến được kiểm tra tự động**: `total = listed + matured + delisted_early +
pending + unknown`; `screener.active ∩ screener.expired = ∅`; mọi CW trong
`recommendations.json` đều thuộc `screener.active`; `DTE ≥ 0` trong snapshot.
Vi phạm → check `universe_identity` / `snapshot_lifecycle` / `recs_listed_only`
chuyển sang `error` và build bị coi là hỏng.

**Phát hiện sự kiện** (cửa sổ 10 phiên, tính trên lịch phiên thật từ panel):
`newListings` (`first_trade` trong cửa sổ), `recentMaturities` (`maturity` trong
cửa sổ), `upcoming` 30/60/90 ngày, `earlyDelistings`. Mỗi sự kiện kèm danh sách
mã để dashboard hiển thị trực tiếp — không cần người dùng mở app mới biết.

**Lưu ý về `last_trade` của Vietstock**: trường này là *phiên giao dịch cuối theo
kế hoạch* (thường trước ngày đáo hạn 2 ngày), nằm ở **tương lai** so với `asof`,
nên **không dùng** để phát hiện "đã ngừng giao dịch". Việc đó dựa trên giá quan
sát được trong panel (`days_since_print`).

Dashboard: khối **Vòng đời chứng quyền** ở trang Tổng quan (4 thẻ sự kiện + lịch
niêm yết/đáo hạn theo tháng + dòng đối soát tổng vũ trụ), cột **Trạng thái** và
chip lọc "Bao gồm CW đã đáo hạn (N)" ở Screener.

## 3. Frontend

- **Không phụ thuộc thư viện ngoài**: chart vẽ bằng canvas (`core.js`), CSS thuần, ES modules.
- **Định tuyến hash**: `#/overview`, `#/heatmap`, `#/screener`, `#/cw/<ticker>`, `#/recommendations`, `#/backtest`, `#/watchlist`, `#/portfolio`, `#/alerts`, `#/data`, `#/method`.
- **Dữ liệu tải lười**: chỉ fetch JSON khi vào trang; series chỉ tải khi mở chi tiết; cache trong bộ nhớ.
- **Trạng thái người dùng** (watchlist, danh mục mô phỏng, bộ lọc, cảnh báo) lưu `localStorage`, không gửi ra ngoài.
- **Suy giảm hợp lý**: nếu thiếu tệp (CW đáo hạn, chưa build series), hiển thị thông báo thay vì lỗi.
- **Cảnh báo dữ liệu cũ**: `meta.dataAgeDays > 3` → banner trên toàn bộ trang.

### 3.1 Song ngữ Việt/Anh (`docs/assets/i18n.js`)

Ba chế độ, chuyển ngay trong topbar, lưu ở `localStorage` (`cwintel:lang`): **VI** (mặc định) · **EN** · **VI+EN**.

Cơ chế dịch không cần backend và không sinh thêm artifact JSON:

| Lớp | Dùng cho | Ghi chú |
|---|---|---|
| `STRINGS` (~600 mục) | nhãn, tiêu đề, cột, nút, tab, ghi chú tĩnh | khoá = chuỗi tiếng Việt đã render, nên không phải sửa 776 literal trong các page |
| `TEMPLATES` (~40 regex) | câu do engine sinh (yếu tố +/−, cảnh báo, vô hiệu hoá, rec_reason) | bắt phần số rồi ghép lại theo trật tự tiếng Anh |
| `PHRASES` | nhãn số ngắn chưa có trong từ điển | chỉ nhận kết quả đã "sạch" tiếng Việt, tránh câu nửa Việt nửa Anh |

Chi tiết triển khai:

- `applyI18n(root)` đi qua text node + thuộc tính `placeholder/title/aria-label`; router gọi lại sau mỗi lần render, thêm `MutationObserver` (debounce 60 ms) cho nội dung render muộn.
- Chế độ **VI+EN** giữ nguyên tiếng Việt và chèn bản dịch nghiêng ngay sau (`<span class="i18n-en">`), chỉ với nhãn ngắn (≤ 48 ký tự) và bỏ qua ô bảng `<td>` để bảng không rối.
- Đổi ngôn ngữ: khôi phục text gốc từ `Map` → áp dụng lại → `render()` lại route, nên `Intl.NumberFormat` chuyển `vi-VN` ↔ `en-US` và chart vẽ lại nhãn.
- Số liệu, ngày tháng và đơn vị (`triệu`/`tỷ` ↔ `m`/`bn`) đổi theo locale trong `core.js` (`fmt.n`, `fmt.vnd`, `fmt.unit`, `fmt.dte`, `fmt.rec`).
- Kiểm thử tĩnh: `tests/test_dashboard_i18n.py` (khoá trùng, bản dịch rỗng/sót tiếng Việt, có công tắc, có hook i18n); kiểm thử DOM chạy cả 4 tổ hợp VI/EN/VI+EN × dark/light, yêu cầu 0 lỗi console và 0 chuỗi chưa dịch ở chế độ EN.

### 3.2 Heatmap: thang màu & tương phản (`docs/assets/heatscale.js`)

Heatmap từng **không hiển thị được** vì `colorFor()` nhận `metric.domain` — một **hàm** `(rows) => …` — thay vì giá trị đã resolve, nên `value / function = NaN` và `mix()` trả `#NaNNaNNaN`. CSS không hợp lệ ⇒ ô trong suốt; `.tm-cell` lại hardcode `color:#fff` ⇒ chữ trắng trên nền trắng ở light mode (dark mode chỉ mất mã màu).

Cách sửa, giữ được cả hai theme:

- `heatscale.js` là module **thuần, không phụ thuộc DOM**: `resolveDomain()` (hàm/mảng/số/null), `mix()`, `luminance()`, `contrast()`, `pickText()`, `readable()`, `scaleColor()`, `legendStops()`.
- `scaleColor()` **luôn** trả `#rrggbb` hợp lệ; mọi đầu vào `NaN/null/undefined/Infinity` rơi về `NO_DATA_COLOR`, không bao giờ sinh `#NaN`.
- `readable(bg)` chọn chữ trắng hoặc chữ đen theo tương phản, và nếu vẫn dưới 4,6:1 thì **dịch nhẹ độ sáng của nền** (giữ nguyên sắc) cho tới khi đạt — nên chữ trên mọi ô đạt WCAG AA ở cả light/dark, không cần hardcode màu chữ.
- `heatmap.js`: `resolveMetric(name, rows)` trả metric với `domain` đã resolve; mỗi ô đặt cả `background` và `color` inline; thêm `role="link"`, `tabindex`, `aria-label`, mở bằng Enter/Space; legend lấy đúng dải màu đang dùng + ô "N/A"; có trạng thái rỗng và vẽ lại khi đổi kích thước (`ResizeObserver`, chỉ khi bề rộng đổi > 8 px để tránh vòng lặp).
- Kiểm thử: `tests/js/heatscale.test.mjs` (3.100+ phép kiểm tra: màu hợp lệ, tương phản ≥ 4,5:1 cho mọi thang/giá trị, domain kiểu hàm, legend, `safeHex`) chạy qua `tests/test_heatmap_scale.py`; cộng thêm kiểm thử DOM 8 chỉ số × {light, dark} yêu cầu 0 ô lỗi, 0 ô tương phản thấp, 0 lỗi console.

### 3.3 Giao diện sáng/tối

- Hai bảng token đầy đủ trong `app.css` (`html[data-theme="dark"|"light"]`), không hardcode màu trong page.
- Nút topbar xoay vòng **Sáng → Tối → Theo hệ thống** (`cwintel:themeMode`), có lắng nghe `prefers-color-scheme`; `data-theme` trên `<html>` để CSS và chart dùng cùng nguồn.
- Chart tự vẽ lại khi đổi theme hoặc đổi kích thước: `registerChart()` gắn `_redraw` cho từng canvas, `ResizeObserver` (debounce 80 ms) + `redrawAllCharts()`.
- Thêm cho khả năng đọc: legend theo màu phía trên chart, crosshair + tooltip nhiều series (không cần hover chính xác), nhãn trục tự nới `padL`, header bảng dính, kẻ sọc, cột mã dính, `text-wrap: pretty`, `focus-visible`, tôn trọng `prefers-reduced-motion`.

### 3.4 Đồng hồ thời gian thực & phân cấp thị giác

- **`docs/assets/clock.js`** là module thuần + một hàm gắn DOM: `clockParts()` tách giờ theo
  `Intl.DateTimeFormat(timeZone: 'Asia/Ho_Chi_Minh')` nên **không phụ thuộc timezone của máy
  người xem**; mỗi nhịp `setInterval` đều đọc lại `Date.now()` (không cộng dồn) nên không trôi khi
  tab bị treo; tick lại ngay khi `visibilitychange`/`pageshow`/`focus` hoặc đổi ngôn ngữ.
- Trạng thái phiên theo lịch HOSE/HNX: `pre`, `ato`, `open`, `break`, `atc`, `post`, `closed`, `weekend`
  và **`holiday`** (`sessionKey()`), kèm nhãn VI/EN và 3 tông màu (`live`/`amber`/`muted`). Build xuất
  `MARKET_HOLIDAYS` vào `meta.marketHolidays`; `app.js` truyền danh sách này cho `startClock()`, nên
  trong ngày lễ đồng hồ hiển thị **"Nghỉ lễ / Market holiday"**, không đếm ngược tới mốc khớp lệnh.
  Nếu artifact cũ chưa có trường này, đồng hồ vẫn hoạt động với lịch cuối tuần như trước.
- Vòng giây là SVG `stroke-dashoffset` (không phải ảnh), số dùng `tabular-nums` nên **không nhảy layout**
  mỗi giây; có `role="timer"`, `aria-label` theo ngôn ngữ và tôn trọng `prefers-reduced-motion`.
- Phân cấp thị giác dùng chung một bộ quy ước trong `app.css`: gai accent bên trái tiêu đề card,
  gạch nhấn ở `section-head`, KPI có `tone` (`up/down/warn/accent/muted`) lấy từ `kpiCard({tone})`,
  chip lọc có số đếm, `.rec-card` tô viền trái theo khuyến nghị, bảng cổng chất lượng có thanh
  "đang chặn" theo từng cổng.
- Trạng thái độ mới dữ liệu dùng ba mức màu: `.pill.warn` + `.banner-warn` (lệch 1 phiên) và
  `.banner-danger` (lệch ≥ 2 phiên). Chuỗi do JS sinh dùng `tx(vi, en)` — ở chế độ VI+EN ghép
  "VI · EN" và gắn `data-no-i18n` để bộ dịch DOM không dịch chồng.
- Lớp **Interaction & visual polish** ở cuối `app.css` dùng token bóng riêng cho dark/light.
  Card/KPI/khuyến nghị nâng `translateY(-4px)` và tăng bóng khi hover; nút/chip nâng 2px, có trạng
  thái `:active`, `:focus-visible`/`:focus-within`. Hover chỉ bật trong `@media (hover: hover)
  and (pointer: fine)` để không bị dính trên cảm ứng; `@media (pointer: coarse)` tăng vùng chạm;
  `prefers-reduced-motion` tắt cả transition lẫn transform. Transform không làm thay đổi layout.
- Chip mã CW có hành động trong `overview.js::lifeChips()` là `<button type="button">` thật,
  nên Enter/Space và screen reader hoạt động; chip chỉ hiển thị vẫn là `<span>`, không tạo nút giả.
- Lớp **Sidebar emphasis** chuẩn hoá menu semibold 600, nhãn nhóm/mục active bold 700 và
  các token viền, shadow, trạng thái hover cho cột điều hướng.
- Lớp **Reference-inspired analytics shell** sau đó thay shell bằng sidebar/topbar dạng panel nổi
  (radius 16–20px, shadow theo theme), mục active xanh dương nhạt và nhịp nội dung rộng hơn.
  Tiêu đề/KPI/card/bảng/control dùng cùng hệ radius và tương phản; active nav đạt WCAG AA.
  Ở ≤900px sidebar trở lại drawer; ở ≤700px topbar wrap để search có một hàng riêng, và vùng
  chạm coarse vẫn giữ icon 38px/menu 42px. Các rule này chỉ thay presentation, không đổi router/data.
- **Be Vietnam Pro** được self-host trong `docs/assets/fonts/` (Latin + Vietnamese, weight 400–700,
  kèm OFL), preload bản 400 và nạp qua `be-vietnam-pro.css`; không gọi Google Fonts. Cả
  `--font-sans` lẫn token `--font-mono` cũ trỏ tới phông này để UI, bảng và canvas đồng nhất;
  `body` bật `tabular-nums` để giữ căn cột số; `document.fonts.ready` trigger redraw để canvas
  không giữ phông fallback sau lần tải đầu.
- `overview.js` dùng `overview-kpi` cho 10 KPI: lưới desktop **5 × 2**, tablet 2 cột và một cột
  ở màn hình ≤420px. Card là grid `auto auto 1fr`, label có min-height hai dòng và cùng min-height
  tổng thể để giá trị/mô tả thẳng hàng, không cắt nội dung động.

## 4. Hiệu năng

Đo trên máy 4 vCPU với cache sẵn:

| Bước | Thời gian |
|---|---|
| Nạp + chuẩn hoá 273k dòng OHLCV | ~8 s |
| Panel 158k dòng, 148k quan sát IV | ~30 s |
| Snapshot + scoring 348 CW | ~5 s |
| Backtest walk-forward 43 kỳ, 215 lệnh, 854 phiên MTM | ~85 s |
| Xuất 780 tệp JSON | ~25 s |
| **Tổng** | **~123 s** |

RAM đỉnh ~1,5 GB. Toàn bộ chạy trong GitHub Actions runner 7 GB.

## 5. Quyết định thiết kế quan trọng

1. **Không dùng BS@HV làm tín hiệu mua.** Trên thị trường VN gần như mọi CW giao dịch cao hơn giá trị BS theo HV; dùng nó sẽ "mua" toàn bộ thị trường. Thay vào đó dùng **định giá tương đối** (premium, IV residual so đường cong cùng cơ sở).
2. **Percentile trong cùng cơ sở** cho premium/IV, tránh so CW FPT với CW HPG.
3. **Momentum percentile trên các underlying duy nhất**, tránh underlying có 30 CW làm méo phân bố.
4. **Confidence-weighted score**: CW thiếu dữ liệu bị giảm trọng số thay vì bị điểm 0 oan.
5. **Cổng chất lượng tách khỏi điểm**: điểm cao vẫn có thể bị hạ hạng; lý do được ghi vào `rec_reason`.
6. **Backtest mark-to-market theo phiên**: đường vốn/drawdown/lợi nhuận tháng tính lại
   từng phiên cho từng vị thế (không compounding các kỳ chồng lấn); báo cáo **gross và net
   riêng** để chi phí không bị trộn với chất lượng tín hiệu; công bố cả chiến lược thua lỗ.
7. **Artifact tĩnh**: đơn giản, miễn phí, không cần server; đổi lại không có realtime và không có order routing.
8. **Vòng đời là hạng nhất, không phải bộ lọc phụ.** CW đáo hạn liên tục, nên
   trạng thái (`listed/matured/pending/...`) được tính ở engine và xuất bản thành
   `lifecycle.json`; UI chỉ hiển thị lại. Trước đây snapshot không lọc theo ngày
   đáo hạn nên 13 mã đã hết hạn vẫn bị chấm điểm, nằm trong cả `active` lẫn
   `expired`, và KPI in "13 đã đáo hạn" trong khi vũ trụ có 980 mã đã đáo hạn.

## 6. Bảo mật & vận hành

- Không có secret trong repo. `VNSTOCK_API` (nếu dùng) lấy từ GitHub Secrets.
- Dashboard chỉ đọc tệp tĩnh cùng origin; không có CORS, không có endpoint ghi.
- Dữ liệu cá nhân (watchlist/danh mục) không rời khỏi trình duyệt.
- Log build in ra stdout, có `buildSeconds`, `warnings`, số bản ghi từng bước.
- Chuỗi publish: `cw_pipeline.yml` (ingest, cron 16:00 ICT T2–T6) → `workflow_run`
  "CW Pipeline Daily" (completed, chỉ khi `success`) → `cw_intelligence.yml` (build + publish,
  cron dự phòng 17:30 ICT). Nhờ vậy build không còn chạy độc lập trước khi ingest xong.
- Bước "Báo cáo độ mới dữ liệu (phiên)" trong `cw_intelligence.yml` in `asof` / phiên đã đóng /
  số phiên lệch vào Summary và phát `::warning` khi lệch, để sự cố hiện ngay trên trang Actions.
