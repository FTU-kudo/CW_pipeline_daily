# Nghiên cứu thanh khoản CW — phương pháp, không phát hành kết quả

Tài liệu này giữ định nghĩa phục vụ phân tích cục bộ. Các snapshot, thống kê theo mã, phân nhóm, kết quả backtest và con số tổng hợp từng có trong bản công khai đã được gỡ vì có thể là dữ liệu dẫn xuất từ nguồn. Không khôi phục hoặc xuất bản lại nếu chưa có quyền bằng văn bản; xem [`DATA_RIGHTS.md`](DATA_RIGHTS.md).

## Chỉ số có thể tính cục bộ

| Chỉ số | Định nghĩa tổng quát | Diễn giải / giới hạn |
|---|---|---|
| ADV20 | Giá trị giao dịch bình quân trên lịch đầy đủ trong 20 phiên | Phiên không giao dịch cần được biểu diễn theo đúng ngữ nghĩa nguồn; không nhầm thiếu dữ liệu với volume bằng 0. |
| Coverage | Tỷ lệ phiên trong cửa sổ mà mã có giao dịch hợp lệ | Cửa sổ và lịch phiên phải đồng nhất giữa các mã. |
| Amihud | Giá trị tuyệt đối của return chia cho giá trị giao dịch, tổng hợp theo cửa sổ | Là proxy price impact, không phải bid-ask spread. |
| Range | `(high − low) / close` tổng hợp theo cửa sổ | Biên độ lớn có thể phản ánh biến động, bước giá hoặc dữ liệu lỗi; không đồng nhất với thanh khoản. |
| Days-to-liquidate | Quy mô vị thế tham chiếu chia cho một phần ADV | Giả định tỷ lệ tham gia phải được nêu; đây không phải cam kết có thể thoát lệnh. |

## Kiểm tra trước khi tin cậy

1. Xác minh OHLCV, volume, đơn vị, timezone, phiên giao dịch và điều chỉnh sự kiện.
2. Giữ giá trị thiếu khác với phiên có giao dịch bằng không; phát hiện duplicate và lỗ hổng lịch sử.
3. Xác định xem giao dịch của nhà tạo lập thị trường có được trộn trong volume hay không.
4. Không suy ra bid/ask, độ sâu sổ lệnh hay khả năng khớp từ nến OHLCV.
5. Tính chỉ số theo thời điểm as-of để tránh nhìn trước tương lai trong backtest.
6. Chỉ chia sẻ các thống kê tổng hợp sau khi rà quyền công bố dữ liệu dẫn xuất theo điều khoản nguồn gốc.

Các phép tính hiện nằm trong `cwintel/liquidity.py`, `cwintel/panels.py` và cấu hình trong `cwintel/config.py`. Các giá trị cấu hình là tham số phần mềm, không phải khuyến nghị đầu tư.
