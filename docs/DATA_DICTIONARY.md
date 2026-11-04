# Từ điển dữ liệu — CW Intelligence

Mọi trường trong `docs/data/*.json`. Quy ước chung:

- **Giá CW**: VND cho 1 chứng quyền (ví dụ `490` = 490 VND/CW). UI hiển thị rút gọn "nghìn VND" ở một số nhãn để dễ đọc, nhưng JSON luôn là VND.
- **Giá cổ phiếu cơ sở**: VND/cổ phiếu.
- **Giá trị giao dịch**: VND.
- **Tỷ lệ (%)**: đơn vị phần trăm (7,8 = 7,8%).
- **Phân số (IV, σ, HV)**: 0,234 = 23,4%.
- **T**: năm, ACT/365.
- `null` = không có dữ liệu (không phải 0).

---

## 1. `meta.json`

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `product` | str | "CW Intelligence" |
| `version` / `methodologyVersion` | str | phiên bản phần mềm / phương pháp |
| `generatedAt` | str | thời điểm build (dd/mm/yyyy HH:MM +07:00) |
| `asof` / `asofLabel` | str | phiên dữ liệu (ISO / dd/mm/yyyy) |
| `dataAgeDays` | int | số ngày lịch từ phiên dữ liệu tới lúc build |
| `dataAgeSessions` | int | số **phiên** dữ liệu còn thiếu so với phiên đã đóng gần nhất |
| `expectedAsOf` / `expectedAsOfLabel` | str | phiên đã đóng gần nhất (ISO / dd/mm/yyyy) |
| `session` | obj | chi tiết lịch phiên: `asof`, `expected`, `lagSessions`, `missing[]`, `todayClosed`, `checkedAt`, `status` |
| `marketHolidays` | list[str] | ngày nghỉ giao dịch ISO cho đồng hồ; lịch 2027 là dự kiến, xem `config.MARKET_HOLIDAYS` |
| `stale` | bool | thiếu ≥2 phiên hoặc dữ liệu cũ hơn `STALE_DATA_DAYS_WARNING` ngày lịch |
| `universe` | obj | `{total, active, expired, underlyings, issuers}` |
| `riskFree` | obj | `{value, source, date}` — lãi suất phi rủi ro năm |
| `dataSources` | list[str] | mô tả nguồn |
| `files` | obj | kích thước các tệp chính (byte) |
| `seriesTickers` | list[str] | danh sách mã có tệp series |
| `seriesBytes` | int | tổng byte của series |
| `counts` | obj | số dòng/bản ghi từng artifact |
| `warnings` | list[str] | cảnh báo build |
| `buildSeconds` | float | thời gian build |

---

## 2. `market.json`

### 2.1 `kpi`

| Trường | Đơn vị | Công thức |
|---|---|---|
| `active` | CW | số CW có giao dịch trong 14 phiên gần `asof` |
| `total` | CW | số CW trong snapshot |
| `expired` | CW | CW đã đáo hạn (còn trong snapshot) |
| `up` / `down` / `flat` | CW | đếm theo `ret1` >0 / <0 / =0 |
| `totalValue` | VND | Σ `value` phiên |
| `totalVolume` | CW | Σ `volume` |
| `itm` / `atm` / `otm` | CW | theo `moneyness` (ATM: \|S/K−1\| ≤ 2%) |
| `liquid` | CW | `value_med20 ≥ 300 triệu` |
| `positiveRec` | CW | BUY + STRONG_BUY |
| `strongBuy` | CW | STRONG_BUY |
| `avgPremium`, `medianPremium` | % | premium hoà vốn |
| `avgScore`, `medianScore` | điểm | CW Score |
| `avgIv`, `avgHv` | phân số | IV và HV trung bình |
| `avgDte` | ngày | thời gian đáo hạn TB |
| `issuers`, `underlyings` | count | số TCPH / cổ phiếu cơ sở |
| `scoreAbove65` | CW | số CW ≥ 65 điểm |
| `noData` | CW | CW không đủ dữ liệu để chấm |

### 2.2 `by_issuer[]`, `by_underlying[]`

