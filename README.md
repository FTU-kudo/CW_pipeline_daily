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
- chỉ commit khi nội dung thay đổi; GitHub Pages cần được cấu hình phục vụ `main:/docs` để cập nhật site;
- nếu lần gọi API thất bại hoặc schema đổi, job fail và snapshot cũ không bị ghi đè.

Không có credentials trong workflow hoặc repo. Workflow kiểm thử offline chỉ chạy unit tests, không gọi API.

## Chạy / kiểm thử cục bộ

```bash
python -m pip install requests
python scripts/fetch_yuanta_snapshot.py
python -m http.server 8000 --directory docs
```

Mở `http://127.0.0.1:8000`. Để chạy test:

```bash
python -m pip install -r requirements-core.txt
pytest -q
```

## Mã cũ

`pipeline.py`, `vnstock_config.py` và `cwintel/` được giữ lại để tham khảo/tái sử dụng offline, nhưng không còn là nguồn dữ liệu hay đường phát hành mặc định. Workflow Yuanta không cài hoặc gọi Vnstock, Vietstock, HNX hay VBMA.
