# Ghi chú audit và thay đổi nguồn dữ liệu

## Trạng thái hiện tại

- Luồng phát hành hiện tại chỉ lấy snapshot `stock_type=EW` từ endpoint Yuanta do chủ dự án cung cấp.
- `scripts/yuanta_snapshot.py` kiểm tra envelope và nhận diện mã/sàn/loại EW, đồng thời giữ nguyên các trường/value gốc; không tự đổi đơn vị.
- Snapshot mới ghi đè `docs/data/yuanta_snapshot.json`. Không có chuỗi OHLCV ngày cho từng CW nên không tạo chart/backtest/Greeks/khuyến nghị.
- Owner đã tuyên bố có quyền sử dụng/công khai API; agent không truy cập được host Yuanta từ sandbox nên chưa kiểm tra live hoặc rà hợp đồng độc lập.
- Workflow test chạy offline. Workflow publish chỉ gọi endpoint Yuanta; không gọi Vnstock/Vietstock/HNX/VBMA/KBS/VCI.
- Cache/artifact lịch sử cũ đã bị xóa khỏi cây hiện tại, nhưng có thể vẫn tồn tại trong Git history, forks, CDN hoặc deployment trước đó.

## Giới hạn

Endpoint ảnh mẫu chỉ là bảng giá tại thời điểm gọi. `fetchedAt` do client ghi, không phải timestamp giao dịch của sàn. Mọi trường số được giữ nguyên, chưa khẳng định đơn vị. Nếu schema hoặc quyền thay đổi, cần dừng publish và cập nhật adapter sau khi xác minh tài liệu/điều khoản.
