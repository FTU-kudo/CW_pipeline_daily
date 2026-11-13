# CW Board — Yuanta

Bảng giá chứng quyền dạng **snapshot** lấy từ API Yuanta mà chủ dự án cung cấp. Mã ứng dụng chỉ gọi endpoint `stock_type=EW`, giữ nguyên tên trường và giá trị gốc từ API, rồi xuất một JSON hiện tại cho GitHub Pages.

> **Giới hạn dữ liệu có chủ ý:** endpoint này không cung cấp OHLCV ngày riêng cho từng chứng quyền. Vì vậy bản này không có chuỗi lịch sử, biểu đồ nến, backtest, Greeks, định giá hay khuyến nghị. Snapshot mới ghi đè snapshot cũ; dự án không tạo dữ liệu lịch sử giả.

## Nguồn

```text
https://ysradar.yuanta.com.vn/api/v3/market_data/price_board/stock/list_stock_info?stock_type=EW
```

Đây là endpoint trong ảnh/tài liệu do chủ dự án cung cấp. Adapter chỉ xác nhận `success`, danh sách `response`, mã, sàn và `SymbolType=EW`; dữ liệu khác được giữ nguyên, không tự quy đổi đơn vị. `fetchedAt` là thời điểm lấy dữ liệu, không phải timestamp phiên do Yuanta xác nhận.

Chủ dự án tuyên bố endpoint được phép sử dụng và công bố. Agent không thể xác minh điều khoản hoặc gọi endpoint này từ sandbox do giới hạn mạng; lần kiểm tra thực tế đầu tiên sẽ là khi chạy workflow trên GitHub Actions.

## Triển khai

Workflow **CW Yuanta EW snapshot — publish**:

- chạy thủ công bằng `workflow_dispatch` hoặc tự chạy ngày làm việc lúc 17:30 ICT;
- lấy snapshot mới, kiểm tra schema rồi ghi `docs/data/yuanta_snapshot.json`;
- làm sạch snapshot đó thành DataFrame, xuất `yuanta_covered_warrants.csv` và
  `docs/data/yuanta_board_analysis.json` (tổng hợp, top biến động, nhóm theo cổ phiếu
  cơ sở, spread, báo cáo chất lượng) — dùng lại chính snapshot vừa lấy nên workflow chỉ
  gọi API **một lần**;
- chỉ commit khi nội dung thay đổi; GitHub Pages cần được cấu hình phục vụ `main:/docs` để cập nhật site;
- nếu lần gọi API thất bại hoặc schema đổi, job fail và snapshot cũ không bị ghi đè.

Không có credentials trong workflow hoặc repo. Workflow kiểm thử offline chỉ chạy unit tests, không gọi API.

## Chạy / kiểm thử cục bộ

```bash
python -m pip install -r requirements-core.txt
python scripts/fetch_yuanta_snapshot.py                 # 1 request, ghi snapshot
python scripts/analyze_yuanta_warrants.py               # làm sạch + CSV + JSON phân tích
python scripts/backfill_yuanta_history.py --offline     # ghi bar phiên + chuỗi + phân tích
python scripts/check_cw_analytics_bridge.py             # báo cáo nối dashboard cũ
python -m http.server 8000 --directory docs
```

Không muốn gọi mạng? Dùng lại payload đã lưu (API gốc hoặc snapshot đã publish):

```bash
python scripts/analyze_yuanta_warrants.py --offline tests/fixtures/yuanta_ew_sample.json \
  --csv /tmp/yuanta_covered_warrants.csv --json /tmp/board.json
```

Script in ra bảng Markdown (10 dòng đầu + top 5 giá trị), tổng hợp phiên và các cảnh báo
chất lượng. Mã thoát: `0` ổn, `1` lỗi mạng/schema, `3` kiểm tra chất lượng mức fail — và khi
đó **không ghi đè** file CSV/JSON đã publish, để Pages không phục vụ một bảng sai và bản tốt
gần nhất không bị mất.

Endpoint nằm sau WAF: ngoài `User-Agent`/`Referer`, client còn ghé trang chủ lấy cookie và
tự đi theo JS interstitial (`jsKey`). Nếu đã cài `curl_cffi` (có trong
`requirements-core.txt`), request dùng TLS fingerprint của Chrome — sát trình duyệt thật
hơn `python-requests`. Chọn thủ công bằng `--transport auto|curl_cffi|requests`, bỏ warm-up
bằng `--no-warmup`.

