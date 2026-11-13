# Yuanta snapshot — build và publish

## API contract đang dùng

Chỉ dùng URL mà chủ dự án cung cấp:

```text
https://ysradar.yuanta.com.vn/api/v3/market_data/price_board/stock/list_stock_info?stock_type=EW
```

Response dự kiến theo ảnh mẫu: object `{success: true, response: [...]}`; mỗi hàng có `StockCode`, `Exchange`, `SymbolType=EW` và các trường bảng giá như `RefP`, `LastMP`, `TotalVol`, `TotalVal`, `B1P/B1V`, `S1P/S1V`. Adapter giữ nguyên payload, không suy diễn đơn vị hay dữ liệu lịch sử. Nếu response đổi schema, workflow dừng và giữ bản JSON đã publish trước đó.

## GitHub Actions

`CW Yuanta EW snapshot — publish` chạy thủ công hoặc 17:30 giờ Việt Nam từ thứ Hai đến thứ Sáu. Nó cài `requirements-core.txt`, gọi API **một lần** trong runner GitHub, validate payload, ghi đè `docs/data/yuanta_snapshot.json`, rồi chạy `scripts/analyze_yuanta_warrants.py --offline docs/data/yuanta_snapshot.json` để sinh `docs/data/yuanta_board_analysis.json` (commit) và `yuanta_covered_warrants.csv` (upload làm artifact của lần chạy, không commit). Không có API key, OTP hoặc secret được truyền.

### Header bắt buộc

Lần chạy đầu tiên fail với `Expecting value: line 1 column 1 (char 0)`: client cũ gửi
`User-Agent: CW-Intelligence/1.0` và không có `Referer`, nên WAF/CDN trả trang HTML chặn
truy cập thay vì JSON. `scripts/yuanta_client.py` gửi cố định:

```text
User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
Referer:    https://ysradar.yuanta.com.vn/
Accept:     application/json, text/plain, */*
```

Lỗi giờ được báo kèm HTTP status, `Content-Type`, 220 ký tự đầu của body và số lần thử,
nên phân biệt được "bị chặn" với "JSON hỏng" ngay trong log CI. 403/429/5xx và lỗi mạng
được retry 3 lần với backoff luỹ thừa (1s, 2s).

`CW Pipeline — offline tests only` chỉ chạy unit tests. Nó không gọi nguồn dữ liệu.

Để Pages phục vụ artifact, repo cần đặt Pages source là `main` + `/docs`; push commit snapshot vào `main` sẽ kích hoạt deploy GitHub Pages nếu Pages đang bật theo branch.

## Rủi ro và xác minh

Chủ dự án đã xác nhận endpoint có quyền sử dụng/công bố. Việc triển khai dựa trên xác nhận đó; sandbox không truy cập được host Yuanta nên chưa có kiểm tra live. Nếu API yêu cầu header/cookie, trả 403, CORS không liên quan với workflow server-side; cần tài liệu chính thức hoặc cấu hình credential đúng cách, không đưa khóa vào chat.

Snapshot là một lần chụp bảng giá, không phải daily OHLCV. Workflow ghi đè file, không lưu lịch sử. Không phục hồi các artifact lịch sử/analytics cũ.

CSV sinh ra từ nguồn nên **không** được commit vào Git: nó chỉ đi kèm artifact của lần chạy
(30 ngày). Chỉ hai file JSON tổng hợp được commit để Pages phục vụ, giống mức công bố đã
được chủ dự án xác nhận cho snapshot.