`{key, count, value, volume, avgPremium, avgScore, up, down}`.

### 2.3 `top` — mỗi khóa là mảng 10 phần tử

`gainers`, `losers`, `value`, `liquidity_improving`, `unusual`.

Phần tử: `{t, u, iss, chg (%), price, value, score, rec, premium}`.
Điều kiện lọc: `value_med20 ≥ 5 triệu VND`.

### 2.4 `breadth[]`

`{date, n, up, down, value, premium, iv, dte}` — 250 phiên gần nhất.

### 2.5 `distributions`

`{score: [5 bucket], premium: [6 bucket], rec: {label: count}}`.

---

## 3. `screener.json`

`{asof, active: [...], expired: [...]}`

Mỗi dòng (CW active):

| Trường | Đơn vị | Ghi chú |
|---|---|---|
| `t`, `u`, `iss`, `issName` | str | mã CW, cổ phiếu cơ sở, mã & tên TCPH |
| `active` | bool | còn giao dịch tại `asof` |
| `date` | ISO | phiên của giá |
| `price` | VND/CW | giá đóng cửa |
| `chg1`, `ret5`, `ret21` | % | thay đổi giá CW |
| `S` | VND | giá cổ phiếu cơ sở |
| `K` | VND | strike **đã điều chỉnh** |
| `ratio` | n:1 | số CW cho 1 cổ phiếu (đã điều chỉnh) |
| `mat` | ISO | ngày đáo hạn |
| `dte` | ngày | còn lại tới đáo hạn |
| `money`, `moneyPct` | str, % | ITM/ATM/OTM và mức |
| `intrinsic`, `timeValue` | VND/CW | giá trị nội tại / thời gian |
| `premium`, `premiumTime` | % | premium hoà vốn và premium thời gian |
| `be`, `beDist` | VND, % | điểm hoà vốn và khoảng cách |
| `gearing`, `effGear` | × | gearing gộp / hiệu dụng |
| `delta`, `deltaOpt` | CP/CW | delta theo CW / delta quyền trên 1 CP |
| `gamma` | 1/VND | |
| `theta`, `thetaPct` | VND/ngày, %/ngày | |
| `vega` | VND/CW/1% σ | |
| `fvSmile`, `fvHv` | VND/CW | giá trị lý thuyết theo smile cùng cơ sở / theo HV |
| `upsideSmile`, `upsideHv` | % | (FV/giá − 1) |
| `sigma` | phân số | HV dùng cho BS (252 → 60 → 20 → fallback) |
| `iv` | phân số | IV suy ra từ giá |
| `ivVsHv`, `ivResid` | % | IV/HV − 1 ; IV/IV_smile − 1 |
| `ivRank` | 0–100 | percentile IV 1 năm |
| `ivQuality` | str | ok / low / stale |
| `vol`, `value`, `value20` | CW, VND, VND | KL phiên, GT phiên, GT TB 20 phiên |
| `traded20` | % | % phiên có giao dịch (20 phiên) — thô, chưa trừ thời gian niêm yết |
| `volAccel` | × | KL 5 phiên / KL TB 20 phiên |
| `adv20`, `adv5` | VND/phiên | GT giao dịch bình quân 20/5 phiên trên **lịch giao dịch đầy đủ** (phiên không khớp lệnh = 0) |
| `cov20` | % | Độ phủ giao dịch 20 phiên thô (CW mới niêm yết sẽ thấp) |
| `covList` | % | Độ phủ tính từ ngày giao dịch đầu tiên — dùng cho cảnh báo/cổng |
| `listedSessions` | phiên | Số phiên kể từ ngày giao dịch đầu tiên |
| `zero20` | phiên | Số phiên không khớp lệnh trong 20 phiên |
| `amihud` | %/1 tỷ VND | Amihud20: trung vị \|r\|/GT giao dịch × 1e9 (cao = tác động giá lớn) |
| `range20` | % | Trung vị (high − low)/close 20 phiên — proxy chênh lệch mua-bán |
| `turnover` | % | Khối lượng bình quân / lượng CW lưu hành |
| `liqTrend` | × | ADV5/ADV20 (>1 = thanh khoản cải thiện) |
| `dtl` | phiên | Số phiên cần thoát vị thế 50 triệu VND ở mức 20% ADV20 |
| `impact` | % | Ước lượng tác động giá cho 50 triệu VND: η·σ·√(Q/ADV), η = 0,10 |
| `liqBucket` | str | Nhóm thanh khoản hiển thị (rất thấp → rất cao) |
| `rsi`, `macdH`, `ma20`, `ma50`, `above20`, `above50`, `breakout` | | chỉ báo trên chuỗi CW |
| `atr`, `atrPct` | VND, % | ATR(14) và ATR/giá |
| `sessions` | phiên | số phiên có dữ liệu |
| `uRet21`, `uRet63` | % | return cổ phiếu cơ sở |
| `uRsi`, `uAbove50`, `uHv` | | RSI, trên MA50, HV252 của cơ sở |
| `score`, `dq`, `rec`, `recReason` | | CW Score, chất lượng dữ liệu, khuyến nghị, lý do |
| `sc` | obj | điểm 6 thành phần |
| `stale` | phiên | tuổi giá so với `asof` |
| `issShare` | 0–1 | tỷ trọng GT giao dịch của TCPH |
| `termsAdj` | bool | đã dùng điều khoản điều chỉnh |