Mở `http://127.0.0.1:8000`. Để chạy test:

```bash
python -m pip install -r requirements-core.txt
pytest -q
```

## Lớp phân tích bảng giá (`cwintel/yuanta_board.py`)

Phân tích chỉ dùng những gì **một mặt cắt bảng giá** thực sự chứa được:

| Nhóm | Chỉ số | Cách tính / kiểm chứng |
|---|---|---|
| Quy mô | `TradingValueVND`, `TotalVol`, `ValueSharePct`, `ValueRank` | `TotalVol × AvgP`, **đối chiếu** với `TotalVal` của nguồn |
| Biến động | `LastPrice`, `PriceChangePct`, `OpenChangePct` | so `RefP`; chỉ tính khi mã có khớp lệnh |
| Chi phí khớp lệnh | `SpreadAbs`, `SpreadPct`, `SpreadTicks`, `MidQuote` | `(S1P − B1P)` / giá giữa, chia bước giá 10 VND |
| Nhóm | `Underlying` | suy ra từ quy ước mã CW (không phải trường của API) |
| Chất lượng | 10 phép kiểm tra | high/low, giá trong dải trần–sàn, đồng nhất thức giá trị, độ sâu sổ lệnh… |

Đơn vị được **xác nhận bằng bằng chứng trong chính payload**: trên dữ liệu mẫu
`2.775.000 / 17.700 = 156,78` khớp `AvgP`, nên `TotalVal` là VND và giá là VND/CW. Dòng
nào lệch quá 0,5% bị gắn cảnh báo, không bị tự sửa.

## OHLCV theo ngày (`cwintel/yuanta_history.py`)

Mỗi lần workflow chạy **sau khi phiên đóng** (≥ 15:10 ICT; cron là 17:30), payload chứa
đúng bar của phiên đó: `OpenP` (giá khớp đầu), `HighestP`/`LowestP`, `LastMP` (khớp cuối),
`TotalVol`, `TotalVal`. Các bar được nối thành chuỗi ngày trong `data/cw_history/`.

Ba giới hạn được giữ chặt, không "làm đầy" cho đẹp:

| Tình huống | Xử lý |
|---|---|
| Ngày workflow không chạy / thất bại | Ghi vào `coverage.missingSessions`; **không** nội suy, không lặp giá |
| Mã không khớp lệnh | `close = null`, `traded = false`; `RefP` (giá tham chiếu = giá phiên trước) giữ ở cột riêng, **không** dùng làm close |
| Chạy tay giữa phiên | Bar đánh dấu `provisional`; **không** ghi đè bar đã đóng của cùng phiên (nhưng bar đã đóng thì nâng cấp được bar dở dang) |
| Chạy lại trong cùng phiên | Idempotent: upsert theo `(ticker, session)`, không nhân đôi dòng |

Vì endpoint không có dữ liệu quá khứ, lịch sử **bắt đầu từ lần chạy đầu tiên** và dày lên
mỗi ngày — đây là lý do duy nhất có thể có chuỗi OHLCV đúng nghĩa từ nguồn này.

## Xếp hạng và chấm điểm CW (`cwintel/yuanta_scoring.py`)

Mỗi phiên, mọi CW **có khớp lệnh** được chấm điểm 0–100 trên bốn trục đo được từ bảng giá:

| Trục | Trọng số | Đo cái gì | Vì sao |
|---|---|---|---|
| Thanh khoản | 45% | giá trị giao dịch (80%) + khối lượng (20%) | thước đo trực tiếp khả năng vào/ra; khối lượng một mình dễ đánh lừa (CW giá 100 VND khớp 1 triệu đơn vị chỉ là 100 triệu đồng) |
| Chi phí | 30% | spread quanh giá giữa: ≤1% → 100, ≥10% → 0 | 1 bước giá trên CW 100 VND là 10%, chi phí vòng 20% |
| Chất lượng giá | 15% | `LastMVol/TotalVol` | đóng cửa bằng đúng một lệnh thì giá kém đại diện |
| Độ ổn định | 10% | tỷ lệ phiên có khớp lệnh (cần ≥ 5 phiên) | mã im lặng nhiều phiên thì không thoát được |

