# Yuanta snapshot — build và publish

## API contract đang dùng

Chỉ dùng URL mà chủ dự án cung cấp:

```text
https://ysradar.yuanta.com.vn/api/v3/market_data/price_board/stock/list_stock_info?stock_type=EW
```

Response dự kiến theo ảnh mẫu: object `{success: true, response: [...]}`; mỗi hàng có `StockCode`, `Exchange`, `SymbolType=EW` và các trường bảng giá như `RefP`, `LastMP`, `TotalVol`, `TotalVal`, `B1P/B1V`, `S1P/S1V`. Adapter giữ nguyên payload, không suy diễn đơn vị hay dữ liệu lịch sử. Nếu response đổi schema, workflow dừng và giữ bản JSON đã publish trước đó.

## GitHub Actions

`CW Yuanta EW snapshot — publish` chạy thủ công hoặc 17:30 giờ Việt Nam từ thứ Hai đến thứ Sáu. Nó cài `requests`, gọi API trong runner GitHub, validate payload, rồi ghi đè `docs/data/yuanta_snapshot.json`. Không có API key, OTP hoặc secret được truyền.

`CW Pipeline — offline tests only` chỉ chạy unit tests. Nó không gọi nguồn dữ liệu.

Để Pages phục vụ artifact, repo cần đặt Pages source là `main` + `/docs`; push commit snapshot vào `main` sẽ kích hoạt deploy GitHub Pages nếu Pages đang bật theo branch.

## Rủi ro và xác minh

Chủ dự án đã xác nhận endpoint có quyền sử dụng/công bố. Việc triển khai dựa trên xác nhận đó; sandbox không truy cập được host Yuanta nên chưa có kiểm tra live. Nếu API yêu cầu header/cookie, trả 403, CORS không liên quan với workflow server-side; cần tài liệu chính thức hoặc cấu hình credential đúng cách, không đưa khóa vào chat.

Snapshot là một lần chụp bảng giá, không phải daily OHLCV. Workflow ghi đè file, không lưu lịch sử. Không phục hồi các artifact lịch sử/analytics cũ và không tính giá/volume theo đơn vị tự giả định.
