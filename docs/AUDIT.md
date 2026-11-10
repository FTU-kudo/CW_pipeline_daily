# Ghi chú audit và chuyển đổi quyền dữ liệu

Tài liệu audit cũ có các số liệu theo mã, số lượng quan sát, ví dụ giá, thống kê chất lượng/backtest và mô tả cache từ các nguồn. Những nội dung này đã được gỡ khỏi working tree vì có thể cấu thành dữ liệu dẫn xuất được công bố lại. Không dùng tài liệu lịch sử này để suy ra tình trạng dữ liệu hiện tại.

## Trạng thái hiện tại

- Vnstock được ghim thế hệ 6 từ kho phát hành riêng của Vnstock; xem `requirements.txt` và `docs/DEPLOY.md`.
- Không có nguồn G6 được chọn, không có credential trong repo và không phát sinh provider request từ GitHub Actions.
- Adapter VCI/KBS thế hệ cũ không còn là fallback trong pipeline G6. Việc ngừng tích hợp cũ không chứng minh nhà cung cấp đã vĩnh viễn ngừng dịch vụ riêng.
- Public artifacts `docs/data/**`, `docs/data.json`, cache và workbook đã bị xóa khỏi cây hiện tại; dữ liệu mới mặc định nằm trong `output/private-data/` (gitignored).
- Build dưới `docs/` fail-closed qua `cwintel/rights.py`; cần source khớp cùng hồ sơ chấp thuận bằng văn bản còn hiệu lực.
- Tài liệu G6 có route `Macro.global_macro.bond_yield`/`Market.bond(...).yield_history`, nhưng chưa xác nhận tương đương ngữ nghĩa với chuỗi HNX spot-rate/continuous-compounding mà mô hình cũ dùng.

## Giới hạn xử lý

Xóa các artifacts khỏi cây hiện tại không xóa chúng khỏi Git history, fork, cache trình duyệt/CDN hoặc một deployment Pages đã có. Nếu cần gỡ hoàn toàn, chủ repo cần xem lại Pages, lịch sử Git và nơi lưu trữ liên quan. Bản rewrite này không viết lại Git history và không truy cập/triển khai GitHub.

Để xem chính sách và điều kiện tái phát hành, đọc [`DATA_RIGHTS.md`](DATA_RIGHTS.md). Đây là cổng kỹ thuật fail-closed; không thay thế việc kiểm tra hợp đồng/điều khoản với nhà cung cấp và sở giao dịch.