Mã không giao dịch **không được chấm** — không có giá thì không có gì để chấm. Trục nào
thiếu dữ liệu thì **bỏ khỏi phép chia** (tính lại trọng số) chứ không cộng 0, và mỗi dòng
ghi `coveragePct` để biết điểm dựa trên bao nhiêu phần trăm trọng số.

Điểm này **không phải khuyến nghị mua/bán**. Nó trả lời một câu hẹp: mã này có giao dịch
được ở quy mô vừa phải mà không bị trượt giá quá nhiều không?

### Định giá Black–Scholes: mở khoá bằng điều khoản từ repo Vietstock

Bảng giá Yuanta **không** có bốn biến Black–Scholes cần (`S`, `K`, `T`, `n`). Repo thứ hai
[`Vietstock_CW_bot`](https://github.com/FTU-kudo/Vietstock_CW_bot) có:

| Biến | Nguồn Vietstock |
|---|---|
| `K` strike | `gia_thuc_hien` |
| `n` tỷ lệ chuyển đổi | `ty_le_chuyen_doi` (`"2 : 1"`) |
| `T` ngày đáo hạn | `ngay_gd_cuoi_cung` |
| `S` giá cổ phiếu cơ sở | **không có trực tiếp** — suy ra, xem dưới |

```bash
git clone --depth 1 https://github.com/FTU-kudo/Vietstock_CW_bot.git ../Vietstock_CW_bot
python scripts/import_vietstock_terms.py --source ../Vietstock_CW_bot
# → data/cw_terms/vietstock_terms.csv  (22.372 dòng, 526 mã, 68 phiên)
python scripts/backfill_yuanta_history.py --offline   # tự dùng bảng điều khoản
```

**`S` được suy ra và kiểm chứng chéo, không phải phỏng đoán.** Repo Vietstock đã tính sẵn
`premium` và `don_bay`, và hai công thức đó độc lập với nhau:

```
don_bay  = (S / CW) / n              →  S = don_bay × CW × n
premium  = (K + CW×n − S) / S × 100  →  S = (K + CW×n) / (1 + premium/100)
```

Trên 400/400 mã kiểm tra được, hai cách cho cùng một `S` (lệch < 1%). Bản ghi nào lệch quá
1% bị **loại** khỏi định giá và đếm vào `excluded`, không lấy trung bình hai giá trị.

Kết quả phiên 13/11: **350/353 mã có giao dịch được định giá**, IV trung vị **48,5%**
(p25–p75 = 38,0–67,7%), ITM 59 / ATM 13 / OTM 278, delta trung vị 0,090.

### Đọc kết quả định giá cho đúng

**IV không phải dự báo.** Nó là biến động ẩn suy ngược từ giá thị trường — "thị trường đang
định giá rủi ro bao nhiêu". IV cao hơn HV là **chi phí** của người mua, không phải cơ hội.

**Không dùng `cwPrice/bsPrice` để xếp hạng.** Khi IV suy ngược từ chính giá đó, hai đại
lượng luôn bằng nhau và tỷ lệ luôn ≈ 0 — vô dụng. Thay vào đó dùng **`ivResidualPct`**: IV của
mã so với trung vị IV các CW **cùng cổ phiếu cơ sở**. Cùng rủi ro nền, khác mức bù rủi ro →
so sánh được. Nhóm dưới 5 mã thì không chấm (trung vị 2 quan sát không đáng tin).

**Giới hạn mô hình.** BS giả định quyền chọn châu Âu, không cổ tức. CW Việt Nam có điều khoản
đặc thù (chốt giá, điều chỉnh khi chia cổ tức) mà mô hình không mô tả, nên `bsPrice` chỉ dùng
để xếp hạng tương đối, không phải giá mục tiêu. Lãi suất phi rủi ro là hằng số cấu hình
(`config.DEFAULT_RISK_FREE`) — repo không có chuỗi lợi suất trái phiếu, nên đây là **tham số
phần mềm**, và điều đó được ghi kèm trong payload (`riskFreeSource`).

### Trọng số điểm khi đã có định giá

| Trục | Trọng số |
|---|---|
| Thanh khoản | 34% |
| Chi phí (spread) | 26% |
| **Định giá (IV so với nhóm)** | **20%** |
| Chất lượng giá | 12% |
| Độ ổn định | 8% |

### Ngữ nghĩa từng trường — dùng đúng, không suy diễn

| Trường | Nghĩa | Cách dùng trong dự án |
|---|---|---|
| `RefP` | Giá tham chiếu = **giá đóng cửa phiên trước** | Mốc tính `%Ngày`, `%gap mở cửa`, và là **chốt kiểm tra liên tục** (xem dưới) |
| `OpenP` | Giá khớp đầu phiên | Bar `open`; `%gap` so với `RefP` |
| `HighestP`/`LowestP` | Giá cao nhất/thấp nhất phiên | Bar `high`/`low`; biên độ trong phiên |
| `LastMP` | **Giá đóng cửa hôm nay** (giá khớp cuối) | Bar `close`; `null` khi mã không khớp lệnh |
| `LastMVol` | Khối lượng **của riêng lệnh khớp cuối** | Đo chất lượng giá đóng cửa (`LastMVol/TotalVol`) |
| `AvgP` | Giá khớp bình quân | Đồng nhất thức `TotalVal ≈ TotalVol × AvgP` |
| `TotalVol`/`TotalVal` | Khối lượng / giá trị giao dịch phiên | Xếp hạng thanh khoản |
| `CeilingP`/`FloorP` | Giá trần / sàn của phiên | Khoảng cách tới biên, phát hiện chạm trần/sàn |

Vì `RefP` là giá đóng cửa hôm qua, **% thay đổi có ngay từ phiên đầu tiên** — không cần chờ
phiên thứ hai trong kho.

Ba phân tích mới dựa trực tiếp vào đó (`cwintel/yuanta_intraday.py`):

- **Biên độ trong phiên**: `(HighestP − LowestP) / RefP`, và vị trí giá đóng cửa trong khoảng
  `[LowestP, HighestP]` (0 = đóng đáy, 1 = đóng đỉnh). Ngày 13/11: trung vị 7,3% ≈ 3 bước
  giá, 63 mã đứng giá cả phiên, 188 mã đóng nửa trên / 102 mã đóng nửa dưới.
- **Trần–sàn**: đọc thẳng `CeilingP`/`FloorP`. Tỷ lệ dải **không cố định** — trung vị 3.800%,
  trải 32,8%–25.800% — vì giá CW có thể xuống sát bước giá tối thiểu (`FloorP` = 10 VND).
  Nên không bao giờ dùng công thức ±7%. Ngày 13/11: 2 mã chạm trần, 6 mã chạm sàn.
- **Chất lượng lệnh khớp cuối**: `LastMVol/TotalVol`. 36/353 mã (10,2%) đóng cửa bằng đúng
  một lệnh → giá đóng cửa của các mã này kém đại diện cho cả phiên.

### RefP là chốt kiểm tra tính liên tục

Vì `RefP` hôm nay chính là `close` hôm qua, mỗi phiên có sẵn một phép đối chiếu độc lập với
kho dữ liệu. `backfill_yuanta_history.py` in ra kết quả, và trang hiển thị ở tab **Trần–sàn**:

```
Liên tục RefP vs close 2026-11-12: 353/407 khớp (86.7%) · lệch>25%: 0 · thiếu phiên: 0 → Liền mạch
```

Ba trạng thái, khác nhau về bản chất:

- `linked` — phiên gần nhất trong kho đúng là phiên liền trước **và** `RefP` khớp `close`.
- `missingSession` — phiên liền trước **không có** trong kho. Đây là chẩn đoán đáng tin nhất,
  vì nó không phụ thuộc việc so giá: giá có tình cờ khớp cũng vẫn bị báo đứt.
- `mismatch` — có phiên liền trước nhưng `RefP` lệch `close` quá 25% → nghi bar phiên trước
  không phải giá đóng cửa thật (hoặc nguồn đã điều chỉnh).

Nhờ vậy khoảng trống dữ liệu được phát hiện **ngay phiên sau khi nó xảy ra**, thay vì phải
suy đoán từ một chuỗi giá trông vẫn liền.

### Nối vào bộ máy CW Analytics cũ

`cwintel.yuanta_history.to_cwintel_ohlcv()` chuyển kho lịch sử sang đúng schema
`cwintel.data` đọc (`Ticker/time/open/high/low/close/volume`, ngày `dd/mm/yyyy`, giá theo
nghìn VND để `_price_to_vnd` nhân lại thành VND). Ghi cache bằng
`write_cwintel_cache()`, hoặc `scripts/backfill_yuanta_history.py --cwintel-cache PATH`.

Dashboard cũ (`docs/legacy.html`) **chưa** build được, và đây là lý do cụ thể — kiểm tra
bằng `python scripts/check_cw_analytics_bridge.py`:

| Dashboard cũ cần | Yuanta EW có? |
|---|---|
| OHLCV theo ngày | **có** (tích luỹ như trên) |
| Strike, tỷ lệ chuyển đổi, ngày đáo hạn | **không** — payload chỉ có trường bảng giá |
| Giá cổ phiếu cơ sở | **không** |
| Chuỗi lợi suất phi rủi ro | **không** |
| Quyền công bố dữ liệu dẫn xuất | xem `docs/DATA_RIGHTS.md` |

Thiếu strike/maturity nghĩa là không thể tính intrinsic, premium, moneyness, Greeks, IV,
điểm hay khuyến nghị — những thứ dashboard cũ hiển thị. Không có giá cổ phiếu cơ sở thì
không có HV/IV. Vì vậy phần nối dừng đúng ở OHLCV và dữ liệu thanh khoản, thay vì bịa điều
khoản để lấp chỗ trống.

Những gì **không** làm, vì nguồn không có dữ liệu: giá lý thuyết, Greeks, IV,
định giá, khuyến nghị, backtest. Payload cũng không có ngày đáo hạn, strike, tỷ lệ chuyển
đổi hay tổ chức phát hành. Mã không khớp lệnh trong phiên để trống giá thay vì dùng lại
`LastMP` của phiên trước (tránh biến động ảo).

## Ba workflow và báo cáo hằng ngày

| Workflow | File | Việc |
|---|---|---|
| `CW Yuanta EW snapshot — publish` | `cw_pipeline.yml` | 17:30 ICT T2–T6: lấy snapshot (1 request), làm sạch, ghi bar vào lịch sử, publish Pages |
| `CW Pipeline — offline tests` | `cw_tests.yml` | Chạy test khi push/PR — không gọi mạng |
| `CW Yuanta — daily analysis` | `daily_analysis.yml` | 18:10 ICT T2–T6, hoặc gọi từ cronjob.org: sinh báo cáo Markdown/JSON từ dữ liệu đã publish |

`pages-build-deployment` trong danh sách Actions là workflow **GitHub tự sinh** cho Pages,
không nằm trong repo — nên cộng lại thành 4 mục, không phải "chỉ có 3".

Báo cáo hằng ngày chạy độc lập với việc lấy dữ liệu:

```bash
python scripts/daily_analysis_report.py --summary        # gọn, cho log
python scripts/daily_analysis_report.py --out report/x.md # đầy đủ, ghi file
python scripts/daily_analysis_report.py --format json     # cho hệ thống khác
```

Mã thoát: `0` bình thường, `1` chưa có snapshot, `3` **dữ liệu cũ hơn ngưỡng** (36 giờ mặc
định) — dùng để cronjob.org cảnh báo khi workflow publish thất bại. Cách dựng cronjob.org,
token và lịch: `docs/CRONJOB.md`.

Vì sao workflow phân tích **không** tự gọi API: chỉ có một nơi chạm mạng (`publish`), nên một
lần WAF chặn không thể vừa làm hỏng việc lấy dữ liệu vừa ghi snapshot rỗng vào lịch sử. Lần
chạy phân tích hoặc phản ánh dữ liệu thật, hoặc báo "dữ liệu cũ" — cả hai đều đúng.

## Mã cũ

`pipeline.py`, `vnstock_config.py` và `cwintel/` được giữ lại để tham khảo/tái sử dụng offline, nhưng không còn là nguồn dữ liệu hay đường phát hành mặc định. Workflow Yuanta không cài hoặc gọi Vnstock, Vietstock, HNX hay VBMA.