---

## 4. `recommendations.json`

`{asof, thresholds, gates, cards: [...]}`

`cards[]`:

| Trường | Ý nghĩa |
|---|---|
| `ticker`, `underlying`, `issuer`, `issuer_name` | định danh |
| `recommendation`, `recommendation_vi` | STRONG_BUY/BUY/HOLD/AVOID/HIGH_RISK/NO_DATA |
| `score` | CW Score 0–100 |
| `data_quality` | 0–1 |
| `risk_level` | Thấp / Trung bình / Trung bình - cao / Cao |
| `rec_reason` | lý do phân loại (kể cả lý do bị hạ hạng) |
| `components` | điểm 6 thành phần |
| `component_confidence` | độ tin cậy từng thành phần 0–1 |
| `metrics` | giá, FV smile/HV, upside, premium, DTE, delta, theta, vega, gearing, IV/HV, IV residual, thanh khoản, moneyness |
| `thesis` | 1–2 câu luận điểm |
| `positive_factors`, `negative_factors` | danh sách yếu tố |
| `risk_warnings` | cảnh báo rủi ro cụ thể |
| `invalidation` | điều kiện vô hiệu hoá luận điểm |
| `trading_plan` | `{available, entry_zone, stop_loss, stop_loss_pct, take_profit[], expected_holding_days, risk_reward, rationale, atr_source, atr_value}` hoặc `{available:false, reason}` |
| `disclaimer` | miễn trừ |

`trading_plan.take_profit[]`: `{underlying_move_pct, holding_sessions, estimated_price, estimated_pl_pct}` — **mô phỏng BS**, không phải giá mục tiêu.

---

## 5. `series/cw/<ticker>.json`

| Trường | Kiểu | Ý nghĩa |
|---|---|---|
| `ticker`, `und` | str | |
| `dates` | list[dd/mm/yyyy] | |
| `o,h,l,c` | list[float] | giá CW (VND) |
| `v` | list[float] | khối lượng |
| `ma20`, `ma50` | list[float] | trung bình động |
| `rsi` | list[float] | RSI(14) |
| `macd` | list[float] | MACD histogram |
| `premium` | list[float] | premium hoà vốn (%) |
| `iv`, `sigma` | list[float] | IV / HV (phân số) |
| `deltaOpt` | list[float] | delta quyền trên 1 CP |
| `fv` | list[float] | giá trị BS theo HV |
| `scoreHistory` | list[{date, score}] | (nếu có) lịch sử điểm theo tháng |

Các mảng cùng độ dài, cùng thứ tự thời gian. Phần tử thiếu là `null`.

## 6. `series/und/<sym>.json`

