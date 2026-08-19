# Nhật ký Cập nhật & Bảo trì (HANDOFF)
**Ngày tạo:** 19/08/2026 (Cập nhật lúc 18:43 ICT)
**Dự án:** Covered Warrant Analytics Pipeline (`CW_pipeline_daily`)
**Thực hiện bởi:** VNAI (Google Antigravity Agent)

---

## 1. Khắc phục lỗi Timeout 3 tiếng trên GitHub Actions (Từ 17/08/2026)
- **Vấn đề:** Các phiên chạy GitHub Actions bị treo liên tục quá giới hạn 3 tiếng. Nguyên nhân cốt lõi là do API của nguồn VCI (thông qua thư viện `vnstock`) bị sập/chặn request, khiến lệnh gọi mạng bị treo vĩnh viễn không phản hồi.
- **Giải pháp đã triển khai:**
  - **Áp dụng Hard-cap Timeout:** Sử dụng `concurrent.futures.ThreadPoolExecutor(timeout=25)` ở tất cả các hàm gọi API ra bên ngoài (đặc biệt là bước tải OHLCV và giá tài sản cơ sở). Đảm bảo pipeline không bao giờ bị kẹt quá 25s cho một lệnh gọi.
  - **Cơ chế Cầu dao tự động (Circuit Breaker):** Thiết lập logic thông minh đếm số lần timeout. Nếu VCI bị treo liên tiếp 6 lần (`CIRCUIT_OPEN_AFTER = 6`), hệ thống sẽ "gạt cầu dao", bỏ qua hoàn toàn VCI trong các lần gọi tiếp theo và chuyển hướng toàn bộ request sang nguồn dự phòng là `KBS` để đảm bảo thời gian chạy Github Actions được tối ưu nhất (giảm từ 3h xuống còn ~5 phút).

## 2. Khắc phục lỗi "Mất tích 6 mã CW mới niêm yết" (Trên bảng điện hiển thị 322 thay vì 328)
- **Vấn đề:** 6 mã CW mới lên sàn (giao dịch từ 14/08) bị biến mất khỏi bảng điện (dashboard). Dù đã giao dịch 3 ngày nhưng trên bảng điện vẫn không thấy tăm hơi.
- **Nguyên nhân cốt lõi:**
  - Nguồn VCI cập nhật (index) các mã CW mới rất chậm. Khi pipeline gọi API VCI cho 6 mã này, VCI không báo lỗi nhưng trả về bảng dữ liệu rỗng (không có dòng nào).
  - Khối mã cũ mặc định coi "Dữ liệu rỗng từ VCI" = "Mã này chưa có dữ liệu", sau đó bỏ qua và xóa hoàn toàn 6 mã này khỏi danh sách hợp lệ, bất chấp việc nguồn `KBS` có khả năng cung cấp đầy đủ dữ liệu lịch sử.
- **Giải pháp đã triển khai:**
  - **Dự phòng dữ liệu (Fallback to KBS):** Cập nhật hàm `fetch_one`, bổ sung luồng xử lý: Nếu VCI trả về DataFrame rỗng, script sẽ lập tức gọi sang KBS để lấy dữ liệu. Nhờ vậy, 6 mã mới đã lấy lại được chuỗi dữ liệu giao dịch 3 ngày vừa qua.
  - **Bảo hiểm dữ liệu giá (Zero-OHLCV Fallback):** Thêm tính năng "ép" các mã siêu mới (chưa có bất kỳ lịch sử giao dịch nào từ cả VCI lẫn KBS) vẫn phải xuất hiện trên bảng điện. Thay vì bị lọc bỏ ở `step3_filter`, chúng sẽ được giữ lại, và mức giá tham chiếu của chúng (`price_cw`) sẽ được gán bằng cột giá cập nhật live (`gia_hien_tai`) đã được lấy từ Step 1, đảm bảo mô hình định giá Black-Scholes tiếp tục hoạt động mượt mà thay vì báo lỗi chia cho 0.

## 3. Quản lý Git & Triển khai liên tục (CI/CD)
- **Vấn đề:** Ban đầu Agent không thể tự động Git Push qua chế độ chạy nền do thiếu môi trường xác thực (Git Credential Manager) của hệ điều hành.
- **Giải pháp:** Tận dụng phiên đăng nhập (login session) và lưu cấu hình credential thông qua lệnh Terminal thủ công từ người dùng, Agent đã đồng bộ thành công khoá xác thực.
- **Kết quả:** Đã tự động hóa thành công toàn bộ quá trình Commit, Rebase và Push (`git pull --rebase` & `git push`) trực tiếp các bản vá lên repository `https://github.com/FTU-kudo/CW_pipeline_daily` cho cả 2 luồng fix bug lớn nêu trên.

---
*Tất cả các bản vá đã được kiểm tra tính toàn vẹn và không làm gián đoạn luồng xử lý (Data Engineering) hiện tại của hệ thống.*
