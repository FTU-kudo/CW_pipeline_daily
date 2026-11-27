# CW Board — Quant Analysis

> **VI:** Bảng giá chứng quyền tĩnh kèm phân tích định lượng, được cập nhật bằng GitHub Actions và xuất bản qua GitHub Pages.
>
> **EN:** A static covered-warrant board with quantitative analytics, refreshed by GitHub Actions and published through GitHub Pages.
>
> **Bản chạy / Live site:** [cw-analytics.vercel.app](https://cw-analytics.vercel.app/)

[English](#english) · [Tiếng Việt](#tiếng-việt)

---

## Tiếng Việt

### Giới thiệu

CW Board thu thập snapshot bảng giá chứng quyền, kiểm tra và phân tích dữ liệu, sau đó cung cấp một giao diện tĩnh để tra cứu. Trình duyệt **chỉ đọc các tệp JSON đã xuất bản trong repo**, không gọi API nhà cung cấp.

Ứng dụng hiển thị tám thẻ KPI cho **phiên hiện đang được tải**: số CW, giá trị giao dịch, số cổ phiếu cơ sở, tăng/giảm/đứng giá, phân bố ITM/ATM/OTM, IV trung vị, IV − HV và spread trung vị. Các chỉ số được tính từ dữ liệu phiên hiện tại và những đầu vào hợp lệ hiện có. Nếu IV/HV hoặc dữ liệu spread không có, giao diện để trống/hiện `—`; **không suy đoán hay dựng dữ liệu lịch sử để lấp chỗ thiếu**. Không dùng các thẻ này để đại diện cho lịch sử nhiều phiên.

### Tính năng

- Bảng giá CW, bộ lọc, sắp xếp, phân tích theo thanh khoản và cổ phiếu cơ sở.
- KPI toàn cảnh gồm tám thẻ; tự xử lý giá trị thiếu, mẫu số bằng 0 và dữ liệu không khả dụng.
- Trang tiếng Việt/English, giao diện sáng/tối và đồng hồ theo múi giờ Việt Nam.
- Ngăn kéo chi tiết từng mã: giá, thanh khoản, bid/ask, dữ liệu định giá, lịch sử, cổ phiếu cơ sở và trường nguồn khi có.
- Lưu chuỗi OHLCV từ các lần chạy pipeline. Lịch sử bắt đầu từ lần chạy đầu tiên; hệ thống không backfill các phiên trước đó.
- Báo cáo phân tích hằng ngày có thể tải dưới dạng artifact của GitHub Actions.

### Phạm vi và giới hạn dữ liệu

- Snapshot lấy từ bảng giá CW (`stock_type=EW`). Dữ liệu gốc được giữ nguyên trước khi làm sạch/phân tích; các đơn vị và kiểm tra chất lượng được ghi trong JSON phân tích.
- OHLCV được tích lũy từ snapshot theo phiên. Một bar chỉ hoàn chỉnh khi snapshot được chụp sau giờ đóng cửa; lần chạy giữa phiên được đánh dấu tạm thời. Phiên bị thiếu được ghi nhận, **không nội suy và không lặp lại giá**.
- Mã không khớp lệnh không có giá đóng cửa trong phiên (`close = null`). Không dùng `RefP` để thay giá đóng cửa.
- IV, HV, định giá, Greeks và spread chỉ được trình bày khi dữ liệu đầu vào đáp ứng yêu cầu. Giá trị không có/không tính được được giữ là `null` hoặc hiển thị `—`, không đổi thành số 0 và không được suy ra từ số liệu lịch sử thiếu.
- Điểm số và chỉ số mô tả dữ liệu; chúng **không phải** dự báo, khuyến nghị đầu tư hay cam kết kết quả.

### Nguồn dữ liệu và ghi công

- Bảng giá: `ysradar.yuanta.com.vn/api/v3/market_data/price_board/stock/list_stock_info?stock_type=EW`.
- Điều khoản CW: repo [Vietstock_CW_bot](https://github.com/FTU-kudo/Vietstock_CW_bot), khi có thể đồng bộ.
- Lợi suất trái phiếu Chính phủ: repo [VN_Bond_Yield_pipeline](https://github.com/FTU-kudo/VN_Bond_Yield_pipeline), khi có thể đồng bộ.

Tên nguồn/endpoint và đường dẫn dữ liệu được ghi nhận ở tầng kỹ thuật để truy xuất và ghi công. Tên nhà cung cấp không được dùng làm nhãn hiển thị trên giao diện. Tệp dữ liệu hiện có tên `docs/data/yuanta_*.json`; đổi tên cần cập nhật đồng bộ các tham chiếu trong ứng dụng và workflow.

### Các tệp dữ liệu đã xuất bản

| Tệp | Nội dung |
|---|---|
| `docs/data/yuanta_snapshot.json` | Snapshot bảng giá gốc và thời điểm lấy dữ liệu |
| `docs/data/yuanta_board_analysis.json` | Phân tích bảng giá, biến động, thanh khoản, spread và kiểm tra chất lượng |
| `docs/data/yuanta_analytics.json` | Phân tích phiên, định giá/chấm điểm khi có đủ dữ liệu và các chỉ số tổng hợp |
| `docs/data/yuanta_sessions.json` | Độ phủ và chuỗi OHLCV theo mã/phiên |
| `docs/data/yuanta_details.json` | Dữ liệu chi tiết cho ngăn kéo từng mã |

Kho dữ liệu lịch sử và dữ liệu hỗ trợ được lưu trong `data/` (ví dụ `data/cw_history/`, `data/cw_terms/`, `data/underlying_history/`, `data/bond_yield/`).

### Chạy cục bộ

Yêu cầu Python 3.11 trở lên. Cài dependency dùng chung cho pipeline và test:

```bash
python -m pip install -r requirements-core.txt
```

Mở giao diện tĩnh từ snapshot/JSON đang có:

```bash
python -m http.server 8000 --directory docs
```

Truy cập `http://127.0.0.1:8000`.

Chạy các bước xử lý thường dùng:

```bash
# Lấy snapshot mới; thao tác này gọi endpoint bên ngoài
python scripts/fetch_yuanta_snapshot.py

# Dùng snapshot đã lưu để tạo CSV và JSON phân tích bảng giá, không gọi lại API
python scripts/analyze_yuanta_warrants.py --offline docs/data/yuanta_snapshot.json

# Cập nhật chuỗi phiên và các JSON phân tích từ snapshot hiện có
python scripts/backfill_yuanta_history.py --offline

# Tạo báo cáo Markdown từ dữ liệu đã publish; không lấy dữ liệu mới
python scripts/daily_analysis_report.py --summary
```

Chạy toàn bộ test (các bài kiểm thử dùng fixture/offline, không gọi API nhà cung cấp):

```bash
pytest -q
```

### Tự động hóa và xuất bản

Workflow `CW Yuanta EW snapshot — publish` (`.github/workflows/cw_pipeline.yml`) có thể chạy thủ công và được lên lịch các ngày trong tuần lúc **17:30 ICT**. Quy trình lấy snapshot, phân tích, cập nhật lịch sử/JSON và chỉ xuất bản thay đổi. Một số nguồn hỗ trợ định giá là tùy chọn; khi không đồng bộ được, pipeline giữ giới hạn dữ liệu và ghi rõ khả năng không có thay vì tạo giá trị giả.

Workflow `CW Yuanta — daily analysis` (`.github/workflows/daily_analysis.yml`) chạy sau đó, lúc **18:10 ICT** các ngày trong tuần. Workflow này chỉ đọc dữ liệu đã publish, không gọi API mới, và tạo báo cáo/artifact. Có thể chạy thủ công từ tab **Actions**.

Để phục vụ website, cấu hình GitHub Pages dùng nhánh `main` và thư mục `/docs`.

### Ghi chú đầu tư

Nội dung chỉ phục vụ thông tin và mục đích giáo dục, không phải tư vấn đầu tư hay đề nghị mua/bán chứng khoán. CW có đòn bẩy, biến động cao và có thể hết hạn vô giá trị. Hãy tự xác minh dữ liệu và cân nhắc rủi ro trước mọi quyết định.

---

## English

### Overview

CW Board collects covered-warrant market snapshots, validates and analyses the data, and serves a static interface for exploration. The browser **reads only JSON files published in this repository**; it does not call the data provider's API.

The overview displays eight KPI cards for **the session currently loaded**: warrant count, trading value, underlying-stock count, advances/declines/unchanged, ITM/ATM/OTM distribution, median IV, IV − HV, and median spread. Metrics are derived from the current session and valid inputs available for it. If IV/HV or spread data is unavailable, the interface leaves the value unavailable or shows `—`; **it does not guess or fabricate historical values to fill gaps**. These cards are not a multi-session history view.

### Features

- Covered-warrant board with filters, sorting, liquidity analysis, and underlying-stock grouping.
- Eight overview KPI cards with safe handling for missing values, zero denominators, and unavailable inputs.
- Vietnamese/English labels, light/dark themes, and a Vietnam-time market clock.
- Per-warrant detail drawer for prices, liquidity, bid/ask, valuation data, history, underlying stocks, and available source fields.
- OHLCV history accumulated from pipeline runs. The series starts with the first run; earlier sessions are not backfilled.
- Daily analysis report available as a GitHub Actions artifact.

### Data scope and limitations

- The snapshot is sourced from the covered-warrant board (`stock_type=EW`). Source values are retained before cleaning/analysis; units and integrity checks are recorded in the analysis JSON.
- Daily OHLCV is accumulated from session snapshots. A bar is complete only when captured after market close; an intraday run is marked provisional. Missing sessions are recorded, **not interpolated or filled by repeating prices**.
- A warrant with no matched trade has no closing price for that session (`close = null`). `RefP` is never substituted for the close.
- IV, HV, valuation, Greeks, and spread are shown only when their required inputs are available. Missing or uncomputable values remain `null` or render as `—`; they are not converted to zero or inferred from unavailable historical data.
- Scores and metrics describe observed data; they are **not** forecasts, investment recommendations, or guarantees of results.

### Data sources and attribution

- Market board: `ysradar.yuanta.com.vn/api/v3/market_data/price_board/stock/list_stock_info?stock_type=EW`.
- Covered-warrant contract terms: [Vietstock_CW_bot](https://github.com/FTU-kudo/Vietstock_CW_bot), when synchronization is available.
- Vietnam government-bond yields: [VN_Bond_Yield_pipeline](https://github.com/FTU-kudo/VN_Bond_Yield_pipeline), when synchronization is available.

Source names/endpoints are recorded in the technical layer for traceability and attribution. The provider name is not used as a user-facing brand. Published data files currently use the `docs/data/yuanta_*.json` naming convention; renaming them requires updating the application and workflow references together.

### Published data files

| File | Contents |
|---|---|
| `docs/data/yuanta_snapshot.json` | Raw market-board snapshot and fetch timestamp |
| `docs/data/yuanta_board_analysis.json` | Board analysis, movers, liquidity, spreads, and integrity checks |
| `docs/data/yuanta_analytics.json` | Session analytics, valuation/scoring when inputs are sufficient, and aggregate metrics |
| `docs/data/yuanta_sessions.json` | OHLCV session series and coverage information |
| `docs/data/yuanta_details.json` | Per-warrant data used by the detail drawer |

Historical and supporting stores live under `data/` (for example `data/cw_history/`, `data/cw_terms/`, `data/underlying_history/`, and `data/bond_yield/`).

### Run locally

Python 3.11 or newer is recommended. Install the shared pipeline and test dependencies:

```bash
python -m pip install -r requirements-core.txt
```

Serve the static UI using the checked-in snapshot/JSON files:

```bash
python -m http.server 8000 --directory docs
```

Open `http://127.0.0.1:8000`.

Common processing commands:

```bash
# Fetch a fresh snapshot; this makes an external API request
python scripts/fetch_yuanta_snapshot.py

# Build a CSV and board-analysis JSON from a saved snapshot, without fetching again
python scripts/analyze_yuanta_warrants.py --offline docs/data/yuanta_snapshot.json

# Update session history and analytics from the existing snapshot
python scripts/backfill_yuanta_history.py --offline

# Build a Markdown report from published data; does not fetch new data
python scripts/daily_analysis_report.py --summary
```

Run the full test suite (tests use fixtures/offline data and do not call the provider API):

```bash
pytest -q
```

### Automation and publishing

The `CW Yuanta EW snapshot — publish` workflow (`.github/workflows/cw_pipeline.yml`) can be run manually and is scheduled on weekdays at **17:30 ICT**. It fetches a snapshot, analyses it, refreshes session history/JSON, and publishes only changed files. Some valuation inputs are optional; if synchronization is unavailable, the pipeline preserves the data limitation and reports unavailable metrics rather than fabricating values.

The `CW Yuanta — daily analysis` workflow (`.github/workflows/daily_analysis.yml`) runs afterward, on weekdays at **18:10 ICT**. It reads published data only, makes no new API request, and creates a report/artifact. It can also be run manually from the **Actions** tab.

To publish the website, configure GitHub Pages to use the `main` branch and `/docs` directory.

### Investment disclaimer

This project is for informational and educational purposes only. It is not investment advice or an offer to buy or sell securities. Covered warrants are leveraged, can be highly volatile, and may expire worthless. Verify the data and consider your risk tolerance before making any investment decision.
