# Kiến trúc sau khi khóa xuất bản dữ liệu

## Nguyên tắc

- Vnstock là thư viện truy cập/chuẩn hóa; giấy phép dùng thư viện không thay thế điều khoản dữ liệu của provider và sở giao dịch.
- Không có nguồn mặc định; người dùng phải chọn `VNSTOCK_SOURCE` và tự quản lý credential trên máy riêng.
- OHLCV, metadata CW, lãi suất, cache và tất cả JSON/Excel phát sinh đều được coi là dữ liệu nguồn hoặc dẫn xuất; mặc định lưu cục bộ, không commit/đính kèm Actions artifact.
- Bộ tính CW (Black–Scholes, biến động, thanh khoản, scoring và backtest) vẫn chạy offline trên cache; chưa thay bằng `vnstock_quant` release candidate vì chưa xác thực tương đương nghiệp vụ.
- `cwintel.build` mặc định ghi vào `output/private-data/dashboard/`. Bất kỳ đích nào trong `docs/` đều bị chặn nếu thiếu hồ sơ chấp thuận bằng văn bản còn hiệu lực, khớp nguồn.

## Luồng dữ liệu riêng tư

```text
Nguồn do người dùng chọn
        │  (khóa chỉ ở máy người dùng; quyền theo điều khoản gốc)
        ▼
pipeline.py ──► output/private-data/cache/*
        │                  │
        ├──► output/private-data/cw_master.xlsx
        ├──► output/private-data/data.json
        └──────────────────┴──► cwintel.data / panels / quant / quality
                                         │
                                         ▼
                         output/private-data/dashboard/*.json
                                         │
                     scripts/serve_private_dashboard.py
                       (127.0.0.1, không public publish)
```

GitHub Actions hiện chỉ cài dependencies lõi và chạy test offline. Không có lịch ingest, không có source keys, không có upload/commit dữ liệu.

## Thành phần

| Thành phần | Vai trò |
|---|---|
| `vnstock_config.py` | Yêu cầu nguồn tường minh; không có VCI/KBS legacy fallback |
| `pipeline.py` | Ingestion thủ công, đầu ra và cache riêng dưới `output/private-data/` |
| `cwintel/data.py` | Đọc cache cục bộ; chuẩn hóa OHLCV và metadata |
| `cwintel/` | Tính năng lượng CW và kiểm tra chất lượng; không gọi mạng |
| `cwintel/rights.py` | Cổng fail-closed nếu đích build nằm trong `docs/` |
| `scripts/check_publication_rights.py` | Kiểm tra record cục bộ (không xác minh tính hợp lệ pháp lý) |
| `scripts/serve_private_dashboard.py` | Phục vụ UI cùng artifact riêng trên loopback |
| `.gitignore` | Chặn cache, workbook, dashboard JSON và hồ sơ quyền ở Git |
| `.github/workflows/cw_pipeline.yml` | Test offline, không ingest/publish |

## Giới hạn migration

- Hiện chưa chọn Vnstock G6 source, chưa có khóa và chưa xác nhận endpoint dữ liệu live.
- G6 docs liệt kê route chứng quyền OHLCV cho một số source; mapping dữ liệu, units, timezone, lịch sử/entitlement cần xác minh trước khi bật nguồn.
- Route bond yield G6 có trong docs nhưng chưa được xác nhận tương đương HNX spot-rate/continuous-compounding mà logic CW hiện cần.
- Public Pages hiện chỉ còn mã UI và tài liệu. Data artifacts đã gỡ khỏi working tree; lịch sử Git và fork vẫn có thể chứa snapshot cũ.
- Gói `vnstock_quant` 1.0.0rc1 ở trang lịch sử được ghi ngày 06-11-2026, tương lai so với ngày rà soát 04-11-2026; không đưa release candidate đó vào requirements.
