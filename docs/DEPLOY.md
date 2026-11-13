# Yuanta snapshot — build và publish

## API contract đang dùng

Chỉ dùng URL mà chủ dự án cung cấp:

```text
https://ysradar.yuanta.com.vn/api/v3/market_data/price_board/stock/list_stock_info?stock_type=EW
```

Response dự kiến theo ảnh mẫu: object `{success: true, response: [...]}`; mỗi hàng có `StockCode`, `Exchange`, `SymbolType=EW` và các trường bảng giá như `RefP`, `LastMP`, `TotalVol`, `TotalVal`, `B1P/B1V`, `S1P/S1V`. Adapter giữ nguyên payload, không suy diễn đơn vị hay dữ liệu lịch sử. Nếu response đổi schema, workflow dừng và giữ bản JSON đã publish trước đó.

## GitHub Actions

`CW Yuanta EW snapshot — publish` chạy thủ công hoặc 17:30 giờ Việt Nam từ thứ Hai đến thứ Sáu. Nó cài `requirements-core.txt`, gọi API **một lần** trong runner GitHub, validate payload, ghi đè `docs/data/yuanta_snapshot.json`, rồi chạy `scripts/analyze_yuanta_warrants.py --offline docs/data/yuanta_snapshot.json` để sinh `docs/data/yuanta_board_analysis.json` (commit) và `yuanta_covered_warrants.csv` (upload làm artifact của lần chạy, không commit). Không có API key, OTP hoặc secret được truyền.

### WAF của Yuanta: hai lớp chặn, ba lớp phòng vệ

Endpoint nằm sau WAF của CDN (`*.cdn.vnis.vn`) và chặn theo hai kiểu khác nhau:

| Triệu chứng trong log | Nghĩa | Xử lý trong `scripts/yuanta_client.py` |
|---|---|---|
| `Expecting value: line 1 column 1 (char 0)` | HTML/403 do thiếu header | gửi `User-Agent` Chrome + `Referer` + `Accept` |
| `HTTP cuối=200, content-type=text/html` + `<title>Attention Required!</title>` + `jsKey` | **JS interstitial**: WAF yêu cầu chạy script rồi gọi lại cùng URL kèm token | đọc `jsKey` từ body, gọi lại như trình duyệt (giữ cookie qua `Session`), tối đa 2 vòng |
| `HTTP 404` / interstitial trỏ lại URL gốc | endpoint đổi, hoặc WAF chặn theo TLS/IP | dừng ngay, không retry vô ích; in đầy đủ body |

Ngoài header, client còn:

- **warm-up**: ghé `https://ysradar.yuanta.com.vn/` một lần để nhận cookie CDN (lỗi warm-up
  không chặn luồng chính);
- **TLS fingerprint**: dùng `curl_cffi` với `impersonate="chrome120"` (JA3 giống Chrome thật)
  vì WAF thường chỉ thử thách client có fingerprint lạ như `python-requests`. Thiếu
  `curl_cffi` thì tự lùi về `requests`; chọn bằng `--transport auto|curl_cffi|requests`.

Lỗi được báo kèm HTTP status, `Content-Type`, body (không cắt mất chỗ chứa `jsKey`) và số
lần thử. 403/429/5xx và lỗi mạng được retry 3 lần với backoff luỹ thừa (1s, 2s); lỗi cấu
trúc (404, interstitial không giải được) dừng ngay.

### Nếu vẫn fail sau bản này

Log sẽ cho biết đang ở tình huống nào. Nếu là interstitial lặp lại, WAF đang chặn theo
thứ không thể giải bằng HTTP thuần (IP datacenter của runner, hoặc yêu cầu cookie phiên
đăng nhập). Khi đó cần một trong hai: (a) xác nhận lại với Yuanta về quyền/điều kiện truy
cập API cho client tự động, hoặc (b) chạy lấy dữ liệu từ máy có mạng/IP phù hợp rồi commit
snapshot — workflow vẫn dùng lại được nhờ `--offline`.

`CW Pipeline — offline tests only` chỉ chạy unit tests. Nó không gọi nguồn dữ liệu.

Để Pages phục vụ artifact, repo cần đặt Pages source là `main` + `/docs`; push commit snapshot vào `main` sẽ kích hoạt deploy GitHub Pages nếu Pages đang bật theo branch.

## Rủi ro và xác minh

Chủ dự án đã xác nhận endpoint có quyền sử dụng/công bố. Việc triển khai dựa trên xác nhận đó; sandbox không truy cập được host Yuanta nên chưa có kiểm tra live. Nếu API yêu cầu header/cookie, trả 403, CORS không liên quan với workflow server-side; cần tài liệu chính thức hoặc cấu hình credential đúng cách, không đưa khóa vào chat.

Snapshot là một lần chụp bảng giá, không phải daily OHLCV. Workflow ghi đè file, không lưu lịch sử. Không phục hồi các artifact lịch sử/analytics cũ.

CSV sinh ra từ nguồn nên **không** được commit vào Git: nó chỉ đi kèm artifact của lần chạy
(30 ngày). Chỉ hai file JSON tổng hợp được commit để Pages phục vụ, giống mức công bố đã
được chủ dự án xác nhận cho snapshot.