`{ticker, dates, c, ma20, ma50, ma200, rsi, macd, hv20, hv60, v}` — 500 phiên gần nhất.

---

## 7. `underlyings.json`

`{asof, items: [...]}`; mỗi item: `{u, close, ret1, ret5, ret21, ret63, rsi, ma20, ma50, ma200, above20, hv20, hv60, hv252, distHigh60, nCw, avgScore, bestCw, bestScore}`.

---

## 7b. `liquidity.json`

Mặt cắt thanh khoản của phiên dữ liệu:

| Khoá | Nội dung |
|---|---|
| `kpi` | ADV20 trung vị/trung bình, độ phủ trung vị, Amihud trung vị, biên độ trung vị, tập trung top-1/5/10, số CW vướng từng ngưỡng cảnh báo |
| `distribution` | p25/median/p75/p90 của `adv`, `coverage`, `amihud`, `range` |
| `buckets` | Phân bố theo nhóm ADV20: số CW, % vũ trụ, % giá trị phiên, độ phủ trung vị |
| `byIssuer`, `byUnderlying` | ADV20 trung vị, độ phủ, giá trị theo TCPH / cổ phiếu cơ sở |
| `universeFlags` | Một dòng / CW: `adv20`, `cov20`, `covList`, `zero20`, `amihud`, `range20`, `dtl`, `bucket`, `rec`, `score` |
| `idle` | CW đang niêm yết nhưng không có giao dịch trong 14 phiên gần nhất (không vào snapshot) |
| `rankCorr` | Tương quan hạng trong mặt cắt: thanh khoản × premium/IV/DTE |
| `thresholds`, `gates` | Tham số mô hình (tỷ lệ tham gia, vị thế tham chiếu, η, ngưỡng cảnh báo) và cổng khuyến nghị |

`backtest.json` có thêm khối `liquidity` (quintile ADV20 toàn vũ trụ, ngưỡng ADV, lợi nhuận/thắng lệ).

## 8. `backtest.json`

| Khóa | Nội dung |
|---|---|
| `config` | tham số: start/end, rebalance, holding_sessions, top_n, chi phí, risk_free, n_signal_dates |
| `summary` | `{score_top, ew_universe, random, underlying_ew}` → mỗi chiến lược: total_return_pct, cagr_pct, ann_vol_pct, sharpe, max_drawdown_pct, avg_period_ret_pct, median_period_ret_pct, best/worst_period_pct, positive_periods_pct |
| `curve[]` | `{date, score_top, ew_universe, random, underlying_ew, eq_score, eq_ew, eq_random, eq_underlying}` (base 100) |
| `trade_stats` | n_trades, win_rate_pct, avg_return_pct, median_return_pct, avg_win_pct, avg_loss_pct, profit_factor, best/worst_trade_pct, avg_holding_sessions, stop_hit_rate_pct, tp_hit_rate_pct |
| `trades[]` | signal_date, entry_date, exit_date, ticker, underlying, issuer, score, recommendation, entry, exit, gross_ret_pct, ret_pct, mfe_pct, mae_pct, holding_sessions, exit_reason, stop_price, tp_price, stop_hit, tp_hit |
| `buckets[]` | nhóm điểm 20 phiên tới: n, avg_ret_pct, median_ret_pct, win_rate_pct, p25/p75 |
| `by_issuer[]`, `by_underlying[]` | n, avg_ret_pct, win_rate_pct |
| `monthly[]` | `{month, ret_pct}` |
| `cost_sensitivity[]`, `holding_sensitivity[]`, `gate_sensitivity[]`, `filter_sensitivity[]` | các bảng độ nhạy |
| `caveats[]` | giả định & giới hạn |

---

## 9. `quality.json`

`{asof, summary: {ok, warn, error, total}, headline[], checks[]}`

`checks[]`: `{id, title, status: ok|warn|error, value: {...}, detail, severity}`.

## 10. `methodology.json`

`{version, currency_units, conventions[], scoring{weights, formula, note}, recommendation{thresholds, gates, note}, trading_plan, backtest, data_quality_rules[], limitations[], sources[]}`.
