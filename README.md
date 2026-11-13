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
python -m http.server 8000 --directory docs
```

Không muốn gọi mạng? Dùng lại payload đã lưu (API gốc hoặc snapshot đã publish):

```bash
python scripts/analyze_yuanta_warrants.py --offline tests/fixtures/yuanta_ew_sample.json \
  --csv /tmp/yuanta_covered_warrants.csv --json /tmp/board.json
```

Script in ra bảng Markdown (10 dòng đầu + top 5 giá trị), tổng hợp phiên và các cảnh báo
chất lượng. Mã thoát: `0` ổn, `1` lỗi mạng/schema, `3` kiểm tra chất lượng mức fail.

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

Những gì **không** làm, vì nguồn không có dữ liệu: chuỗi ngày, giá lý thuyết, Greeks, IV,
định giá, khuyến nghị, backtest. Payload cũng không có ngày đáo hạn, strike, tỷ lệ chuyển
đổi hay tổ chức phát hành. Mã không khớp lệnh trong phiên để trống giá thay vì dùng lại
`LastMP` của phiên trước (tránh biến động ảo).

## Mã cũ

`pipeline.py`, `vnstock_config.py` và `cwintel/` được giữ lại để tham khảo/tái sử dụng offline, nhưng không còn là nguồn dữ liệu hay đường phát hành mặc định. Workflow Yuanta không cài hoặc gọi Vnstock, Vietstock, HNX hay VBMA.
